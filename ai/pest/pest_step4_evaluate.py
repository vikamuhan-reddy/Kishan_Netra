"""
Pest model - Step 4: evaluation.

Reports overall accuracy WITH a 95% Wilson confidence interval, macro F1,
per-class precision/recall and the confusion matrix. The Wilson interval is
here from the first build on purpose - on the disease model it had to be
retrofitted after an audit, and that is the mistake this pipeline is meant
not to repeat.

Class names are read from pest_classes.json, never hardcoded.
"""
import json
import math
from pathlib import Path

import torch
import torch.nn as nn
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from torchvision import datasets, models, transforms

AI_DIR = Path(__file__).resolve().parent
DATA_DIR = AI_DIR / "pest_dataset_split"
MODEL_PATH = AI_DIR / "pest_best_model.pth"
CLASSES_PATH = AI_DIR / "pest_classes.json"
METRICS_PATH = AI_DIR / "pest_eval_metrics.json"
SPLIT_REPORT_PATH = AI_DIR / "pest_split_report.json"

BATCH_SIZE = 64
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def wilson_interval(acc: float, n: int, z: float = 1.96):
    """95% Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 0.0)
    p = float(acc)
    denom = 1.0 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z ** 2) / (4 * (n ** 2)))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def evaluate_model():
    with CLASSES_PATH.open("r", encoding="utf-8") as f:
        classes = json.load(f)

    print(f"Using device: {DEVICE}")
    model = models.mobilenet_v3_small(weights=None)
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, len(classes))
    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
    model = model.to(DEVICE)
    model.eval()

    test_dataset = datasets.ImageFolder(DATA_DIR / "test", transform)
    if test_dataset.classes != classes:
        raise SystemExit(
            f"Class order mismatch: pest_classes.json={classes} "
            f"but test folder order={test_dataset.classes}"
        )
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

    all_preds, all_labels = [], []
    with torch.no_grad():
        for inputs, labels in test_loader:
            outputs = model(inputs.to(DEVICE))
            _, preds = torch.max(outputs, 1)
            all_preds.extend(preds.cpu().numpy().tolist())
            all_labels.extend(labels.numpy().tolist())

    n = len(all_labels)
    correct = sum(1 for p, l in zip(all_preds, all_labels) if p == l)
    acc = correct / n
    ci_low, ci_high = wilson_interval(acc, n)
    macro_f1 = f1_score(all_labels, all_preds, average="macro")
    report = classification_report(all_labels, all_preds, target_names=classes)
    cm = confusion_matrix(all_labels, all_preds)

    print("\n" + "=" * 58)
    print("           PEST MODEL - STEP 4: EVALUATION")
    print("=" * 58)
    print("\n--- HEADLINE ---")
    print(f"Test Accuracy : {acc * 100:.2f}%  ({correct}/{n})")
    print(f"95% Wilson CI : [{ci_low * 100:.2f}%, {ci_high * 100:.2f}%]")
    print(f"Macro F1      : {macro_f1:.4f}")
    print("\nCondition: 100% field-condition images (Paddy Doctor). There is")
    print("no lab-condition counterpart for either pest class, so unlike the")
    print("disease model this one reports NO lab-vs-field gap. Any claim of")
    print("robustness to lab imagery would be unsupported by this test set.")

    print("\n--- PER-CLASS PRECISION & RECALL ---")
    print(report)

    print("--- CONFUSION MATRIX ---")
    print(f"{'True / Pred':>16}", end="")
    for c in classes:
        print(f"{c[:10]:>12}", end="")
    print()
    for i, row in enumerate(cm):
        print(f"{classes[i]:>16}", end="")
        for val in row:
            print(f"{val:>12}", end="")
        print()

    per_class = {}
    for i, c in enumerate(classes):
        support = int(cm[i].sum())
        rec = float(cm[i][i] / support) if support else 0.0
        rlo, rhi = wilson_interval(rec, support)
        per_class[c] = {
            "support": support,
            "recall": rec,
            "recall_wilson_95_ci": [rlo, rhi],
        }

    metrics = {
        "task": "pest_damage",
        "classes": classes,
        "n_test": n,
        "accuracy": acc,
        "accuracy_wilson_95_ci": [ci_low, ci_high],
        "macro_f1": float(macro_f1),
        "confusion_matrix": cm.tolist(),
        "per_class": per_class,
        "condition": "field_only",
        "lab_vs_field_gap": None,
        "lab_vs_field_gap_note": "No lab-condition pest data exists in the source dataset.",
    }
    with METRICS_PATH.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nWrote {METRICS_PATH.name}")


if __name__ == "__main__":
    evaluate_model()
