import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms.functional as TF
from sklearn.metrics import confusion_matrix, f1_score
from torchvision import datasets, models, transforms

AI_DIR = Path(__file__).resolve().parent
DATA_DIR = AI_DIR / "dataset_split"
MODEL_PATH = AI_DIR / "best_model.pth"
CLASSES_PATH = AI_DIR / "classes.json"
METRICS_PATH = AI_DIR / "eval_metrics.json"
REPORT_PATH = AI_DIR / "validation_report.json"
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
NUM_CLASSES = 5


def load_classes():
    with CLASSES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def softmax(logits):
    logits = np.asarray(logits, dtype=np.float64)
    logits = logits - np.max(logits)
    e = np.exp(logits)
    return e / e.sum()


def wilson_interval(acc: float, n: int, z: float = 1.96):
    if n <= 0:
        return (0.0, 0.0)
    p = float(acc)
    denom = 1.0 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z ** 2) / (4 * (n ** 2)))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def compute_bootstrap(labels: np.ndarray, preds: np.ndarray, n_iters: int = 500, seed: int = 42):
    rng = np.random.default_rng(seed)
    n = len(labels)
    accs = []
    for _ in range(n_iters):
        idx = rng.integers(0, n, size=n)
        accs.append(float(np.mean(labels[idx] == preds[idx])))
    mean_acc = float(np.mean(accs))
    low, high = np.percentile(accs, [2.5, 97.5])
    return mean_acc, (float(low), float(high))


def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10):
    confidences = np.max(probs, axis=1)
    predictions = np.argmax(probs, axis=1)
    correct = predictions == labels

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i == n_bins - 1:
            mask = (confidences >= lo) & (confidences <= hi)
        else:
            mask = (confidences >= lo) & (confidences < hi)
        if not np.any(mask):
            continue
        bin_conf = float(np.mean(confidences[mask]))
        bin_acc = float(np.mean(correct[mask]))
        ece += (np.sum(mask) / len(labels)) * abs(bin_acc - bin_conf)
    return float(ece)


def load_model():
    model = models.mobilenet_v3_small(weights=None)
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, NUM_CLASSES)
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.to(DEVICE)
    model.eval()
    return model


NORMALIZE = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


def get_test_records(normalized: bool = True):
    steps = [transforms.Resize((224, 224)), transforms.ToTensor()]
    if normalized:
        steps.append(NORMALIZE)
    dataset = datasets.ImageFolder(str(DATA_DIR / "test"), transforms.Compose(steps))
    source_labels = []
    for path, _ in dataset.samples:
        name = Path(path).name
        if name.startswith("lab_"):
            source_labels.append("lab")
        else:
            source_labels.append("field")
    return dataset, source_labels


