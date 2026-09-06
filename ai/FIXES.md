# `ai/` — Remediation Plan

Companion to [`FLAWS.md`](FLAWS.md). One section per finding, in the order they
should be done. Every fix below is concrete: the file, the lines, the
replacement, and the command that proves it worked.

**Numbering matches `FLAWS.md` exactly.** Where a fix closes more than one
finding, that is stated.

Run everything through the project interpreter:

```
ai/.venv/Scripts/python.exe
```

---

## Order of work, and why this order

| Phase | Fixes | Why here |
|---|---|---|
| **A — Stop the bleeding** | 1, 2 | The demo path is currently wrong. Nothing else matters until it is right. |
| **B — Close the spec violations** | 3, 4, 12 | Direct breaches of the Section 4 absolute rules, all in the sensor-failure path, all small. |
| **C — Make the bugs catchable** | 11 | Fault injection is what would have caught B without an audit. Do it right after B so the tests can prove B. |
| **D — Restore honesty of record** | 6, 10, 5 | Claims that outrun the artifacts. Fix before anything is presented. |
| **E — Make the trend layer real** | 7, 8 | The early-warning claim needs data with structure before it means anything. |
| **F — Finish the edges** | 9, 13, 14, 15 | Correctness and hygiene. |

Phase A is roughly twenty minutes. Phase A plus B is the difference between a
demo that misleads and a demo that holds.

---

# PHASE A — Stop the bleeding

## Fix 1 — Class labels swapped at inference *(CRITICAL)*

The root cause is that the class order is written down in three places and
derived in a fourth. Deleting the duplicates is the fix; correcting them in
place only resets the clock.

### 1a. Make training emit the class order as an artifact

`step3_train.py`, immediately after line 43 (`class_names = image_datasets['train'].classes`):

```python
class_names = image_datasets['train'].classes
print(f"Classes: {class_names}")

# The class order is decided by ImageFolder's alphabetical sort, not by us.
# Persist it beside the weights so no downstream file has to guess it.
import json
with open(AI_DIR / "classes.json", "w", encoding="utf-8") as f:
    json.dump(class_names, f, indent=2)
```

Use whatever the script's existing path variable is; define `AI_DIR =
Path(__file__).parent` if it has none.

### 1b. Write `classes.json` now, without retraining

The order is recoverable from the split directory, and `eval_metrics.json`
already records it. Do not retrain to produce a five-line file:

```bash
ai/.venv/Scripts/python.exe -c "import json,os; json.dump(sorted(os.listdir('dataset_split/train')), open('classes.json','w'), indent=2)"
```

Expected `classes.json`:

```json
["Bacterial Blight", "Blast", "Brown Spot", "Healthy", "Tungro"]
```

### 1c. Delete the hardcoded lists

`inference_server.py:36` — replace:

```python
CLASSES      = ["Bacterial Blight", "Blast", "Brown Spot", "Tungro", "Healthy"]
```

with:

```python
# Loaded, never hardcoded: the order is ImageFolder's alphabetical sort and a
# duplicate of it in this file is what swapped Healthy and Tungro before.
with open(AI_DIR / "classes.json", encoding="utf-8") as _f:
    CLASSES = json.load(_f)
```

Add `import json` at the top. Do the same at `step8_integration_test.py:66`.

`dashboard.html:416-417` is already correct, but it is a fourth copy. Either
have the dashboard fetch the class list from the inference server's existing
`"classes"` response field (`inference_server.py:96` already returns it), or
leave a comment at those lines pointing to `classes.json` as the source of
truth.

### 1d. Add a guard so this can never silently recur

In `inference_server.py`, after the session loads:

```python
_n_out = SESSION.get_outputs()[0].shape[-1]
if len(CLASSES) != _n_out:
    raise RuntimeError(
        f"Class list has {len(CLASSES)} entries but the model emits {_n_out} "
        f"logits. Refusing to serve mislabelled predictions."
    )
