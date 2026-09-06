"""
KisanNetra — Out-of-Distribution (OOD) Evaluation
===================================================
Tests the deployed FP32 ONNX model on genuinely new images — not from the
training/validation/test split — to measure real generalization.

Usage
-----
    python ood_eval.py <real_photos_dir>

Expected directory layout (same as dataset_split/test):

    real_photos/
        Bacterial Blight/   <- 4–6+ images
        Blast/
        Brown Spot/
        Healthy/
        Tungro/

The class names must match classes.json exactly (case-sensitive).

Output
------
  - Prints a side-by-side table vs. the Step 4 split numbers.
  - Saves ood_eval_results.json next to this script.

Why this matters
----------------
Internal split accuracy is a lab number. OOD performance is the closest
practical proxy for what the model does on a real Indian field. A model
that memorizes its training distribution scores well on a held-out split
from that same distribution; it fails on genuinely new images. This test
cannot be faked with images from dataset_split/.
"""
import sys
import io
import json
import math
import os
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image
import onnxruntime as ort

AI_DIR      = Path(__file__).parent
MODEL_PATH  = AI_DIR / "kisannetra_fp32.onnx"
CLASSES_F   = AI_DIR / "classes.json"
METRICS_F   = AI_DIR / "eval_metrics.json"
OUTPUT_F    = AI_DIR / "ood_eval_results.json"
IMG_SIZE    = 224
MEAN        = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD         = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ── Wilson confidence interval (95%) ─────────────────────────────────────────
def wilson_ci(correct: int, total: int, z: float = 1.96):
    """Returns (lower, upper) as fractions [0,1].

    Wilson score interval is well-behaved for small n (unlike Wald ±).
    At n=20 the CI is wide (~±20%); at n=50 it is ±14%. Report the CI
    alongside every number so the uncertainty is visible, not hidden.
    """
    if total == 0:
        return 0.0, 0.0
    p = correct / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return max(0.0, centre - spread), min(1.0, centre + spread)


# ── Identical preprocessing as inference_server.py ───────────────────────────
def preprocess(path: str) -> np.ndarray:
    """Raw image file → normalized float32 tensor (1, 3, 224, 224).

    Must be byte-for-byte equivalent to inference_server.preprocess so that
    the OOD numbers are directly comparable to inference server output.
    """
    img = Image.open(path).convert("RGB")
    img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]
    return arr.astype(np.float32)


