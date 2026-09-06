# 03 — Use Case Prioritization

Scored comparison of the four candidate use cases named in the master prompt, plus the
composite we actually selected.

**Scoring:** 1 (poor) to 5 (excellent) on every axis **except deployment risk**, where
1 is low risk and 5 is high risk. Scores are internal engineering estimates, not any
official SIH or Qualcomm rubric.

---

## Scores

| Axis | UC1 Disease vision | UC2 Pest detection | UC3 Water stress | UC4 Environmental risk | **UC5 Composite (UC1 ⊕ UC3)** |
|---|:--:|:--:|:--:|:--:|:--:|
| PS alignment | 5 | 5 | 5 | 4 | **5** |
| User value | 4 | 5 | 5 | 4 | **5** |
| Qualcomm relevance | 5 | 5 | 2 | 1 | **5** |
| Technical depth | 3 | 4 | 2 | 2 | **5** |
| Novelty | 1 | 2 | 1 | 1 | **4** |
| Feasibility in 12 days | 4 | 2 | 5 | 4 | **4** |
| Demo impact | 3 | 4 | 3 | 2 | **5** |
| Data availability | 4 | 2 | 5 | 3 | **4** |
| Deployment risk *(lower better)* | 3 | 4 | 2 | 2 | **3** |
| **Total (risk inverted)** | **31** | **31** | **30** | **25** | **40** |

---

## The finding that drove the decision

**Every individual use case scores 1 or 2 on novelty.** Crop disease classification has
hundreds of public implementations. Threshold-based irrigation is a first-year IoT
project. Environmental rule engines are decades old. Any one of them, built well, is
still a project a judge has seen before.

**The composite scores 4** — not because we invented a new technique, but because the
combination resolves a problem neither half can solve alone:

> Vision cannot separate nitrogen deficiency from water stress, because a single RGB
> frame does not contain the information. Sensors cannot identify a disease, because a
> moisture probe cannot see a lesion. Together they resolve an ambiguity that is
> genuinely unresolvable by either.

This is **differentiated engineering**, not algorithmic novelty, and we will describe it
as exactly that. Claiming a novel algorithm here would not survive questioning.

---

## Per use case

### UC1 — Crop disease detection from images

**Verdict: PROCEED, as an input to UC5 rather than an endpoint.**

Strong on PS alignment (D1 verbatim) and Qualcomm relevance — the vision model is the
NPU workload that justifies the silicon. Weak on novelty and technical depth *in
isolation*: fine-tuning a MobileNet on a leaf dataset is a solved exercise.

The change that makes it valuable is architectural: **emit a ranked differential, not an
argmax label.** An argmax discards exactly the information the fusion layer needs. This
costs nothing at inference time and is the enabling decision for the whole system.

Main risk is dataset domain gap — see `00_initial_technical_assessment.md` §4. Data
availability scores 4 rather than 5 only because the field-realistic Indian cotton
datasets still need their access and licence verified.

### UC2 — Pest detection

**Verdict: DEFER, architect the slot.**

Scores identically to UC1 in total, and on user value it is the strongest of all four —
blanket pesticide spraying in Indian cotton is a documented national problem and the PS
calls it out directly (D6).

It is deferred purely on **feasibility (2)** and **data availability (2)**: a second
model, an annotated detection dataset, and its own quantization and profiling pass, all
inside 12 days, taken directly out of the three MUST capabilities.

The architecture reserves the slot — a pest detector emits into the same
`VisionDifferential` contract and the fusion engine consumes it unchanged. Deployment
risk is the highest of the four (4): small objects, camera placement, and focus depth
are genuinely hard in-field.

**We satisfy D6 without the pest model**, through correct cause attribution: not
spraying for a disease that is actually thirst *is* targeted intervention.

### UC3 — Water stress and irrigation intelligence

**Verdict: PROCEED, as the disambiguating signal in UC5.**

Highest feasibility and data availability of the four, and high user value — water is
the binding constraint for the target user.

But note the honest score: **Qualcomm relevance 2.** Threshold logic over a moisture
probe does not need a 12-TOPS NPU, and presenting it as though it does would be exactly
the kind of unearned claim that loses credibility. Its value here is not that it is
computationally demanding. Its value is that **it carries the information vision
lacks.**

### UC4 — Environmental risk monitoring

**Verdict: ADOPT as a bounded rule-based layer. Do not present it as ML.**

Lowest total (25) and lowest Qualcomm relevance (1). Retained because the PS asks for it
(D10–D12) and because it is cheap: established agronomic disease-pressure windows are
transparent, need no training data, and answer questions well.

Explicitly **not** a learned predictor. Validating a yield or outbreak forecast requires
longitudinal ground truth we do not have, and claiming a model we could not validate is
the easiest available way to lose a judging round.

### UC5 — Composite: corroborated diagnosis

**Verdict: PROCEED. This is the project.**

Scores highest on every axis that differentiates (technical depth 5, novelty 4, demo
impact 5) while remaining feasible (4), because both halves were already being built.

The demo is thirty seconds and cannot be reproduced by any classifier:

> Identical vision output. Two field histories. Two different recommended actions —
> one costing money on fertilizer, the other on water. Getting it backwards harms the
> crop *and* wastes the input.

Implemented in [`iot/fusion/engine.py`](../iot/fusion/engine.py); documented in
[09_sensor_fusion.md](09_sensor_fusion.md); locked by
[`tests/test_fusion.py`](../tests/test_fusion.py).

---

## Resulting build order

| Rank | Use case | Priority |
|---|---|---|
| 1 | UC5 composite — fusion and explanation | **MUST** ✅ built |
| 2 | UC1 vision differential | **MUST** ⬜ |
| 3 | UC3 sensor window and irrigation advisory | **MUST** ✅ built |
| 4 | UC4 environmental rules | **SHOULD** ⬜ |
| 5 | UC2 pest detection | **DEFER** — slot reserved |
