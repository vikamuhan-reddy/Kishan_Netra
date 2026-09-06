# `ai/` — Flaw Audit

**Date:** 2026-09-04 · **Scope:** everything in `ai/` · **Method:** code read plus
runtime reproduction. Every finding below was executed, not inferred.

The build in this directory was produced by a different operator
(`BUILD_LOG.md` names *"Antigravity (Claude Sonnet 4.6)"*, session 2026-09-03).
This is an audit of that work.

**Headline: two findings make the current demo path actively wrong rather than
merely incomplete.** A healthy plant is reported as a viral disease and a viral
disease is reported as healthy; and a model shipped in this folder predicts at
chance level.

| # | Severity | Finding |
|---|---|---|
| 1 | **CRITICAL** | Class labels swapped at inference — Healthy ↔ Tungro |
| 2 | **CRITICAL** | INT8 model predicts at chance (22%) and is still shipped |
| 3 | **CRITICAL** | Rule engine crashes when the pH sensor fails |
| 4 | **CRITICAL** | Missing N/P/K sensors become `0` and generate fertiliser prescriptions |
| 5 | HIGH | Near-duplicate deduplication never implemented, but ticked as done |
| 6 | HIGH | Steps 5–8 ran without their checkpoints; both trackers are stale |
| 7 | HIGH | "Early warning" trend layer is fed statistically independent noise |
| 8 | HIGH | Trend warning can display a negative time-to-threshold |
| 9 | MEDIUM | Brown Spot and Tungro can never reach HIGH risk |
| 10 | MEDIUM | The lab-vs-field gap is explained incorrectly |
| 11 | MEDIUM | The mock generator can only emit `VALID`, so the failure path is undemonstrable |
| 12 | MEDIUM | Irrigation reads invented defaults for missing sensors |
| 13 | LOW | EC validity is gated on the pH status key |
| 14 | LOW | Deprecated `datetime.utcnow()` |
| 15 | LOW | Orphaned export artifacts |

---

## 1. CRITICAL — Class labels are swapped at inference

`inference_server.py:36` and `step8_integration_test.py:66` both declare:

```python
CLASSES = ["Bacterial Blight", "Blast", "Brown Spot", "Tungro", "Healthy"]
```

The model was trained with `torchvision.datasets.ImageFolder`, which sorts class
directories **alphabetically**. The real order is:

```
['Bacterial Blight', 'Blast', 'Brown Spot', 'Healthy', 'Tungro']
```

`eval_metrics.json` confirms this, and `dashboard.html:417` uses the correct
mapping — so the dashboard and the inference server **disagree with each other**.

**Reproduced.** Running the exported FP32 ONNX over held-out test images:

```
true Healthy  -> argmax idxs [3, 3, 3, 3, 3, 0, 3, 3, 3, 1, 4, 3]
true Tungro   -> argmax idxs [3, 1, 4, 4, 4, 4, 4, 4, 4, 4, 1, 4]
```

Index 3 is Healthy and index 4 is Tungro. The server's list has them the other
way round.

**Consequence.** Every healthy plant is reported as **Tungro**, and every plant
with **Tungro** — an insect-vectored viral disease with no cure, where the
response is to remove infected plants — is reported as **Healthy**. This is the
worst available failure direction: the model is right and the label is wrong, so
nothing in the confidence score signals a problem.

**Fix.** Delete both hardcoded lists. Persist the class order at training time
(`image_datasets['train'].classes` is already read at `step3_train.py:43`) into
a `classes.json` written next to the weights, and load it everywhere. A
hardcoded ordering that duplicates a sorted directory listing will drift again.

---

## 2. CRITICAL — The INT8 model predicts at chance and is still in the folder

`step5_export.py` documents, in its own header, that five separate quantization
approaches were tried and all produced 22–36% accuracy. The root cause it
records is that every onnxruntime path inserts Quantize/DequantizeLinear ops on
activations, and MobileNetV3's HardSwish outputs are clipped by the quantization
range. Its stated resolution is that FP32 is the deployment model.

**That analysis is correct and the honesty in the source file is good. The
problem is what is on disk.**

`kisannetra_int8.onnx` (1.70 MB) is still present, loads cleanly, and is 3.5×
smaller than the FP32 model — which is exactly the shape of a result someone
puts on a slide.

**Reproduced,** 150 held-out test images balanced 30 per class:

