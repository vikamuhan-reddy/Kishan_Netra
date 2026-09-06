# 09 — Sensor Fusion

Design and behaviour of [`iot/fusion/engine.py`](../iot/fusion/engine.py).

**Status: built, tested, running.** Every example in this document is real output from
`python -m demo.differential_demo`, not an illustration.

---

## 1. Why fusion exists here

The standard justification for sensor fusion — "combining modalities improves accuracy"
— is weak and judges know it. Ours is stronger and more specific:

> Cotton leaf chlorosis and reddening present similarly whether the cause is water
> stress, nitrogen deficiency, or a viral infection. **A single RGB frame does not
> contain the information required to separate them.** This is an information limit,
> not a modelling weakness — a larger vision model does not fix it. A three-day
> soil-moisture trend does.

So fusion here is not an accuracy optimization. It is **the mechanism that makes the
diagnosis possible at all**, which is why the system is architected around it rather
than adding it as a post-processing step.

The consequence is economic, which is how it should be presented to judges: the two
candidate causes lead to *opposite* interventions. Irrigating a nitrogen-deficient plant
wastes water. Fertilizing a water-stressed plant makes the stress worse and wastes the
input. The farmer pays twice — once for the wrong input, once for the untreated problem.

---

## 2. Fusion option selected

The master prompt asks for an explicit comparison of four options.

| Option | Assessment | Verdict |
|---|---|---|
| **A — Rule-based** | Transparent and cheap, but cannot express "vision thinks X, sensors make X unlikely" as a degree. Collapses to a decision tree that ignores vision confidence. | Rejected |
| **B — Feature-level fusion** | Concatenate image embeddings with sensor features, train one model. Highest ceiling, but needs paired image+sensor training data that **does not exist** for Indian cotton. Would have to be fabricated, which is not evidence. | Rejected — no data |
| **C — Decision-level fusion** | Vision emits a distribution; sensor likelihoods reweight it. Needs no paired training data, is explainable term by term, and degrades gracefully. | **SELECTED** |
| **D — Temporal fusion** | Sequence models over sensor history. The trend information is real and necessary, but a learned temporal model needs longitudinal ground truth we do not have. | Partially adopted — trend as a *derived feature*, not a learned model |

**Selected: C, with D's trend features computed explicitly.**

This is the simplest approach that creates real value, which is the stated selection
criterion. It is also the only one honest about our data situation: option B is the
textbook answer and we cannot support it with evidence, so we do not claim it.

---

## 3. How it works

```
VisionDifferential                    SensorWindow
{nitrogen: 0.41,                      72h of readings
 water_stress: 0.37,      ────┐   ┌──── derived: current moisture,
 leaf_curl: 0.13, ...}        │   │     trend %/day, peak temp,
                              ▼   ▼     mean humidity, hours since irrigation
                    ┌─────────────────────┐
                    │  per-hypothesis     │
                    │  agronomic          │  each returns (multiplier, evidence[])
                    │  likelihood         │
                    └──────────┬──────────┘
                               │
                    degraded?  │  pull multipliers toward 1.0
                               ▼
                    posterior = prior × multiplier, normalized
                               │
                               ▼
                    margin < threshold?  ──► needs_human_review
                               │
                               ▼
                    Diagnosis + Evidence + Action
```

### Key design decisions

**Vision emits a distribution, not a label.** An argmax discards exactly the information
fusion needs. `VisionDifferential` validates that scores sum to 1.0 and rejects anything
else — a contract violation is a bug, not a warning.

**Every multiplier carries its reason.** A likelihood function returns
`(factor, list[Evidence])`, and each `Evidence` names the signal, the observation, the
hypothesis it moved, and the direction. It is structurally impossible to produce a
recommendation this system cannot explain.

**Nitrogen deficiency is diagnosed by exclusion, and says so.** We cannot measure soil
nitrogen with a moisture/temperature/humidity probe. What the engine asserts is narrower
and defensible: *chlorosis under adequate, stable moisture is not explained by water.*
The docstring in the code states this limitation explicitly so nobody later mistakes it
for a nitrogen sensor.

---

## 4. Agronomic thresholds

Defaults in `FusionConfig`, for cotton on medium-textured soil:

| Parameter | Default | Basis |
|---|---|---|
| `moisture_stress_pct` | 20% | Below this, cotton shows water stress on medium soil |
| `moisture_adequate_pct` | 28% | Above this, water is not the limiting factor |
| `moisture_waterlogged_pct` | 45% | Saturation; prolongs leaf wetness, favours bacterial spread |
| `drying_trend_pct_per_day` | −3.0 | More negative counts as actively drying |
| `heat_stress_c` | 38°C | Cotton heat stress onset |
| `blight_humidity_pct` | 80% | Sustained humidity favourable to bacterial blight |
| `whitefly_favourable_temp_c` | 30°C | Whitefly (leaf curl vector) activity |
| `min_decision_margin` | 0.15 | Below this post-fusion margin, decline to commit |
| `max_dropout_ratio` | 0.30 | Above this, distrust the sensor layer |
| `degraded_influence` | 0.25 | How far a degraded window may move the prior |