def main():
    if len(sys.argv) < 2:
        print("Usage: python ood_eval.py <real_photos_dir>")
        print()
        print("  <real_photos_dir>  directory with class subdirectories")
        print("  Example: python ood_eval.py real_photos/")
        sys.exit(1)

    ood_dir = Path(sys.argv[1])
    if not ood_dir.is_dir():
        print(f"ERROR: {ood_dir} is not a directory.")
        sys.exit(1)

    # ── Load model and class list ─────────────────────────────────────────────
    if not MODEL_PATH.exists():
        print(f"ERROR: {MODEL_PATH} not found. Run step5_export.py first.")
        sys.exit(1)

    with open(CLASSES_F, encoding="utf-8") as f:
        classes = json.load(f)

    print(f"Loading model: {MODEL_PATH}")
    sess = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    n_out   = sess.get_outputs()[0].shape[-1]
    if n_out != len(classes):
        print(f"ERROR: model outputs {n_out} logits but classes.json has {len(classes)} entries.")
        sys.exit(1)
    print(f"Model loaded. Classes: {classes}\n")

    IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    # ── Per-class evaluation ──────────────────────────────────────────────────
    per_class = {}
    total_correct = 0
    total_images  = 0

    for cls in classes:
        cls_dir = ood_dir / cls
        if not cls_dir.is_dir():
            print(f"  [SKIP] {cls} — directory not found at {cls_dir}")
            per_class[cls] = {"found": 0, "correct": 0, "acc": None, "ci_lo": None, "ci_hi": None}
            continue

        paths = [p for p in sorted(cls_dir.iterdir()) if p.suffix.lower() in IMG_EXTS]
        if not paths:
            print(f"  [SKIP] {cls} — no images found in {cls_dir}")
            per_class[cls] = {"found": 0, "correct": 0, "acc": None, "ci_lo": None, "ci_hi": None}
            continue

        correct = 0
        errors  = []
        for p in paths:
            try:
                tensor = preprocess(str(p))
                logits = sess.run(None, {in_name: tensor})[0][0]
                pred   = classes[int(np.argmax(logits))]
                if pred == cls:
                    correct += 1
                else:
                    errors.append(f"{p.name} → {pred}")
            except Exception as exc:
                errors.append(f"{p.name} → ERROR: {exc}")

        n   = len(paths)
        acc = correct / n
        lo, hi = wilson_ci(correct, n)
        per_class[cls] = {
            "found": n, "correct": correct,
            "acc": acc, "ci_lo": lo, "ci_hi": hi,
            "errors": errors,
        }
        total_correct += correct
        total_images  += n

    # ── Load Step 4 split numbers for comparison ──────────────────────────────
    split_acc = {}
    if METRICS_F.exists():
        with open(METRICS_F, encoding="utf-8") as f:
            m = json.load(f)
        # Reconstruct per-class accuracy from confusion matrix
        cm = m.get("confusion_matrix", [])
        cls_list = m.get("classes", [])
        for i, c in enumerate(cls_list):
            if i < len(cm) and cm[i]:
                row_total = sum(cm[i])
                split_acc[c] = cm[i][i] / row_total if row_total > 0 else 0.0

    # ── Report ────────────────────────────────────────────────────────────────
    print("=" * 72)
    print("  KisanNetra — OOD Evaluation Report")
    print(f"  Model: {MODEL_PATH.name}")
    print(f"  Source: {ood_dir.resolve()}")
    print(f"  Time: {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print("=" * 72)
    print()

    header = f"{'Class':<20} {'N':>4}  {'OOD Acc':>8}  {'95% CI':>17}  {'Step4 Split':>11}  {'Delta':>7}"
    print(header)
    print("-" * 72)

    for cls in classes:
        d = per_class.get(cls, {})
        n   = d.get("found", 0)
        acc = d.get("acc")
        lo  = d.get("ci_lo")
        hi  = d.get("ci_hi")
        s4  = split_acc.get(cls)

        acc_str = f"{acc*100:6.1f}%" if acc is not None else "  N/A  "
        ci_str  = f"[{lo*100:.1f}%, {hi*100:.1f}%]" if lo is not None else "       N/A      "
        s4_str  = f"{s4*100:6.1f}%"   if s4  is not None else "    N/A"
        delta   = (acc - s4) if (acc is not None and s4 is not None) else None
        d_str   = f"{delta*100:+.1f}%" if delta is not None else "    N/A"

        print(f"{cls:<20} {n:>4}  {acc_str:>8}  {ci_str:>17}  {s4_str:>11}  {d_str:>7}")

        if d.get("errors"):
            for e in d["errors"][:3]:      # show at most 3 misclassifications
                print(f"  {'':20} ↳ {e}")
            if len(d["errors"]) > 3:
                print(f"  {'':20} ↳ ... {len(d['errors']) - 3} more")

    print("-" * 72)
    if total_images > 0:
        overall = total_correct / total_images
        lo_all, hi_all = wilson_ci(total_correct, total_images)
        print(f"{'OVERALL':<20} {total_images:>4}  {overall*100:6.1f}%  [{lo_all*100:.1f}%, {hi_all*100:.1f}%]")
    print("=" * 72)

    # ── Interpretation guidance ───────────────────────────────────────────────
    print()
    print("INTERPRETATION NOTES")
    print("  • OOD Acc < Step4 Split: expected — internal split images come from")
    print("    the same distribution as training data. OOD is the harder test.")
    print("  • Wide CI on small N is expected and honest. 5 images → ±20%.")
    print("    More images narrow the interval; 20+ per class is strongly preferred.")
    print("  • Delta column: negative = model generalized less well on real images.")
    print("    Values within 1–2 CI widths of zero are within noise.")
    print()
    print("  Do NOT blend these numbers with Step 4 metrics — they answer")
    print("  different questions. Report them separately.")
    print()

    # ── Save JSON artifact ────────────────────────────────────────────────────
    output = {
        "model":        MODEL_PATH.name,
        "ood_source":   str(ood_dir.resolve()),
        "timestamp":    time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_images": total_images,
        "total_correct": total_correct,
        "overall_acc":  total_correct / total_images if total_images > 0 else None,
        "per_class":    per_class,
    }
    with open(OUTPUT_F, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved to: {OUTPUT_F}")


if __name__ == "__main__":
    main()