```
kisannetra_fp32.onnx     111/150 = 74.0%
kisannetra_int8.onnx      33/150 = 22.0%
```

Five classes means chance is 20%. **The INT8 model has not degraded; it has no
signal at all.**

*(The 74.0% for FP32 is lower than the reported 87.70% because this sample is
balanced 30-per-class and taken alphabetically, while the real test set is
dominated by classes the model handles well. It is a consistency check, not a
competing accuracy figure.)*

**Fix.** Delete `kisannetra_int8.onnx`, or rename it to something that cannot be
mistaken for a deliverable (`kisannetra_int8.BROKEN.onnx`). Then record Step 5
honestly: INT8 was attempted, it failed for a named architectural reason, and
FP32 is the deployment model. A failed quantization with a diagnosed cause is a
respectable engineering result. A 1.7 MB file implying success is not.

---

## 3. CRITICAL — The rule engine crashes when the pH sensor fails

`step6_rule_engine.py`. In `evaluate_nutrients`, `ph` is bound only inside the
success branch:

```python
if _sensor_ok(status, "soil_ph"):
    ph = sensor["soil_ph"]
    ...
else:
    alerts.append({... "Soil pH sensor FAILED — MANUAL CHECK RECOMMENDED." ...})
```

but the zinc rule later reads it unconditionally:

```python
if n > N_HIGH or ph > 7.2:
```

When the pH sensor is `FAILED` or `UNKNOWN` and nitrogen is not excessive,
Python's short-circuit does not save it and `ph` is unbound.

**Reproduced** with `soil_ph` status `FAILED` and `soil_n` = 40:

```
CRASH: UnboundLocalError cannot access local variable 'ph' where it is not
       associated with a value
```

**Consequence.** The sensor-failure path is the one the whole Section 6 contract
exists to handle, and it is the path that crashes. Press the failure case in a
demo and the engine raises instead of printing MANUAL CHECK RECOMMENDED.

**Fix.** Initialise `ph = None` before the branch and guard the zinc rule on
`ph is not None`.

---

## 4. CRITICAL — Missing nutrient sensors become `0` and produce prescriptions

Also `step6_rule_engine.py`:

```python
n = sensor.get("soil_n", 0)
p = sensor.get("soil_p", 0)
k = sensor.get("soil_k", 0)
ec = sensor.get("soil_ec", 0)
```

There is no `sensor_status` check for N, P, K or EC anywhere. A missing reading
becomes `0`, which is below every low threshold.

**Reproduced** with `soil_n` and `soil_p` absent from the payload:

```
MISSING-SENSOR ALERT -> N LOW | Soil N 0 mg/kg is low — apply urea or split-dose…
MISSING-SENSOR ALERT -> P LOW | Soil P 0 mg/kg is low — apply DAP or SSP…
```

**Consequence.** This violates two of the absolute rules in Section 4 of the
master specification simultaneously — *"never replace a missing/failed sensor
value with zero or a guess"* and the prohibition on presenting invented values
as measured. It then converts the invented zero into a fertiliser
recommendation, which is the one output class the specification is most careful
about elsewhere. Note the contrast: the zinc rule is written with exemplary
care, and the nitrogen rule three lines above it will tell a farmer to buy urea
because a wire fell off.

**Fix.** Give N, P, K and EC the same status gate the pH rule already has, and
emit an UNKNOWN alert rather than a prescription when a reading is absent.

---

## 5. HIGH — Near-duplicate deduplication was never implemented

Step 2's checklist in `PS-26180-MASTER.md` ticks *"Deduplicated exact + near-
duplicate images"*. `step2_clean_split.py` contains MD5 hashing only — zero
matches for `phash`, `dhash`, `imagehash` or any perceptual method.

MD5 catches byte-identical files. The 53 removals are exact duplicates. **Near-
duplicates — the same leaf photographed twice, the ones that actually leak
across a train/test boundary and inflate test accuracy — were never searched
for.**

This matters more than usual here, because Paddy Doctor field images are
captured in sessions: multiple frames of the same plant, seconds apart, are
common and are not byte-identical.

**Fix.** Either add a perceptual hash pass with cluster-aware splitting (all
members of a near-duplicate cluster must land in the same split), or untick the
box and state exact-only in the results. The reported accuracy cannot be defended
against a leakage question until one of those is true.

---