```

This catches a count mismatch, not an order mismatch — so pair it with the
verification below, which catches order.

### Verify

```bash
ai/.venv/Scripts/python.exe -c "
import json,os,numpy as np,onnxruntime as ort
from PIL import Image
C=json.load(open('classes.json')); print('classes:',C)
s=ort.InferenceSession('kisannetra_fp32.onnx',providers=['CPUExecutionProvider']); n=s.get_inputs()[0].name
mean=np.array([0.485,0.456,0.406],np.float32); std=np.array([0.229,0.224,0.225],np.float32)
def prep(p):
    im=Image.open(p).convert('RGB'); w,h=im.size; sc=256/min(w,h)
    im=im.resize((round(w*sc),round(h*sc)),Image.BILINEAR); w,h=im.size
    l,t=(w-224)//2,(h-224)//2; im=im.crop((l,t,l+224,t+224))
    return ((np.asarray(im,np.float32)/255.0-mean)/std).transpose(2,0,1)[None]
for cls in C:
    d=os.path.join('dataset_split/test',cls); fs=sorted(os.listdir(d))[:20]
    hit=sum(C[int(np.argmax(s.run(None,{n:prep(os.path.join(d,f))})[0][0]))]==cls for f in fs)
    print('{:<18} {}/20 correct'.format(cls,hit))
"
```

**Pass condition:** every class scores well above 4/20 (chance). Before the fix,
Healthy and Tungro both score near zero while the others are fine — that
asymmetry is the swap's signature.

---

## Fix 2 — The chance-level INT8 model is still shippable *(CRITICAL)*

The engineering judgement in `step5_export.py` is already right. Only the
artifact and the record need to change.

### 2a. Take the broken file out of reach

```bash
mv kisannetra_int8.onnx kisannetra_int8.BROKEN_22pct.onnx
```

Renaming beats deleting: the name now carries the finding, and nobody can point
a demo at it by accident or rediscover the same dead end in three weeks.

### 2b. Record Step 5 honestly in `PS-26180-MASTER.md`

Set the status to `DONE` and fill the result with what actually happened:

```
- Result (FP32 size / INT8 size / accuracy delta):
  - FP32 ONNX: 5.82 MB — THE DEPLOYMENT MODEL. 87.70% test accuracy.
  - INT8: attempted via five onnxruntime schemes. All produced 22–36%
    accuracy against a 20% chance baseline — no usable signal.
  - Measured independently during audit: 22.0% on a balanced 150-image
    sample, versus 74.0% for FP32 on the same sample.
  - ROOT CAUSE: every onnxruntime path inserts QuantizeLinear /
    DequantizeLinear on activation tensors; MobileNetV3's HardSwish outputs
    are clipped by the quantization range and the representation collapses.
  - The broken artifact is retained as kisannetra_int8.BROKEN_22pct.onnx so
    the dead end is not silently repeated. It is NOT a deliverable.
  - SOFTWARE-ONLY VALIDATION. No Qualcomm, Hexagon or NPU execution was
    involved in any figure above.
```

Tick the first four boxes and the software-only label. **Leave "Reported to
human and received go-ahead" unticked** until that actually happens — see
Fix 6.

### 2c. Say it out loud in the demo

This is a strength, not an embarrassment. "We tried five quantization paths, all
collapsed, and here is the architectural reason" is a better answer than a size
number. The honest follow-up: a HardSwish-aware quantizer, or swapping the
activation to ReLU and retraining, is the real path to INT8 — and neither was in
tonight's budget.

### Verify

```bash
ls kisannetra_int8*.onnx     # only the BROKEN-named file should exist
grep -c "SOFTWARE-ONLY" PS-26180-MASTER.md
```

---

# PHASE B — Close the specification violations

All three are in `step6_rule_engine.py`, all in the sensor-failure path.

## Fix 3 — `UnboundLocalError` when the pH sensor fails *(CRITICAL)*

In `evaluate_nutrients`, initialise before the branch:

```python
alerts = []
status = sensor.get("sensor_status", {})
ph = None                      # bound before use; the zinc rule reads it below
```

Then guard the zinc rule:

```python
# Zinc — NEVER claim 'sensor detected zinc'; use agronomic prior
zinc_risk = (n is not None and n > N_HIGH) or (ph is not None and ph > 7.2)
if zinc_risk:
    alerts.append({...})
