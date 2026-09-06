"""
Pest model - independent reproduction check.

This exists to catch the bug class that hit the disease model: a verification
script that carried its own hardcoded class list and therefore silently
disagreed with the model's real output ordering.

Rules this script follows:
  * The class list comes ONLY from pest_classes.json. No class name is
    written anywhere in this file.
  * Inference goes through the exported ONNX artifact, not the .pth. If the
    exported model is what ships, the exported model is what gets checked.
  * Preprocessing is re-implemented here from PIL + numpy rather than reusing
    the torchvision transform objects from the training scripts, so a bug in
    that shared pipeline cannot hide by being on both sides of the check.
  * Labels come from the test directory layout, resolved through the loaded
    class list - not from an assumed index order.

Exit code is non-zero if any check fails.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

AI_DIR = Path(__file__).resolve().parent
TEST_DIR = AI_DIR / "pest_dataset_split" / "test"
ONNX_PATH = AI_DIR / "kisannetra_pest_fp32.onnx"
CLASSES_PATH = AI_DIR / "pest_classes.json"
METRICS_PATH = AI_DIR / "pest_eval_metrics.json"
REPORT_PATH = AI_DIR / "pest_verification_report.json"

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TOLERANCE = 0.005  # 0.5 percentage points between this run and step 4


def wilson_interval(acc: float, n: int, z: float = 1.96):
    if n <= 0:
        return (0.0, 0.0)
    p = float(acc)
    denom = 1.0 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z ** 2) / (4 * (n ** 2)))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def preprocess(path):
    """Bilinear resize to 224x224, CHW float32, ImageNet normalization.
    Matches torchvision Resize((224,224)) + ToTensor + Normalize."""
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return np.transpose(arr, (2, 0, 1)).astype(np.float32)


def main():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        return ok

    for p in (ONNX_PATH, CLASSES_PATH, TEST_DIR):
        if not p.exists():
            print(f"[FAIL] required artifact missing: {p}")
            return 1

    with CLASSES_PATH.open("r", encoding="utf-8") as f:
        classes = json.load(f)
    print(f"Class list loaded from {CLASSES_PATH.name}: {classes}")

    sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out_shape = sess.get_outputs()[0].shape
    n_out = out_shape[-1]
    check("ONNX output width equals len(pest_classes.json)",
          n_out == len(classes), f"model={n_out} classes.json={len(classes)}")

    # Labels resolved through the loaded class list, not an assumed order.
    dirs_on_disk = sorted(d.name for d in TEST_DIR.iterdir() if d.is_dir())
    check("test directories match the loaded class list exactly",
          dirs_on_disk == sorted(classes),
          f"disk={dirs_on_disk} classes.json={sorted(classes)}")

    class_to_idx = {c: i for i, c in enumerate(classes)}
    samples = []
    for cls_dir in sorted(TEST_DIR.iterdir()):
        if not cls_dir.is_dir():
            continue
        for img in sorted(cls_dir.glob("*.*")):
            if img.suffix.lower() in (".jpg", ".jpeg", ".png"):
                samples.append((img, class_to_idx[cls_dir.name]))
    print(f"Reproducing over {len(samples)} test images (ONNX, CPU)...")

    preds, labels = [], []
    batch, batch_labels = [], []
    for i, (path, label) in enumerate(samples):
        batch.append(preprocess(path))
        batch_labels.append(label)
        if len(batch) == 32 or i == len(samples) - 1:
            out = sess.run(None, {in_name: np.stack(batch)})[0]
            preds.extend(np.argmax(out, axis=1).tolist())
            labels.extend(batch_labels)
            batch, batch_labels = [], []

    n = len(labels)
    correct = int(sum(1 for p, l in zip(preds, labels) if p == l))
    acc = correct / n
    lo, hi = wilson_interval(acc, n)
    print(f"\nReproduced accuracy: {acc*100:.2f}% ({correct}/{n})")
    print(f"95% Wilson CI      : [{lo*100:.2f}%, {hi*100:.2f}%]")

    per_class = {}
    for c, idx in class_to_idx.items():
        sup = sum(1 for l in labels if l == idx)
        hit = sum(1 for p, l in zip(preds, labels) if l == idx and p == idx)
        per_class[c] = {"support": sup, "recall": (hit / sup) if sup else 0.0}
        print(f"  {c:16s} recall {per_class[c]['recall']*100:6.2f}%  (n={sup})")

    reported = None
    if METRICS_PATH.exists():
        with METRICS_PATH.open("r", encoding="utf-8") as f:
            m = json.load(f)
        reported = m.get("accuracy")
        check("step 4 metrics use the same class list",
              m.get("classes") == classes,
              f"metrics={m.get('classes')} classes.json={classes}")
        check(f"reproduced accuracy within {TOLERANCE*100:.1f}pp of step 4",
              abs(acc - reported) <= TOLERANCE,
              f"reproduced={acc*100:.2f}% step4={reported*100:.2f}%")
    else:
        check("pest_eval_metrics.json present", False, "run pest_step4_evaluate.py first")

    # A model that has collapsed onto one class can still post a high number
    # on an imbalanced set; require every class to beat chance.
    chance = 1.0 / len(classes)
    worst = min(v["recall"] for v in per_class.values())
    check("every class recall is above chance",
          worst > chance, f"worst={worst*100:.2f}% chance={chance*100:.2f}%")

    all_pass = all(c["pass"] for c in checks)
    report = {
        "task": "pest_damage",
        "artifact_verified": ONNX_PATH.name,
        "classes_source": CLASSES_PATH.name,
        "classes": classes,
        "n_test": n,
        "reproduced_accuracy": acc,
        "reproduced_wilson_95_ci": [lo, hi],
        "step4_reported_accuracy": reported,
        "per_class_recall": per_class,
        "checks": checks,
        "verdict": "PASS" if all_pass else "FAIL",
    }
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nVERDICT: {report['verdict']}  -> wrote {REPORT_PATH.name}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
