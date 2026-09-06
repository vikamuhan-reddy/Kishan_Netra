# KisanNetra — Rigorous Model Validation Protocol
## Beyond the basic Step 4 evaluation

The Step 4 numbers (field accuracy near 87.7%, macro F1 near 0.863, and a
lab/field split) are a real, honest baseline. They are not, by themselves,
enough to survive sustained technical scrutiny.

A single train/test split can look healthy while hiding a class-order bug,
a calibration problem, or a distributional mismatch. The exact failure mode
that already struck this project is a reminder that a passing metric is not the
same as a trustworthy metric. This protocol adds the checks that catch that
class of issue before a judge, reviewer, or demo audience does.

Each section below states what it catches and the concrete check or command to
run.

---

## 1. Statistical confidence — is the reported accuracy real or just a lucky split?

**What it catches:** a single train/test split can overstate or understate true
performance by chance, especially on a smaller validation set. The lab set is
small enough that a narrow point estimate can conceal meaningful uncertainty.

**Do this:**
- Compute a proper confidence interval for every reported accuracy (Wilson or
  Clopper-Pearson, not a naive ±). Report it alongside every percentage.
  Example: "87.70% (95% CI: 85.4–89.8%)" rather than just "87.70%".
- Bootstrap the test set (1,000 resamples) to estimate an empirical
  distribution of accuracy instead of relying only on a single split.
- If time allows, retrain with 2–3 random seeds and report the spread. A model
  that lands at 85%, 88%, and 91% across seeds is behaving differently from one
  that stays near 87–88% consistently.

**Why it matters:** a model can look stable in one run while still being a
statistically fragile result. Confidence intervals turn a point estimate into an
honest claim.

---

## 2. Calibration — does the confidence score mean anything?

**What it catches:** this matters more here than in a typical classifier,
because the differential fusion engine explicitly uses the model's ranked
confidence to decide how much to trust or override the visual prediction. If a
prediction is reported at 95% confidence but is only correct 70% of the time in
that confidence band, the fusion rule is reasoning over a number that lies.

**Do this:**
- Plot a reliability diagram: bucket predictions by confidence range (0–10%,
  10–20%, ... 90–100%), then compute actual accuracy per bucket. A well-
  calibrated model follows the diagonal.
- Compute Expected Calibration Error (ECE): a single number summarizing the gap
  between confidence and accuracy across those buckets.
- If calibration is poor, temperature scaling is an inexpensive, standard
  fix: fit a single scalar on the validation set and rescale logits before
  softmax. This is worth doing before trusting the differential fusion engine's
  confidence thresholds.

**Why it matters:** a fusion layer can only be as honest as its confidence
input. Calibration is not nicety work; it is decision integrity work.

---

## 3. Independent reproduction — verify the evaluation script is not the bug

**What it catches:** this is the exact failure pattern behind the class-label-
swap audit. The evaluation path and the inference path can both be internally
consistent while still disagreeing with the real class mapping. In that case,
the metric looks fine because both code paths are using the same hidden wrong
assumption.

**Do this:** never trust a single code path's self-reported metric. Write a
second, independent scoring script that:
- loads the ONNX model directly, not through `inference_server.py`
- loads `classes.json` directly, not a hardcoded list
- runs the test set and computes accuracy from scratch, using its own argmax
  and class mapping
- compares the result to `eval_metrics.json` and requires an exact match

If the two disagree, that is the signal — the metric is not trustworthy.
This is a cheap and high-value check, and it would likely have caught the
original class-order bug before anyone ever relied on the output.

---

## 4. Out-of-distribution stress test — real generalization, not just an internal split

**What it catches:** a model can score well on a held-out split from the same
source distribution while still failing badly on genuinely new images: a
different phone, different lighting, different camera angle, or a different
field environment.

**Do this:**
- If the Mendeley archive is extracted, treat it as a **pure holdout** and never
  use it for training or threshold tuning. Evaluate it exactly once at the end.