```

## Fix 4 — Missing nutrient sensors become `0` and trigger prescriptions *(CRITICAL)*

Replace the four silent defaults with `None` and gate every rule. The pattern
the pH rule already uses is the correct one — extend it:

```python
def _reading(sensor, key, status_key=None):
    """A reading, or None. Never a substituted value.

    Section 4: 'Never replace a missing/failed sensor value with zero or a
    guess.' A missing value is a fault to be reported, not a number to reason
    with — 0 mg/kg nitrogen reads as a severe deficiency and generates a
    fertiliser prescription from an absent wire.
    """
    if sensor.get(key) is None:
        return None
    st = sensor.get("sensor_status", {}).get(status_key or key, "UNKNOWN")
    return sensor[key] if st in ("VALID", "STALE") else None
```

Then each nutrient rule becomes:

```python
n = _reading(sensor, "soil_n", "soil_npk")
if n is None:
    alerts.append({"nutrient": "N", "level": "UNKNOWN",
                   "message": "Soil N reading unavailable — MANUAL CHECK RECOMMENDED. "
                              "No fertiliser recommendation is made without a reading.",
                   "confidence": "NONE"})
elif n < N_LOW:
    ...
```

Repeat for P, K and EC. **The rule to hold onto: no reading, no prescription.**

Add the matching status keys to the Section 6 contract — `soil_npk` for the
7-in-1 device's nutrient channels, `soil_ec` per Fix 13.

## Fix 12 — Irrigation's invented defaults *(MEDIUM, same edit)*

```python
tank = sensor.get("tank_level", 100)     # -> _reading(sensor, "tank_level")
surf = sensor.get("surface_moisture", 100)
root = sensor.get("root_moisture", 100)
```

A missing tank level defaulting to 100% full is the most dangerous assumption
available to a pump-safety gate. Route all three through `_reading` and treat
`None` as blocking for tank, confidence-reducing for the moisture probes.

### Verify Phase B

```bash
ai/.venv/Scripts/python.exe -c "
import step6_rule_engine as R
base={'timestamp':'t','soil_ph':6.4,'soil_ec':1.2,'soil_n':40,'soil_p':18,'soil_k':35,
 'surface_moisture':30,'root_moisture':20,'tank_level':70,'humidity':60,
 'air_temperature':30,'light_lux':900,'rain':False,'flow_lpm':0,
 'sensor_status':{'soil_ph':'VALID','surface_moisture':'VALID','root_moisture':'VALID','tank_level':'VALID'}}
s=dict(base); s['sensor_status']=dict(base['sensor_status'],soil_ph='FAILED')
print('pH FAILED ->', [a['level'] for a in R.evaluate_nutrients(s)])
s2=dict(base); del s2['soil_n']; del s2['soil_p']
print('N/P absent ->', [(a['nutrient'],a['level']) for a in R.evaluate_nutrients(s2) if a['nutrient'] in ('N','P')])
s3=dict(base); del s3['tank_level']
print('tank absent ->', R.evaluate_irrigation(s3)['blocked'])
"
```

**Pass conditions:** no exception; N and P report `UNKNOWN` rather than `LOW`;
no message contains "apply"; missing tank blocks irrigation.

---

# PHASE C — Make these bugs catchable without an audit

## Fix 11 — The mock generator can only emit `VALID` *(MEDIUM)*

This is the highest-leverage fix in the document. Findings 3 and 4 survived
because no demo could reach the branches they live in.

`sensor_contract.py`:

```python
VALIDITY = ("VALID", "STALE", "FAILED", "UNKNOWN")

@staticmethod
def generate_mock_reading(faults=None, drop=None):
    """faults: {'soil_ph': 'FAILED'} forces a status.
       drop:   ['soil_n'] removes the key entirely, as a dead bus would.

    The contract defines four validity states; a generator that can only emit
    VALID makes three-quarters of the contract untestable, and the failure
    path is the behaviour that distinguishes this system from a dashboard.
    """
    faults = faults or {}
    reading = {...}
    reading["sensor_status"].update(faults)
    for key in (drop or []):
        reading.pop(key, None)
    return reading
