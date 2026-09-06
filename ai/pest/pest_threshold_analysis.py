"""
Pest model - abstain-threshold analysis.

The headline 94.98% hides the question that actually matters to a farmer:
how often does a HEALTHY leaf get called a pest? That is the error that
erodes trust, and it is the dominant error in this model's confusion matrix.

This sweeps a confidence threshold. A pest verdict is only raised when the
model's max softmax >= T; below that the node reports INCONCLUSIVE and asks
for a re-image rather than guessing.

Class list is read from pest_classes.json. No class name is hardcoded; the
negative class is identified by position in the loaded list via the
NEGATIVE_CLASS constant checked against that list at runtime.
"""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

AI_DIR = Path(__file__).resolve().parent
TEST_DIR = AI_DIR / "pest_dataset_split" / "test"
ONNX_PATH = AI_DIR / "kisannetra_pest_fp32.onnx"
CLASSES_PATH = AI_DIR / "pest_classes.json"
OUT_PATH = AI_DIR / "pest_threshold_analysis.json"

NEGATIVE_CLASS = "No Pest Damage"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess(path):
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return np.transpose(arr, (2, 0, 1)).astype(np.float32)


def softmax(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)


def main():
    classes = json.load(CLASSES_PATH.open(encoding="utf-8"))
    if NEGATIVE_CLASS not in classes:
        raise SystemExit(f"{NEGATIVE_CLASS!r} not in {CLASSES_PATH.name}: {classes}")
    neg = classes.index(NEGATIVE_CLASS)
    cls_to_idx = {c: i for i, c in enumerate(classes)}

    samples = []
    for d in sorted(TEST_DIR.iterdir()):
        if d.is_dir():
            for f in sorted(d.glob("*.*")):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    samples.append((f, cls_to_idx[d.name]))

    sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name

    probs, labels = [], []
    buf, buf_lab = [], []
    for i, (p, l) in enumerate(samples):
        buf.append(preprocess(p))
        buf_lab.append(l)
        if len(buf) == 32 or i == len(samples) - 1:
            probs.append(softmax(sess.run(None, {in_name: np.stack(buf)})[0]))
            labels.extend(buf_lab)
            buf, buf_lab = [], []
    probs = np.concatenate(probs)
    labels = np.array(labels)
    preds = probs.argmax(axis=1)
    conf = probs.max(axis=1)

    is_healthy = labels == neg
    is_pest = ~is_healthy

    print("=" * 70)
    print("  PEST ALERT THRESHOLD SWEEP  (n = %d test images)" % len(labels))
    print("=" * 70)
    print("  A pest alert fires only when max softmax >= T and the predicted")
    print("  class is a pest. Otherwise: no alert (healthy, or INCONCLUSIVE).")
    print()
    print(f"{'T':>6} {'false alerts':>14} {'pest recall':>13} {'inconclusive':>13} {'acc(decided)':>13}")
    print("-" * 70)

    rows = []
    for T in [0.00, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99]:
        decided = conf >= T
        alert = decided & (preds != neg)
        # false alert: a healthy leaf that raises a pest alert
        n_fa = int((alert & is_healthy).sum())
        fa_rate = n_fa / int(is_healthy.sum())
        # pest recall: a pest leaf correctly alerted with the right pest class
        n_hit = int((alert & is_pest & (preds == labels)).sum())
        rec = n_hit / int(is_pest.sum())
        inconc = float((~decided).mean())
        acc_dec = float((preds[decided] == labels[decided]).mean()) if decided.any() else 0.0
        rows.append({"threshold": T, "false_alert_rate": fa_rate, "false_alerts": n_fa,
                     "pest_recall": rec, "inconclusive_rate": inconc,
                     "accuracy_on_decided": acc_dec})
        print(f"{T:>6.2f} {n_fa:>5d} ({fa_rate*100:5.2f}%) {rec*100:>12.2f}% "
              f"{inconc*100:>12.2f}% {acc_dec*100:>12.2f}%")

    print()
    print("Read this as a product decision, not a metric:")
    print("  T=0.00 is the raw model - 1 healthy leaf in 12 raises a false pest alert.")
    print("  Raising T trades missed pest detections for farmer trust.")
    print("Note: all figures come from held-out FIELD-condition Paddy Doctor")
    print("images. They are not a measurement of deployed field performance.")

    json.dump({"task": "pest_damage", "classes": classes,
               "negative_class": NEGATIVE_CLASS, "n_test": int(len(labels)),
               "sweep": rows}, OUT_PATH.open("w", encoding="utf-8"), indent=2)
    print(f"\nWrote {OUT_PATH.name}")


if __name__ == "__main__":
    main()
