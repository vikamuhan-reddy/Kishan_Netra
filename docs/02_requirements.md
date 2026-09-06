# 02 — Requirements

Translation of SIH PS 26180 into engineering requirements, with priority and a concrete
acceptance test for each.

**Priority definitions**

- **MUST** — the project fails its own pitch without this
- **SHOULD** — build it, but simply; do not let it consume the MUSTs
- **DEFER** — architected and explained, not implemented this round
- **OUT** — explicitly not attempted; stated openly to judges

**Acceptance test rule:** a requirement is not "done" because code exists. It is done
when the named test passes or the named measurement has been recorded. Requirements
whose acceptance test is a measurement we have not taken are marked ⏳, not ✅.

---

## 1. Crop health monitoring (PS section 1)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D1 — detect disease from leaf images | Vision model emits a **ranked differential** over cotton hypotheses, not an argmax label. Emitting a distribution is what makes fusion possible. | Edge (NPU) | **MUST** | Held-out-*condition* accuracy reported alongside random-split accuracy, with the gap explained | ⬜ |
| D2 — identify nutrient deficiency | Nitrogen deficiency included as a hypothesis in the same differential; resolved by *excluding* water stress using soil moisture | Edge | **MUST** | `test_identical_image_yields_different_action_per_field` | ✅ |
| D3 — monitor growth stage and field health | Growth stage as fusion context; field health as an aggregate of recent diagnoses | Edge | **DEFER** | — | ⬜ |

**Note on D2.** We cannot measure soil nitrogen with a moisture/temp/humidity probe and
we do not pretend to. What the system can legitimately say is that chlorosis under
adequate, stable moisture is *not explained by water* — which is precisely the
distinction that decides whether the farmer buys fertilizer or turns on a pump.

---

## 2. Pest detection (PS section 2)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D4 — camera-based pest detection | Object detection model (YOLOv8n class) producing counts and locations | Edge (NPU) | **DEFER** | — | ⬜ |
| D5 — early alert before spread | Infestation trend across successive captures crossing a density threshold | Edge | **DEFER** | — | ⬜ |
| D6 — targeted rather than blanket intervention | **Partially met by the fusion engine already.** Correct cause attribution *is* targeted intervention: not spraying for a disease that is actually thirst. | Edge | **MUST** | `test_sensors_overturn_the_camera_when_they_should` | ✅ |

**Why pest detection is deferred.** It needs a second model, an annotated detection
dataset, and its own quantization and profiling pass. In 12 days that comes directly
out of the three MUST capabilities. The architecture reserves the slot: a pest detector
emits into the same `VisionDifferential` contract and the fusion engine consumes it
unchanged.

D6 is retained as a MUST because it is achievable *without* the pest model, through
correct attribution.

---

## 3. Smart irrigation (PS section 3)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D7 — monitor moisture, temp, humidity, weather | `SensorWindow` contract with derived features: current value, least-squares trend, peak temperature, mean humidity, hours since irrigation | Edge | **MUST** | `test_drying_scenario_actually_dries`, `test_simulator_is_deterministic` | ✅ |
| D8 — detect water stress **and over-irrigation** | Water stress from low/falling moisture. Over-irrigation via the waterlogged threshold, which also raises bacterial blight likelihood. | Edge | **MUST** | `test_identical_image_yields_different_action_per_field`; waterlogged path exercised by the `waterlogged` scenario | ✅ |
| D9 — recommend irrigation schedule | Advisory strings driven by moisture state and trend | Edge | **SHOULD** | Demo produces "irrigate" vs "delay" correctly for the two scenarios | ⬜ |

**A single reading cannot do this.** "Dry because it was never watered" and "dry because
it is mid-afternoon" look identical in a snapshot. The trend carries the information,
which is why the window — not the reading — is the contract.

---

## 4. Environmental risk (PS section 4)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D10 — track drought/flood/heat/disease conditions | Threshold and trend rules over the sensor window: heat stress, waterlogging, sustained high humidity as a blight-favourable window | Edge | **SHOULD** | Humid-spell scenario raises bacterial blight likelihood | ⬜ |
| D11 — identify abnormal patterns | Statistical anomaly detection against the rolling window | Edge | **SHOULD** | — | ⬜ |
| D12 — field-level localized alerts | Alerts carry the field/device identity | Edge | **SHOULD** | — | ⬜ |