def evaluate_all(model):
    dataset, source_labels = get_test_records()
    loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=False)

    logits_all = []
    labels_all = []
    probs_all = []
    preds_all = []

    for inputs, labels in loader:
        inputs = inputs.to(DEVICE)
        with torch.no_grad():
            logits = model(inputs)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = np.argmax(probs, axis=1)
        logits_all.append(logits.cpu().numpy())
        probs_all.append(probs)
        preds_all.append(preds)
        labels_all.append(labels.numpy())

    logits_all = np.concatenate(logits_all, axis=0)
    probs_all = np.concatenate(probs_all, axis=0)
    preds_all = np.concatenate(preds_all, axis=0)
    labels_all = np.concatenate(labels_all, axis=0)

    acc = float(np.mean(preds_all == labels_all))
    macro_f1 = float(f1_score(labels_all, preds_all, average="macro"))
    cm = confusion_matrix(labels_all, preds_all)

    lab_mask = np.array([s == "lab" for s in source_labels])
    field_mask = np.array([s == "field" for s in source_labels])
    lab_acc = float(np.mean(preds_all[lab_mask] == labels_all[lab_mask])) if np.any(lab_mask) else 0.0
    field_acc = float(np.mean(preds_all[field_mask] == labels_all[field_mask])) if np.any(field_mask) else 0.0
    gap = float(lab_acc - field_acc)

    ci_low, ci_high = wilson_interval(acc, len(labels_all))
    mean_boot, boot_bounds = compute_bootstrap(labels_all, preds_all, n_iters=500)
    ece = compute_ece(probs_all, labels_all, n_bins=10)

    major_confusions = []
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            if i != j and cm[i, j] > 0:
                major_confusions.append({
                    "true_class": i,
                    "pred_class": j,
                    "count": int(cm[i, j]),
                })
    major_confusions = sorted(major_confusions, key=lambda x: x["count"], reverse=True)[:10]

    return {
        "accuracy": acc,
        "lab_accuracy": lab_acc,
        "field_accuracy": field_acc,
        "lab_minus_field_gap": gap,
        "macro_f1": macro_f1,
        "confusion_matrix": cm.tolist(),
        "accuracy_wilson_95_ci": [ci_low, ci_high],
        "bootstrap_mean_accuracy": mean_boot,
        "bootstrap_95_ci": list(boot_bounds),
        "ece": ece,
        "major_confusions": major_confusions,
        "class_names": load_classes(),
        "n_samples": int(len(labels_all)),
    }


def check_independent_reproduction():
    with METRICS_PATH.open("r", encoding="utf-8") as f:
        recorded = json.load(f)
    eval_result = evaluate_all(load_model())
    issues = []

    for key in ["lab_acc", "field_acc", "gap", "macro_f1"]:
        expected = float(recorded.get(key, 0.0))
        actual = eval_result[{
            "lab_acc": "lab_accuracy",
            "field_acc": "field_accuracy",
            "gap": "lab_minus_field_gap",
            "macro_f1": "macro_f1",
        }[key]]
        if abs(expected - actual) > 1e-9:
            issues.append(f"{key}: expected {expected} but got {actual}")

    if recorded.get("classes") != eval_result["class_names"]:
        issues.append("class list mismatch")

    cm_expected = np.asarray(recorded.get("confusion_matrix", []), dtype=int)
    cm_actual = np.asarray(eval_result["confusion_matrix"], dtype=int)
    if cm_expected.shape != cm_actual.shape or not np.array_equal(cm_expected, cm_actual):
        issues.append("confusion matrix mismatch")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "recorded_metrics": recorded,
        "computed_metrics": {
            "lab_acc": eval_result["lab_accuracy"],
            "field_acc": eval_result["field_accuracy"],
            "gap": eval_result["lab_minus_field_gap"],
            "macro_f1": eval_result["macro_f1"],
            "classes": eval_result["class_names"],
            "confusion_matrix": eval_result["confusion_matrix"],
        },
    }