## 6. HIGH — Steps 5–8 ran without their checkpoints, and both trackers are stale

Three sources disagree about where the project is:

| Source | Claims |
|---|---|
| `BUILD_LOG.md` | last entry 2026-09-03 10:05; Steps 3–8 TODO |
| `PS-26180-MASTER.md` | Steps 0–4 DONE, Steps 5–8 TODO |
| Disk | Step 5 exports, Step 6 engine, Step 7 dashboard, Step 8 test harness all present |

**Step 5 is a CHECKPOINT.** The specification requires reporting and waiting for
confirmation before continuing. It was executed, and Steps 6, 7 and 8 were built
on top of it, with the tracker still reading `TODO`.

Step 4's checklist has *"Reported to human and received go-ahead"* ticked. No
such confirmation exists in the session record.

**Consequence.** The tracker is the project's stated single source of truth, and
it currently understates the work while overstating the review. Anyone resuming
from it will redo Step 5 and will believe Step 4 was signed off.

**Fix.** Reconcile the master file against disk, mark clearly which checkpoints
were passed unreviewed, and retire `BUILD_LOG.md` or make it generated. Two
hand-maintained trackers will always drift.

---

## 7. HIGH — The "early warning" layer is fed independent noise

`sensor_contract.py` draws every field from an independent uniform distribution
on each call. Successive readings have **no temporal correlation whatsoever**.

`step6_rule_engine.py` then computes a rate of change over the last ten readings
and emits:

```
EARLY WARNING (root moisture trending ↓, ~N readings to threshold)
```

Over independent uniform samples this slope is a random variable centred on
zero. The number of readings to threshold is meaningless.

The master specification is explicit on this point: *"Never label a plain
threshold alert an 'AI prediction' — that requires an actual trend
calculation."* The trend calculation exists; its input does not support it.

**Fix.** Make the generator a random walk with per-channel drift, bounds and
realistic step sizes, so moisture declines between rainfall events instead of
teleporting. The rule-engine code is fine — the data feeding it is not.

---

## 8. HIGH — Trend warning can display a negative time-to-threshold

```python
steps = int((value - threshold) / roc) if roc != 0 else 0
```

The guard admits any `value < threshold * 1.2`, which includes values **above**
the threshold. With `value=25`, `threshold=22`, `roc=-1.0`, this yields
`steps = -3`, printed as *"~-3 readings to threshold"*.

**Fix.** Clamp to `max(0, …)` and only emit the warning when the value is
approaching the threshold from the safe side.

---

## 9. MEDIUM — Brown Spot and Tungro can never reach HIGH risk

```python
HIGH_RISK_DISEASES = {
    "Bacterial Blight": {"humidity_thresh": 80, "temp_range": (25, 35)},
    "Blast":            {"humidity_thresh": 85, "temp_range": (24, 32)},
    "Brown Spot":       {},
    "Tungro":           {},
}
```

Empty dictionaries fall back to `hum_thresh = 999` and `t_range = (0, 100)`. A
humidity of 999% is unreachable, so `env_corroborated` is permanently `False`
for those two classes, and HIGH risk requires corroboration. **Brown Spot and
Tungro are silently capped at MEDIUM forever.**

Brown spot is strongly associated with nutrient-poor and drought-stressed soil,
and the node measures exactly that; tungro is insect-vectored, so humidity is
genuinely the wrong corroborator. Both deserve a rule, or an explicit comment
saying no environmental corroborator applies — not an empty dictionary that
looks like an oversight because it is indistinguishable from one.

---

## 10. MEDIUM — The lab-vs-field gap is explained incorrectly

`PS-26180-MASTER.md` Step 4 reports lab 77.78% (77/99), field 88.79% (800/901),
and explains it as *"lab images are high-res studio portraits; field images are
real Tamil Nadu conditions."*

That explains a gap. It does not explain **this** gap, whose direction is the
reverse of the project's own central claim about out-of-distribution vision.

The likely cause is in `split_report.json`: training was roughly **4,185 field
images against 436 lab images**, about 90/10. The model is better on field data
because field data is nearly all it saw. The lab test set is 99 images, so
77.78% carries roughly ±8 points at 95% confidence.

**This is still a defensible result** — it is honest, and it is measured. But
stated as written it reads as *"our model handles hard field conditions better
than clean lab conditions,"* which inverts the argument. A judge who asks one
follow-up question finds the training split.