**Explicitly rule-based, and labelled as such.** Established agronomic disease-pressure
windows are transparent, need no training data, and are defensible under questioning. A
learned predictor here would require longitudinal ground truth we do not have, and
claiming one we could not validate would be the single easiest way to lose credibility.

---

## 5. Edge AI processing (PS section 5)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D13 — process images and sensors on device | Vision model compiled to a Qualcomm target and profiled on Snapdragon silicon; fusion runs on CPU | Edge | **MUST** | SPIKE-0 records device name, latency, memory, and per-layer compute-unit split | ⏳ |
| D14 — operate under intermittent connectivity | Local inference, local alerting, local queue; reconnect reconciles | Edge | **MUST** | Network disabled mid-demo → inference and alerts continue → reconnect drains queue | ⬜ |
| D15 — low-latency recommendations | Measured end-to-end time from capture to advisory | Edge | **MUST** | Measured number, never asserted | ⏳ |

**D13 is the requirement the entire Qualcomm relevance rests on**, and it is the only
one we cannot satisfy with software alone. It is therefore scheduled on day 1, not
day 9. See [01_plan_12_days.md](01_plan_12_days.md) §1.

**On D15.** Latency is a weak *justification* for edge in this PS — a farmer can wait
three seconds for a photo result. The strong justifications are absent connectivity
(D14), bandwidth (a device watching a field continuously cannot stream video over a
rural link at any price), and fleet unit economics. Measure latency, but do not lead
with it.

---

## 6. Farmer advisory (PS section 6)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D16 — simple advisories | PS-verbatim advisory strings: irrigate now / delay irrigation / possible disease / pest activity increasing / heat-stress warning / flood-risk alert | Edge | **MUST** | Advisory set covers every string the PS names | ⬜ |
| D17 — deliver via app, display, or SMS | App/display this round. SMS requires a cellular path — see below. | Edge | **SHOULD** | — | ⬜ |
| — | Every recommendation carries traceable evidence | Edge | **MUST** | `test_every_recommendation_carries_traceable_evidence` | ✅ |

⚠️ **The SMS constraint nobody notices.** The RB3 Gen 2 has Wi-Fi 6E and Bluetooth 5.2
but **no onboard cellular radio** (verified 2026-09-02). SMS delivery therefore requires
an explicit backhaul decision — USB LTE dongle, LoRa to a village gateway, or
store-and-forward over intermittent Wi-Fi. Most teams will draw a cloud arrow and never
notice. Naming and solving this is cheap credibility.

**Recommendations are advisory only.** No automatic actuation of pumps or sprayers from
a single prediction. See [decision_log.md](decision_log.md) DR-006.

---

## 7. Analytics dashboard (PS section 7)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D18 — historical trends | Time-series view of sensor history and past diagnoses | Cloud (optional) | **DEFER** — minimal trends view only | — | ⬜ |
| D19 — yield-risk forecasting | Risk score from accumulated stress exposure | Cloud | **DEFER** | — | ⬜ |

Judges spend little time on dashboards and it is not where this project wins. A minimal
trends view is sufficient; anything more is effort taken from the MUSTs.

---

## 8. Scalable deployment (PS section 8)

| PS req | Engineering interpretation | Edge/Cloud | Priority | Acceptance test | State |
|---|---|---|---|---|---|
| D20 — smallholder → cooperative → enterprise | Per-tier cost model; shared-device model for smallholders via cooperatives | — | **DEFER** — architecture and cost slide only | — | ⬜ |
| D21 — integrate weather, equipment, irrigation | Documented integration interfaces | — | **DEFER** — architecture slide only | — | ⬜ |

**Unit economics note for D20.** A $399–599 device is not affordable per smallholder
plot. The credible deployment model is one device per cooperative or per cluster of
plots, which is also why cotton (higher value per acre than rice) makes the economics
easier to defend.

---

## Summary

| Priority | Count | Requirements |
|---|---|---|
| **MUST** | 9 | D1, D2, D6, D7, D8, D13, D14, D15, D16, + explainability |
| **SHOULD** | 7 | D9, D10, D11, D12, D17 |
| **DEFER** | 8 | D3, D4, D5, D18, D19, D20, D21 |

Currently satisfied with a passing test: **5**. Blocked on SPIKE-0: **2**. Remaining
build work: the rest.