def evaluate_perturbations(model, n_samples: int = 400):
    """Perturbation robustness.

    ORDER MATTERS. Perturbations are applied to the [0,1] image and the result
    is normalized afterwards - never the other way round. torchvision's
    adjust_brightness and adjust_contrast blend against a constant and CLAMP
    the result to [0,1]; a normalized tensor spans roughly [-2.1, +2.6], so
    perturbing after normalizing pinned 64-81% of pixels to a clamp boundary
    and destroyed the image. That harness bug, not model fragility, produced
    the earlier near-chance brightness (26.6%) and contrast (20.3%) figures.
    blur and rotate do not clamp, which is why only those two looked sane.

    A clean-baseline accuracy is measured on the SAME sample so each drop is
    a like-for-like comparison, and every figure carries a 95% Wilson interval
    so a drop cannot be over-read at small n.
    """
    dataset_raw, _ = get_test_records(normalized=False)
    rng = np.random.default_rng(42)
    subset = rng.choice(len(dataset_raw), size=min(n_samples, len(dataset_raw)), replace=False)
    transforms_to_test = {
        "blur": lambda x: TF.gaussian_blur(x, kernel_size=(5, 5)),
        "brightness_low": lambda x: TF.adjust_brightness(x, 0.7),
        "contrast_high": lambda x: TF.adjust_contrast(x, 1.4),
        "rotation_10deg": lambda x: TF.rotate(x, 10),
    }

    def accuracy(fn):
        correct = 0
        for idx in subset:
            image, label = dataset_raw[idx]
            x = NORMALIZE(fn(image) if fn is not None else image)
            with torch.no_grad():
                logits = model(x.unsqueeze(0).to(DEVICE))
            if int(np.argmax(torch.softmax(logits, dim=1).cpu().numpy()[0])) == label:
                correct += 1
        return correct / len(subset)

    baseline = accuracy(None)
    b_lo, b_hi = wilson_interval(baseline, len(subset))
    results = {
        "_clean_baseline": {
            "accuracy": baseline,
            "wilson_95_ci": [b_lo, b_hi],
            "samples": int(len(subset)),
            "note": "Unperturbed accuracy on the same sample; drops are measured against this.",
        }
    }
    for name, fn in transforms_to_test.items():
        acc = accuracy(fn)
        lo, hi = wilson_interval(acc, len(subset))
        results[name] = {
            "accuracy": acc,
            "wilson_95_ci": [lo, hi],
            "drop_vs_clean": baseline - acc,
            "samples": int(len(subset)),
        }
    return results


def evaluate_rule_engine_scenarios():
    import sys

    sys.path.insert(0, str(AI_DIR))
    from step6_rule_engine import evaluate_irrigation, evaluate_nutrients, fuse_disease

    checks = []

    scenario_1 = {
        "rain": False,
        "tank_level": 80,
        "surface_moisture": 15,
        "root_moisture": 12,
        "flow_lpm": 0.0,
        "sensor_status": {
            "tank_level": "VALID",
            "surface_moisture": "VALID",
            "root_moisture": "VALID",
        },
    }
    out_1 = evaluate_irrigation(scenario_1)
    checks.append({
        "name": "irrigation_dry_soil_uses_irrigate",
        "passed": out_1["action"] == "IRRIGATE",
        "detail": out_1,
    })

    scenario_2 = {
        "rain": True,
        "tank_level": 80,
        "surface_moisture": 30,
        "root_moisture": 25,
        "sensor_status": {
            "tank_level": "VALID",
            "surface_moisture": "VALID",
            "root_moisture": "VALID",
        },
    }
    out_2 = evaluate_irrigation(scenario_2)
    checks.append({
        "name": "rain_blocks_irrigation",
        "passed": out_2["action"] == "HOLD",
        "detail": out_2,
    })

    scenario_3 = {
        "soil_ph": 6.8,
        "soil_n": 25,
        "soil_p": 10,
        "soil_k": 20,
        "soil_ec": 2.5,
        "sensor_status": {
            "soil_ph": "VALID",
            "soil_ec": "VALID",
            "soil_npk": "VALID",
        },
    }
    out_3 = evaluate_nutrients(scenario_3)
    checks.append({
        "name": "nutrient_shortage_flags_are_emitted",
        "passed": any(a["nutrient"] in {"N", "P", "K", "EC", "pH"} for a in out_3),
        "detail": out_3,
    })

    d1 = fuse_disease("Blast", 0.85, {"humidity": 90, "air_temperature": 28, "light_lux": 1000})
    d2 = fuse_disease("Healthy", 0.99, {"humidity": 40, "air_temperature": 20, "light_lux": 1000})
    checks.append({
        "name": "disease_fusion_high_and_healthy_ranges",
        "passed": d1["final_risk"] == "HIGH" and d2["final_risk"] == "NONE",
        "detail": {"blast": d1, "healthy": d2},
    })

    return checks