**Fix.** Restate with the cause and the confidence interval. Consider reporting
a lab-trained control for contrast.

*(Two obligations recorded earlier are correctly honoured in Step 4: Healthy is
flagged as field-only with no lab figure, and Brown Spot's lab metric is flagged
as least reliable. Credit where due.)*

---

## 11. MEDIUM — The failure path cannot be demonstrated

`sensor_contract.py` hardcodes every status to `VALID`:

```python
"sensor_status": {
    "surface_moisture": "VALID", "root_moisture": "VALID",
    "soil_ph": "VALID", "tank_level": "VALID"
}
```

`STALE`, `FAILED` and `UNKNOWN` are defined in the contract and **can never be
produced by the generator**. The MANUAL CHECK RECOMMENDED path — the behaviour
that distinguishes this system from a dashboard — is unreachable in any demo
driven by this generator.

It is also why finding #3 was never noticed: the crash requires a `FAILED` pH
status, which the generator cannot emit.

**Fix.** Add a fault-injection parameter so a status can be forced, and add the
failure cases to `step8_integration_test.py`.

---

## 12. MEDIUM — Irrigation reads invented defaults

```python
tank = sensor.get("tank_level", 100)
surf = sensor.get("surface_moisture", 100)
root = sensor.get("root_moisture", 100)
```

A missing tank level defaults to **100% full**, the most dangerous possible
assumption for a pump-safety gate. The status check in `_sensor_ok` currently
catches this, so it is latent rather than live — but it is one refactor away
from becoming finding #4 in the irrigation path.

**Fix.** Default to `None` and force the caller to handle absence.

---

## 13. LOW — EC validity is gated on the pH status key

```python
if _sensor_ok(status, "soil_ph"):  # same 7-in-1 sensor
```

The reasoning is sound — pH and EC come from the same RS485 device — but a
partial failure of that device is real, and the coupling is invisible to anyone
reading the alert output. Add a `soil_ec` status key to the contract.

---

## 14. LOW — Deprecated `datetime.utcnow()`

`sensor_contract.py` uses `datetime.utcnow()`, deprecated since Python 3.12 and
scheduled for removal. It also returns a naive datetime to which `"Z"` is then
appended, asserting UTC without carrying it. Use
`datetime.now(timezone.utc).isoformat()`.

---

## 15. LOW — Orphaned export artifacts

`kisannetra_fp32.onnx.data` (6.09 MB, 12:17) and `kisannetra_preproc.onnx`
(6.11 MB, 14:51) are both present. `kisannetra_fp32.onnx` loads standalone, so
the `.data` external-weights file appears to be left over from an earlier export
and is not referenced. Roughly 12 MB of ambiguity in a directory where someone
has to pick the right file under demo pressure.

**Fix.** Delete what is unused; name what is kept so its role is obvious.

---

## What is genuinely good

Worth stating, because the list above is one-sided by construction:

- **The evaluation is honest.** Lab and field accuracy are reported separately,
  the confusion matrix is now persisted, and it is internally consistent — the
  diagonal sums to 877, matching 77 lab + 800 field, and the macro F1
  recomputes to 0.863 against the reported 0.8627.
- **The quantization failure is documented rather than hidden**, with a correct
  architectural diagnosis (HardSwish clipping under QDQ).
- **The zinc rule is written exactly as specified** — an agronomic prior with a
  soil-test recommendation, never a sensor claim.
- **The split is leakage-aware by source** and the test set is 90.1% field,
  which is the harder and more honest choice.
- **The dashboard's class mapping is correct**, which is what makes finding #1
  diagnosable rather than invisible.

---

## Suggested order of work

1. **#1 class swap** — smallest fix, largest consequence, and it invalidates any
   live demo run through `inference_server.py` until done.
2. **#3 and #4 rule-engine faults** — both are in the sensor-failure path, both
   are a few lines, and #4 is a direct violation of the specification's absolute
   rules.
3. **#2 remove or rename the INT8 artifact** and record Step 5 honestly.
4. **#11 fault injection** in the mock generator, then add failure cases to the
   Step 8 harness — this is what would have caught #3 and #4 without an audit.
5. **#6 reconcile the trackers** before any further steps are built on them.
6. **#5 near-duplicate dedup**, or amend the claim.
7. **#10 restate the gap** with its actual cause before it reaches a slide.