```

Then add to `step8_integration_test.py`:

| Case | Expected |
|---|---|
| `faults={'soil_ph':'FAILED'}` | no exception; pH alert `UNKNOWN`, confidence `NONE` |
| `drop=['soil_n','soil_p']` | N and P `UNKNOWN`; **no message containing "apply"** |
| `faults={'tank_level':'FAILED'}` | irrigation `blocked=True` |
| `faults={'root_moisture':'STALE'}` | decision proceeds, confidence reduced |
| every class in `classes.json` | round-trips through the server with its own name |

The "apply" assertion is worth stating plainly: **no test should ever allow a
fertiliser recommendation derived from an absent reading.**

---

# PHASE D — Restore the honesty of the record

## Fix 6 — Stale trackers and unreviewed checkpoints *(HIGH)*

1. Update `PS-26180-MASTER.md` statuses to match disk: Steps 5, 6, 7 and 8 all
   have artifacts. Fill each `Result` from what the scripts actually produce.
2. Add a line to each checkpoint that was passed without review, in the file's
   own vocabulary:

   ```
   - Notes: CHECKPOINT PASSED WITHOUT REVIEW. Step 5 was executed and Steps 6–8
     were built on top of it while this entry still read TODO. Flagged rather
     than back-dated.
   ```
3. Untick Step 4's "Reported to human and received go-ahead" — that confirmation
   is not in the session record.
4. Retire `BUILD_LOG.md`, or generate it from the master file. Two
   hand-maintained trackers always drift, and they already have.

## Fix 10 — The lab-vs-field gap explanation *(MEDIUM)*

Replace the Step 4 note with the actual cause:

```
- Notes:
  - Field accuracy (88.79%) EXCEEDS lab accuracy (77.78%). The direction is the
    reverse of the usual lab-to-field drop, and the cause is the training
    composition, not model robustness: training was ~4,185 field images against
    ~436 lab, roughly 90/10. The model is better on field data because field
    data is nearly all it saw.
  - The lab test set is 99 images, so 77.78% carries roughly +/-8 points at 95%
    confidence. It should not be quoted to two decimal places.
  - Healthy is field-only — no lab figure exists; expected, not an error.
  - Brown Spot's lab metric is the least reliable of the four (90 lab images).
```

Stated as it was, the result reads as *"our model handles hard field conditions
better than clean lab conditions"* — which inverts the project's own argument
about out-of-distribution vision. One follow-up question from a judge finds the
training split. Say it first.

## Fix 5 — Near-duplicate deduplication *(HIGH)*

Two honest options.

**Option A — implement it (~30 minutes).** Add a perceptual hash pass to
`step2_clean_split.py`, cluster by Hamming distance, and split by cluster so
every member lands in one split:

```python
def dhash(path, size=8):
    """64-bit difference hash. Near-identical frames collide; unrelated
    images do not. Catches what MD5 cannot: the same leaf photographed twice."""
    im = Image.open(path).convert("L").resize((size + 1, size), Image.BILINEAR)
    px = np.asarray(im, dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)
```

Union-find over pairs with Hamming distance ≤ 5, then assign whole clusters to
train/val/test. **Then re-run Steps 3 and 4** — the accuracy number changes and
the old one cannot be quoted afterwards.

**Option B — amend the claim (2 minutes).** Untick "near-duplicate" in Step 2,
state exact-MD5-only in the result, and record the leakage risk as known and
unquantified.

Option B is legitimate under time pressure. What is not legitimate is leaving
the box ticked. This matters here specifically because Paddy Doctor images are
captured in sessions — several frames of one plant, seconds apart, not
byte-identical — which is exactly the leakage MD5 cannot see.

---

# PHASE E — Make the trend layer mean something

## Fix 7 — The generator has no temporal structure *(HIGH)*

Give `SensorDataGenerator` state and make it a bounded random walk:

```python
class SensorDataGenerator:
    """Stateful. Successive readings must be correlated, or the rate-of-change
    layer downstream is computing the slope of noise and the early-warning
    figure means nothing."""

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.state = {"surface_moisture": 32.0, "root_moisture": 24.0, ...}
        self.drift = {"surface_moisture": -0.45, "root_moisture": -0.25, ...}

    def step(self):
        for k, v in self.state.items():
            v += self.drift[k] + self.rng.gauss(0, self.noise[k])
            self.state[k] = max(self.floor[k], min(self.ceil[k], v))
        if self.raining:
            self.state["surface_moisture"] += 6.0   # recharge, then resume drying
