# KisanNetra — Pest-Damage Classifier

A **second, independent** MobileNetV3-Small classifier, sitting alongside the
5-class disease model. It shares no weights, no class list and no artifacts
with the disease pipeline; nothing in `ai/` outside this folder was modified.

**Software-only validation. No Qualcomm / Hexagon / NPU hardware was used and
no NPU profiling was performed.**

## Data

Source: the **already-downloaded** `paddy-disease-classification/train_images`
folder — the same one the disease model uses. No new dataset was downloaded,
so no new licensing question arises. (The standalone "Rice Pest Dataset" was
*not* used; it derives substantially from IP102, which is academic-use-only.)

| Class            | Raw   | Exact dupes removed | Usable |
|------------------|-------|---------------------|--------|
| Hispa            | 1,594 | 5                   | 1,589  |
| Dead Heart       | 1,442 | 13                  | 1,429  |
| No Pest Damage   | 1,764 | 15                  | 1,749  |

Both pest classes are far above the ~100-image reliability threshold, so no
class needed the low-reliability flag that Brown Spot's 90-image lab side
carries in the disease model.

**`No Pest Damage` is a design decision, not a silent addition.** A
hispa-vs-dead-heart-only model cannot say "no pest here" — it would label
every healthy leaf as one of the two pests. The negative class is drawn from
the same `normal` folder the disease model's `Healthy` class comes from, so it
adds no new data source. Set `INCLUDE_NEGATIVE = False` in
`pest_step2_clean_split.py` to get a pure two-class pest-type discriminator.

Split is 70/15/15, per class, on the deduplicated pool, so no image appears in
more than one split.

**Condition:** 100% field-condition imagery. Paddy Doctor has no lab-condition
pest data, so this model has **no lab-vs-field gap to report** — the same way
`Healthy` was noted as a field-only class in the disease model. Any claim that
this model is robust on lab-style imagery would be unsupported by its test set.

Because `No Pest Damage` and the disease model's `Healthy` draw on the same
source images, the two models are not statistically independent on those
images. They remain independent on all pest and disease imagery.

## Results (test set, n = 717)

| Metric | Value |
|---|---|
| Accuracy | **94.98%** (681/717) |
| 95% Wilson CI | **[93.13%, 96.35%]** |
| Macro F1 | 0.9519 |

Per-class recall: Dead Heart 98.60% (n=215), Hispa 95.40% (n=239),
No Pest Damage 91.63% (n=263).

Confusion is almost entirely Hispa ↔ No Pest Damage (22 healthy leaves called
Hispa, 11 Hispa called healthy) — expected, since early hispa scarring is
visually subtle. Dead Heart is near-perfectly separable.

The Wilson interval is computed in `pest_step4_evaluate.py` itself, from the
first build. It was not added later by an audit.

## Export

`kisannetra_pest_fp32.onnx` — 5.81 MB, 94.98% (ONNX-verified, matches PyTorch).
This is the deployment artifact.

**INT8 attempted and failed, reported honestly.** Static QUInt8 quantization
produced **34.59%** accuracy versus 94.98% FP32 — a collapse, saved as
`kisannetra_pest_int8.BROKEN_35pct.onnx` and never presented as deployable.
This independently reproduces the disease model's HardSwish finding
(`ai/step5_export.py`), which recorded 22–36% across five onnxruntime schemes.
Same architecture, same root cause: onnxruntime inserts Quantize/Dequantize ops
on activation tensors, and HardSwish's negative outputs get clipped.

## Independent reproduction check

`pest_verify_independent.py` was written **as part of this build**, not as a
follow-up fix, because a hardcoded class list is exactly what went wrong in the
disease model's verification script. Its rules:

- The class list comes only from `pest_classes.json`; no class name appears
  anywhere in the file.
- It runs the **exported ONNX artifact**, not the `.pth`.
- Preprocessing is re-implemented from PIL + numpy rather than reusing the
  training scripts' torchvision transforms, so a shared-pipeline bug cannot
  hide by being on both sides of the comparison.
- Labels are resolved through the loaded class list, not an assumed index order.

Current verdict: **PASS**, all five checks. It reproduces 94.98% exactly
through the independent preprocessing path.

## Running it

```
python pest_step2_clean_split.py      # inventory + leakage-free split
python pest_step3_train.py --timing-only   # time one epoch before committing
python pest_step3_train.py --epochs 4      # ~3 min on CUDA
python pest_step4_evaluate.py         # accuracy + Wilson CI + confusion matrix
python pest_step5_export.py           # ONNX FP32 + honest INT8 attempt
python pest_verify_independent.py     # independent reproduction; nonzero exit on failure
```

## Alert threshold — a product decision, made on numbers

`pest_threshold_analysis.py` sweeps the confidence at which a pest alert
fires. The question is not "what is the accuracy" but "how often does a
healthy leaf raise a false pest alert", because that is the error that erodes
a farmer's trust.

| T | false alerts on healthy | pest recall | inconclusive |
|---|---|---|---|
| 0.00 (raw) | 8.37% (22/263) | 96.92% | 0% |
| 0.70 | 5.32% | 93.39% | 6.6% |
| **0.80** | **3.04%** | **90.31%** | **11.2%** |
| 0.90 | 0.76% | 83.70% | 18.8% |

**Decision: T = 0.80.** The raw model raises a false pest alert on roughly
1 healthy leaf in 12, which is too high to trust. T=0.80 cuts that by 2.75×
for 6.6 points of recall. The reason abstaining is cheap here is specific to
this project: the node is a **fixed sentinel watching one zone on a capture
cycle**, so an inconclusive frame is a deferred look at the same plants on the
next cycle, not a missed detection. T=0.90 was rejected — 13 points of recall
is too much to pay once false alerts are already down to 3%.

## Fusion rule — decided explicitly

`pest_fusion_rule.py`, tested by `test_pest_fusion.py` (18/18 passing).

1. **Disease and pest stay two independent verdicts.** Nothing is averaged.
   They answer different questions about the same image; a blended score
   could not be explained to a farmer or a judge.
2. **Same corroboration principle as `fuse_disease`** — visual confidence
   alone can never reach HIGH:
   - *Hispa* can reach HIGH, corroborated by soil nitrogen above `N_HIGH`.
     This is not a new agronomic claim; `step6_rule_engine` already asserts
     the N-excess → leaf-pest relationship in its own nutrient rule, and the
     node has that sensor.
   - *Dead Heart* is **capped at MEDIUM**. Yellow stem borer, and nothing on
     this node observes stem-borer pressure. HIGH is unreachable by design,
     exactly the precedent already set for Tungro.
3. **Alerts require T ≥ 0.80**, else INCONCLUSIVE and re-image.
4. **The disagreement case is explained, not silent.** "Disease: Healthy,
   Pest: Hispa" is not a contradiction — the disease model has no pest class
   and cannot represent feeding damage. The pest channel is authoritative on
   pest questions. When both channels fire, the farmer gets **one** advisory
   naming both, because they make one trip to the field.

Two tests exist specifically to enforce the project's honesty rules: a
faulted NPK probe and an absent nitrogen reading must both fail to
corroborate, so a missing sensor can never escalate an alert.

## Not done — deliberately

The dashboard is still **not** wired up. The fusion rule above is now decided
and tested, but rendering it in `dashboard.html` is a separate change.