def check_regression_lock():
    classes = load_classes()
    train_names = sorted(p.name for p in (DATA_DIR / "train").iterdir() if p.is_dir())
    expected_order = sorted(train_names)
    if classes != expected_order:
        return {
            "passed": False,
            "reason": f"classes.json order mismatch: classes.json={classes} expected={expected_order}",
        }

    model = load_model()
    model.eval()
    test_dataset = datasets.ImageFolder(str(DATA_DIR / "test"), transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]))
    sample = test_dataset[0][0].unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        out = model(sample)
    if out.shape[1] != len(classes):
        return {
            "passed": False,
            "reason": f"model output has {out.shape[1]} classes but classes.json defines {len(classes)}",
        }

    return {"passed": True, "reason": "class ordering and model output dimension are consistent"}


def main():
    model = load_model()
    validation = evaluate_all(model)
    independent = check_independent_reproduction()
    perturbations = evaluate_perturbations(model)
    rule_checks = evaluate_rule_engine_scenarios()
    regression = check_regression_lock()

    report = {
        "status": "completed",
        "model": str(MODEL_PATH.name),
        "device": str(DEVICE),
        "protocol": {
            "statistical_confidence": {
                "accuracy": validation["accuracy"],
                "wilson_95_ci": validation["accuracy_wilson_95_ci"],
                "bootstrap_mean_accuracy": validation["bootstrap_mean_accuracy"],
                "bootstrap_95_ci": validation["bootstrap_95_ci"],
            },
            "calibration": {"ece": validation["ece"]},
            "confusion_analysis": {
                "macro_f1": validation["macro_f1"],
                "major_confusions": validation["major_confusions"],
                "confusion_matrix": validation["confusion_matrix"],
                "classes": validation["class_names"],
            },
            "independent_reproduction": independent,
            "perturbation_robustness": perturbations,
            "rule_engine_checks": rule_checks,
            "regression_lock": regression,
            "overall_notes": {
                "lab_accuracy": validation["lab_accuracy"],
                "field_accuracy": validation["field_accuracy"],
                "lab_minus_field_gap": validation["lab_minus_field_gap"],
            },
        },
    }

    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== KisanNetra Model Validation Report ===")
    print(f"Model: {MODEL_PATH.name}")
    print(f"Device: {DEVICE}")
    print(f"Overall accuracy: {validation['accuracy'] * 100:.2f}%")
    print(f"Lab accuracy: {validation['lab_accuracy'] * 100:.2f}%")
    print(f"Field accuracy: {validation['field_accuracy'] * 100:.2f}%")
    print(f"Lab-field gap: {validation['lab_minus_field_gap'] * 100:.2f}%")
    print(f"Macro F1: {validation['macro_f1']:.4f}")
    print(f"95% Wilson CI: {validation['accuracy_wilson_95_ci']}")
    print(f"Bootstrap 95% CI: {validation['bootstrap_95_ci']}")
    print(f"ECE: {validation['ece']:.4f}")
    print("\nIndependent reproduction check:")
    print(f"  passed={independent['passed']} issues={independent['issues']}")
    print("\nPerturbation robustness (perturb applied BEFORE normalization):")
    base = perturbations["_clean_baseline"]
    print(f"  clean baseline: {base['accuracy'] * 100:.2f}% "
          f"[{base['wilson_95_ci'][0] * 100:.2f}%, {base['wilson_95_ci'][1] * 100:.2f}%] "
          f"over {base['samples']} samples")
    for k, v in perturbations.items():
        if k.startswith("_"):
            continue
        print(f"  {k}: {v['accuracy'] * 100:.2f}% "
              f"[{v['wilson_95_ci'][0] * 100:.2f}%, {v['wilson_95_ci'][1] * 100:.2f}%] "
              f"drop {v['drop_vs_clean'] * 100:+.2f}pp")
    print("\nRule-engine checks:")
    for item in rule_checks:
        print(f"  {item['name']}: {'PASS' if item['passed'] else 'FAIL'}")
    print(f"\nRegression lock: {'PASS' if regression['passed'] else 'FAIL'} - {regression['reason']}")
    print(f"\nReport saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