```

Moisture should decline between rainfall events and jump on rain. Then the
existing rate-of-change code becomes meaningful without changing a line of it.

Keep a `generate_mock_reading()` shim so nothing downstream breaks, and keep the
`seed` parameter — a reproducible demo is worth more than a random one.

## Fix 8 — Negative time-to-threshold *(HIGH)*

```python
def _trend_warning(key, value, label, threshold):
    roc = _rate_of_change(_history[key])
    if roc is None or roc >= 0:
        return None
    if value <= threshold:        # already breached; not a forecast
        return None
    steps = max(0, int((value - threshold) / -roc))
    return f"EARLY WARNING ({label} trending down, ~{steps} readings to threshold)"
```

Three corrections: only forecast from the safe side of the threshold, divide by
`-roc` so the sign is right, and clamp at zero.

**Only call the result an early warning once Fix 7 lands.** Until the input has
temporal structure, this is a threshold alert wearing a prediction's label —
which Section 3 of the specification prohibits by name.

---

# PHASE F — Finish the edges

## Fix 9 — Brown Spot and Tungro can never reach HIGH *(MEDIUM)*

Empty dictionaries fall back to `humidity_thresh = 999`, which is unreachable,
so those two classes are silently capped at MEDIUM forever. Make the intent
explicit:

```python
HIGH_RISK_DISEASES = {
    "Bacterial Blight": {"humidity_thresh": 80, "temp_range": (25, 35)},
    "Blast":            {"humidity_thresh": 85, "temp_range": (24, 32)},
    # Brown spot tracks nutrient and water stress, not humidity — and this node
    # measures both, so it corroborates on soil rather than air.
    "Brown Spot":       {"corroborator": "soil_stress"},
    # Tungro is insect-vectored. No sensor on this node observes leafhopper
    # pressure, so there is no corroborator and HIGH is unreachable BY DESIGN.
    "Tungro":           {"corroborator": None, "max_risk": "MEDIUM"},
}
```

Then implement `soil_stress` corroboration for brown spot (low N or low root
moisture), and have `fuse_disease` state the reason when a class is capped:
*"Tungro risk capped at MEDIUM — no environmental corroborator available on
this node."* A cap the operator can see is a design decision; a cap they cannot
is a bug.

## Fix 13 — EC gated on the pH status key *(LOW)*

Add `soil_ec` to the contract's `sensor_status`, and gate EC on its own key.
The devices share a bus, but partial failures are real and the coupling is
invisible in the output today.

## Fix 14 — Deprecated `datetime.utcnow()` *(LOW)*

```python
from datetime import datetime, timezone
"timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
```

The current code appends `"Z"` to a naive datetime, asserting UTC without
carrying it.

## Fix 15 — Orphaned export artifacts *(LOW)*

Confirm `kisannetra_fp32.onnx.data` is unreferenced (`kisannetra_fp32.onnx`
loads standalone, so it almost certainly is), then delete it. Establish what
`kisannetra_preproc.onnx` is for — if it is the preprocessing-embedded variant,
name it so; if it is superseded, delete it. Roughly 12 MB of ambiguity in a
directory where somebody has to pick the right file under demo pressure.

---

# Definition of done

Phase A and B are the bar for showing this to anyone.

- [ ] `classes.json` exists and is the only class-order source
- [ ] Per-class verification passes for all five classes
- [ ] No file named `kisannetra_int8.onnx` without `BROKEN` in it
- [ ] Step 5 recorded with the INT8 failure, its cause, and the software-only label
- [ ] `evaluate_nutrients` survives every validity state on every channel
- [ ] No fertiliser recommendation is reachable from an absent reading
- [ ] Missing tank level blocks irrigation
- [ ] Fault injection exists and the Step 8 harness exercises it
- [ ] Master file matches disk; unreviewed checkpoints marked as such
- [ ] Step 4's gap note states the training-composition cause
- [ ] Near-duplicate dedup implemented, or the claim withdrawn
- [ ] "Early warning" only claimed once the generator has temporal structure

---

# One structural note

Findings 1, 3, 4 and 12 share a single root cause: **a default standing in for a
value that was never checked.** A hardcoded class list standing in for the
trained order. `0` standing in for a missing nutrient reading. `100` standing in
for an unknown tank level.

The specification names this exactly once, in Section 4 — *"never replace a
missing/failed sensor value with zero or a guess"* — and the code follows it
carefully in the pH rule and the zinc rule while breaking it four lines away.
The rule is right. It just needs to be applied to every channel, and enforced by
a test rather than by attention.