- Better: collect 20–30 new images across the 5 classes using different phones,
  lighting, and field conditions. This is the strongest practical generalization
  test and the most convincing evidence you can show a judge.
- Report OOD performance separately from the Step 4 split metrics. Do not blend
  them together.

**Why it matters:** internal split accuracy is a lab number. OOD performance is
closer to the real deployment question.

---

## 5. Perturbation robustness — does it survive a bad camera day?

**What it catches:** field deployment means imperfect images — glare, motion
blur, off-angle capture, dust on the lens, heavy shadow, or compression loss.
A model that only works on clean test-set images is a lab result, not a field
result.

**Do this:** take a sample of validation images and apply perturbations one at
a time:
- Gaussian blur to simulate motion or focus blur
- brightness and contrast shifts to simulate overexposure and shade
- small rotations to simulate off-angle capture
- JPEG compression at a lower quality setting to simulate cheap sensors or
  lossy transmission

Report accuracy under each condition instead of only on the clean baseline. A
meaningful degradation under blur or brightness shift is useful hardware and
system information, not just a model weakness.

---

## 6. Confusion analysis — do the mistakes make agronomic sense?

**What it catches:** whether errors are random noise or a systematic,
explainable pattern. This matters because a model with meaningful confusion
patterns can still be useful if those confusions are understandable and bounded.

**Do this:** inspect the confusion matrix in `eval_metrics.json` and focus on the
largest off-diagonal cells. As already seen, Blast→Tungro and Brown Spot→Blast
are recurring confusions. Check whether those classes are visually similar in
the field and whether the mistake is agronomically plausible. If the confusion is
between visually dissimilar classes, that is a red flag. If it is between
related disease states with similar lesion structure, it can be an honest,
explainable limitation rather than a model failure.

**Why it matters:** a model that makes “reasonable” mistakes is more credible
than one that makes unpredictable errors across unrelated classes.

---

## 7. Rule-engine correctness tests — not just fault-injection, actual domain correctness

**What it catches:** the rule engine must not only avoid crashing or inventing
values under sensor faults; it must also generate agronomically correct outputs
for known scenarios.

**Do this:** build a small table of hand-verified scenarios with expected
outputs, such as:

| Scenario | Inputs | Expected output |
|---|---|---|
| Textbook blast risk | humidity 88%, temp 27°C, visual=Blast conf 0.7 | disease risk HIGH |
| Healthy, dry, hot | all nutrients normal, moisture 45%, no disease visual | no alerts, no irrigation |
| Classic N deficiency | N low, all else normal | N-deficiency alert with correct fertiliser guidance |
| Tungro, low humidity | visual=Tungro conf 0.8, humidity 40% | capped at MEDIUM with stated reason |

Run these as a labeled test suite, separate from the fault-injection suite.
Fault injection proves the engine does not crash. These scenarios prove the
engine is making sensible agronomic decisions.

---

## 8. Regression lock — protect fixed bugs from silently reappearing

**What it catches:** the class-label-swap bug could reappear any time someone
re-trains, re-exports, or edits `classes.json` by hand. A fix without a
permanent test is only a temporary repair.

**Do this:** add the per-class verification step and the independent-reproduction
check as permanent, always-run tests rather than one-off audit commands. Anyone
who re-trains or re-exports the model should run these before a new artifact is
trusted.

**Why it matters:** the most dangerous model bug is the one that survives the
first validation run and then reappears later in a different code path.

---

## Priority if time is short

If you cannot do all eight checks, this is the order of value:

1. **Section 3 — independent reproduction**
   Cheapest fix for the exact class of bug that already bit this project.
2. **Section 4 — OOD evaluation with new photos**
   Most convincing evidence to a judge and most realistic generalization test.
3. **Section 1 — confidence intervals**
   Makes every reported number defendable instead of a bare point estimate.
4. **Section 6 — confusion analysis**
   Already has the data; it just needs to be read with intent.
5. **Sections 2, 5, 7, and 8** as time allows.

These are all worthwhile, but the first four are the highest-leverage checks for
this project at the moment.