⚠️ **These are starting points from general agronomy, not calibrated field constants.**
They are stated as tunable configuration, and no field-accuracy claim may be made until
they are validated against local conditions. Saying this openly is the correct posture;
presenting them as validated would not survive an agronomist in the room.

---

## 5. Worked examples — real output

The vision differential below is **byte-identical in all three cases**. Only the sensor
history changes.

```
nitrogen_deficiency    41%
water_stress           37%
leaf_curl_virus        13%
bacterial_blight        6%
healthy                 3%
```

Note the top-two margin: **4 points.** The camera is genuinely unsure.

### Case A — `drying_down`

```
soil moisture now : 21%          moisture trend : -4.5 %/day
peak temperature  : 43 C         mean humidity  : 42%

camera alone       : nitrogen_deficiency (41%)
after fusion       : water_stress (67%)
ACTION             : irrigate
>>> sensors overturned the camera's conclusion

why
  [+] moisture trend: falling 4.5%/day              supports water_stress
  [+] irrigation history: 120h since last           supports water_stress
  [+] peak temperature: 43C (above 38C threshold)   supports water_stress
```

### Case B — `well_watered`

```
soil moisture now : 32%          moisture trend : -0.6 %/day
peak temperature  : 37 C         mean humidity  : 55%

camera alone       : nitrogen_deficiency (41%)
after fusion       : nitrogen_deficiency (71%)
ACTION             : soil test, then nitrogen application

why
  [+] soil moisture: 32% adequate, not water-driven    supports nitrogen_deficiency
  [+] moisture trend: stable (-0.6%/day)               supports nitrogen_deficiency
```

**This pair is the entire pitch.** Same image, opposite advice, each traceable to a
measurement. A classifier gives both farmers Case B's answer.

Note also that in Case B fusion did *not* overturn the camera — it **sharpened** a 41%
call into an actionable 71%. Fusion that only ever contradicts vision would be
suspicious; this one agrees when the evidence agrees.

### Case C — `failing_sensor` (44% dropout)

```
soil moisture now : 14%          reading dropout : 44%

after fusion       : water_stress (59%)
[!] sensor window 44% incomplete - sensor influence reduced to 25%
```

Reached the same conclusion as Case A but at **59% rather than 67%** confidence, and
said why. A half-dead probe must not speak more confidently than a working one — this
is asserted by `test_degraded_sensors_reduce_their_own_influence`.

---

## 6. Uncertainty and refusal to commit

Two independent guards:

1. **Degraded input** — above `max_dropout_ratio` incomplete readings, every multiplier
   is pulled toward 1.0 by `degraded_influence`, so a failing sensor cannot manufacture
   a confident diagnosis.
2. **Insufficient margin** — if the post-fusion top-two gap is below
   `min_decision_margin`, the diagnosis is flagged `needs_human_review` and the
   recommended action becomes *"inspect manually — evidence is not conclusive"*.

There is also a defensive path for total sensor contradiction: if every hypothesis is
driven to zero, the engine falls back to the vision prior and records that it did,
rather than dividing by zero or inventing a result.

**Refusing to answer is a feature.** For a farmer acting on a recommendation with real
money, a confident wrong answer is worse than an honest "inspect this yourself."

---

## 7. Honest limitations

State these before a judge finds them:

1. **Thresholds are uncalibrated.** General agronomy, not field-validated for a specific
   region, soil type, or cotton variety.
2. **Not a nitrogen sensor.** Nitrogen deficiency is inferred by excluding water stress,
   not measured.
3. **Multipliers are hand-set, not learned.** They encode agronomic reasoning; they were
   not fitted to data, because the paired image+sensor dataset does not exist.
4. **Single-plant scope.** The engine reasons over one differential and one sensor
   window; spatial spread across a field is not modelled.
5. **No pest hypothesis yet.** The contract supports it; the model is deferred.

Limitation 3 is the one most likely to be challenged. The answer is that hand-set
agronomic weights are *appropriate* when the alternative is fitting weights to data we
would have had to fabricate — and that the architecture accepts learned weights without
modification once real paired data exists.

---

## 8. Cost

Runs on CPU in well under a millisecond. The expensive part of the pipeline is the
vision model on the NPU. Fusion is deliberately cheap and deliberately transparent,
because a farmer-facing recommendation that cannot be explained should not be shown.
