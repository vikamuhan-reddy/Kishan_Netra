# 00 — Initial Technical Assessment

**Problem Statement:** SIH PS 26180 — Smart Farming Assistant (Edge AI)
**Organization:** Qualcomm Inc | **Category:** Hardware | **Theme:** Agriculture, FoodTech & Rural Development
**Assessment date:** 2026-09-02
**Status:** Pre-implementation. No code written. No claims measured.

**Evidence labels used throughout:**
`DIRECT` = explicit in PS · `INFERRED` = engineering inference · `RECOMMENDED` = our design choice · `EXTERNAL` = verified from outside source (link + date)

---

## 1. Exact PS interpretation

### 1.1 What the PS explicitly requires (DIRECT)

| # | Requirement | PS wording anchor |
|---|---|---|
| D1 | Detect crop disease from leaf/plant images | "Detect visible signs of crop diseases from leaf and plant images" |
| D2 | Identify nutrient deficiency via colour/texture/growth | "Identify nutrient deficiencies through color, texture, and growth analysis" |
| D3 | Monitor growth stages and field health | "Monitor crop growth stages and overall field health" |
| D4 | Camera-based pest detection + infestation patterns | "Detect common insect pests and infestation patterns using camera-based AI" |
| D5 | Early alerts before infestation spreads | "Generate early alerts before infestations spread" |
| D6 | Targeted intervention, not blanket pesticide | "Support targeted intervention rather than blanket pesticide application" |
| D7 | Monitor soil moisture, temperature, humidity, weather | Section 3 |
| D8 | Detect water stress AND over-irrigation | "Detect water stress and over-irrigation scenarios" |
| D9 | Recommend irrigation schedules to conserve water | Section 3 |
| D10 | Track drought / excess rain / flood / heat stress / disease-outbreak conditions | Section 4 |
| D11 | Identify abnormal environmental patterns | Section 4 |
| D12 | Field-level localized alerts | Section 4 |
| D13 | Image + sensor processing **directly on device** | Section 5 |
| D14 | Operate under limited/intermittent connectivity | Section 5 |
| D15 | Low-latency recommendations | Section 5 |
| D16 | Simple advisories (irrigate now / delay / disease / pest / heat / flood) | Section 6 — verbatim list |
| D17 | Delivery via mobile app, local display, **or SMS** | Section 6 |
| D18 | Historical trends dashboard | Section 7 |
| D19 | Yield-risk forecasting | Section 7 |
| D20 | Scale: smallholder → cooperative → enterprise | Section 8 |
| D21 | Integrate with weather data, farm equipment, irrigation systems | Section 8 |

The PS says **"implement some or all of the following."** This is explicit permission to go deep rather than wide. We will use it.

### 1.2 Constraints and users (DIRECT)

- **Target user:** small and marginal farmers in India who "lack access to timely diagnostics and expert advice."
- **Environment:** "regions with limited internet connectivity."
- **Risk context:** droughts, erratic rainfall, floods, pest infestation, disease, heat stress, soil degradation — framed as *increasing* under climate variability.
- **Economic objectives, stated:** higher yields, lower input costs, more efficient water use, faster threat response.

### 1.3 Evaluation clues (INFERRED)

| Clue | Source in PS | Implication for us |
|---|---|---|
| **Category is `Hardware`, not Software** | PS metadata | A laptop-only demo will be scored down regardless of software quality. We need physical or hosted-device evidence. **This is the highest-leverage fact in the whole PS and is easy to miss.** |
| Qualcomm is the proposing org | PS metadata | Edge inference on Qualcomm silicon is the point, not an accessory. Cloud inference with an offline cache misses the brief. |
| "real-time on-device intelligence" appears in the title | PS title | Latency and locality must be *measured*, not asserted. |
| "before they become large-scale crop failures" | Description | Judges will look for **prediction / early warning**, not just classification of damage already visible. Most competing teams will only classify. |
| "lower input costs" + "targeted intervention rather than blanket" | D6, background | The economic argument must be quantified, even roughly. A recommendation that saves a farmer a wrong spend beats one that names a pathogen. |
| "small and marginal farmers" + SMS listed as a delivery channel | D17 | Low-literacy, low-connectivity, regional-language UX is in scope, not polish. |

---

## 2. What Qualcomm likely expects (INFERRED)

Qualcomm sponsors this to see **edge silicon justified by workload**, not branding. Expected line of questioning:

1. What executes on **CPU vs GPU vs NPU**, and why that split?
2. What is the **measured** latency, memory footprint, and model size on a Qualcomm target?
3. What does **INT8 quantization** cost in accuracy and buy in latency?
4. Why does this need to be on-device at all — what breaks if it is a cloud API?

Question 4 kills most projects. A crop disease photo is not latency-critical; a farmer can wait three seconds. So **"low latency" is a weak justification for this PS.** The defensible on-device arguments here are:

- **Connectivity** (DIRECT, D14): the farm has no reliable link. Cloud is not degraded, it is *absent*.
- **Bandwidth** (INFERRED): a device that watches a field continuously cannot stream video over a rural link at any price. Bandwidth, not latency, is the binding constraint.
- **Unit economics at fleet scale** (INFERRED): 1,000 farms of continuous monitoring is a cloud bill the smallholder economy does not support.

Lead with bandwidth, connectivity and unit economics. Treat latency as a secondary measured fact.

---

## 3. Verified Qualcomm resource map

> All rows verified 2026-09-02. Product facts change — re-verify before the final deck.

| Resource | What it does | Verified status | How we would use it | Source |
|---|---|---|---|---|
| **Qualcomm AI Hub Workbench** | Optimize, validate, deploy ML models on-device | Live. Docs moved `app.aihub.qualcomm.com/docs` → `workbench.aihub.qualcomm.com/docs` (301) | Primary compile + profile + on-device-inference path | [docs](https://workbench.aihub.qualcomm.com/docs/) |
| — input formats | PyTorch, TorchScript, ONNX, TensorFlow Lite | Confirmed in docs | Export path from training | same |
| — compile targets | Qualcomm AI Runtime (QNN APIs), TFLite, ONNX Runtime | Confirmed in docs | Target QNN for NPU | same |
| — hosted devices | "the system automatically provisions devices in the cloud for on-device profiling and inference" | Capability confirmed; **specific device list not exposed in public docs** | **Level B validation** — real latency without owning a board | same |
| — free tier | **UNVERIFIED.** Third-party sources mention a free model and $9.99/mo founding-member pricing; official docs do not state cost | ⚠️ must confirm at signup | Blocks planning if paid | [cybernews](https://cybernews.com/ai-knowledge-base/tools/qualcomm-ai-hub/) — secondary source, low trust |
| **AI Hub Models** | 300+ pre-optimized models with published performance metrics | Live | Day-one spike baseline; also a benchmark reference point | [github](https://github.com/qualcomm/ai-hub-models) |
| **Dragonwing RB3 Gen 2 Dev Kit** | QCS6490 Linux edge AI board | Live | Level C physical target | [qualcomm.com](https://www.qualcomm.com/developer/hardware/rb3-gen-2-development-kit) |

### 3.1 RB3 Gen 2 — verified specifications

| Attribute | Value | Note |
|---|---|---|
| SoC | Dragonwing QCS6490 (QCS5430 on the Lite variant) | |
| CPU / GPU / NPU | Kryo 670 / Adreno 643L / Hexagon 770, **up to 12 dense TOPS** | NPU is the AI target |
| Camera | 2× C-PHY/D-PHY 30-pin expansion; GMSL-capable ports. Vision Kit adds IMX577 12MP + OV9282 1MP | Vision Kit ships usable cameras |
| Sensor I/O | GPIO exposing SPI, UART, I2C, PCIe, USB, MIPI | ✅ soil / temp / humidity sensors attach directly |
| Connectivity | **Wi-Fi 6E + Bluetooth 5.2. No onboard cellular.** | ⚠️ see risk R4 |
| OS | Linux, Ubuntu, Android, Windows | |
| Price | Core Kit **$399**, Vision Kit **$599** (Thundercomm) | ⚠️ India import + customs + lead time — see risk R2 |

**Finding worth surfacing to judges (R4):** the board has no cellular radio. A field deployment on a low-connectivity Indian farm therefore needs an explicit backhaul decision — USB LTE dongle, LoRa to a village gateway, or store-and-forward over intermittent Wi-Fi. The PS demands SMS delivery (D17), which *requires* a cellular path somewhere in the system. Most teams will draw a cloud arrow and never notice. Naming this constraint and solving it deliberately is cheap credibility.

---

## 4. The core technical risk nobody talks about

**Crop disease classification benchmarks are contaminated.** PlantVillage — the dataset every SIH team reaches for — is roughly 54k images of *detached leaves on uniform laboratory backgrounds*. Models score 99%+ on it and then fail on a real field photo, because the model learned background and lighting, not the lesion.

If we present a 99% accuracy number from a random train/test split, a competent judge asks one question — *"what was your test split?"* — and the project is over.

**Mitigation is non-negotiable and must be visible in the deck:**

- Test on a **held-out acquisition condition**, never a random split (different field / session / camera / lighting).
- Report the **honest field-realistic number** next to the lab number, and explain the gap. A defended 78% beats an undefended 99%.
- Handle degraded input explicitly: blur, occlusion, harsh sun, dust, partial leaves.

Reporting the drop *ourselves*, before a judge finds it, converts our biggest weakness into evidence of rigour. This is the highest-value differentiator available and it costs nothing but honesty.

---

## 5. Candidate architectures

### Architecture A — "Classifier + dashboard" (the default; what most teams will build)

Camera → CNN → disease label → app. Sensors rendered as charts alongside.

**REJECT.** No fusion, no edge justification, indistinguishable from hundreds of public repositories. PS section 5 and the Hardware category are both unaddressed.

### Architecture B — "Corroborated diagnosis" (RECOMMENDED)

Vision produces a *differential* — a ranked set of hypotheses with confidence — not a label. Sensor history acts as the disambiguator. Fusion resolves the differential into one diagnosis plus an explanation naming the evidence used.

**Why this is defensible:** the real agronomic problem is that **yellowing leaves are ambiguous.** Nitrogen deficiency, water stress and several diseases look alike to a camera. Vision alone genuinely cannot separate them — this is not a modelling weakness, it is an information limit. A three-day soil-moisture trend *can*.

> Same leaf image, two sensor histories, two different recommendations:
>
> - moisture 18% and falling for 3 days, no irrigation event → **water stress → irrigate, do not fertilize**
> - moisture 34% and stable, adequate → **nitrogen deficiency → soil test / N application**

This makes sensor fusion **load-bearing** rather than decorative, is demonstrable in thirty seconds, and is exactly what Architecture A cannot do. It also lands the PS economic objective (D6, "lower input costs"): the failure it prevents is *the farmer buying the wrong input* — money lost twice, once on the wrong input and again on the untreated real problem.

### Architecture C — "Predictive risk engine"

Time-series environmental modelling that forecasts disease and pest pressure windows before symptoms appear.

**DEFER as primary, ADOPT as a bounded secondary layer.** Strongly aligned with "before they become large-scale crop failures," but validating a forecast needs longitudinal ground truth we will not have in hackathon timeframes. Include an honest bounded version — established agronomic risk models for humidity/temperature disease windows — and label it clearly as rule-based, not as a learned predictor we validated.

**Recommendation: B as the spine, C as a bounded layer on top.**

---

## 6. Preliminary model candidates

| Task | Candidate | Rationale | Deployment note |
|---|---|---|---|
| Disease / deficiency vision | MobileNetV3 or EfficientNet-Lite, INT8 | Small, NPU-friendly, present in AI Hub Models | Verify op support under QNN before committing |
| Pest detection | YOLOv8n / YOLO-NAS-S | Detection is needed (count + location), not classification | Heavier; validate on target early |
| Sensor anomaly | Rule + lightweight statistical model | Transparent, explainable, needs no training data | CPU. Do **not** deep-learn this |
| Fusion / risk | Explicit probabilistic or rule-based fusion | Must be explainable to a farmer and to a judge | CPU |

The master prompt is right to warn against deep learning where a transparent rule is better. Irrigation scheduling and environmental risk are exactly those cases. An LSTM for soil moisture would be worse engineering *and* worse for judging.

---

## 7. Risk register

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **Dataset domain gap** — lab-trained model fails on field images | **CRITICAL** | Held-out-condition testing; report the honest field number; see section 4 |
| R2 | **Hardware unavailable** — $399–599 plus India import lead time | **HIGH** | Day-one AI Hub hosted-device spike yields Level B evidence with no board. Board becomes upside, not dependency. |
| R3 | **Qualcomm path fails late** — unsupported ops, quantization accuracy collapse | **HIGH** | Move to day one. Spike before training anything. |
| R4 | **No onboard cellular on RB3 Gen 2**, but PS demands SMS | MEDIUM | Explicit backhaul design decision; USB LTE dongle for the demo |
| R5 | **Scope sprawl** — eight PS sub-requirements, shallow everywhere | **HIGH** | PS says "some or all." Build three deeply. |
| R6 | **Documentation displaces implementation** | **HIGH** | Docs written as evidence accrues, not before. See section 8. |
| R7 | Live demo fails on stage | MEDIUM | Recorded fallback for every stage; deterministic replay mode |

---

## 8. Deviations from the master prompt (logged)

| Master prompt says | We do instead | Why |
|---|---|---|
| §44: produce full assessment, do not code | This assessment **plus a day-one Qualcomm spike in parallel** | The highest-risk item must be retired first, not fifth |
| §32: 25 markdown documents | ~8 documents, each written when the evidence it describes exists | Judges read none of them; documentation must not displace build time |
| §31: ten serial gates | Gate 5 (Qualcomm deployment) pulled to position 1 as a spike | De-risks the hardest claim in hours instead of weeks |
| §0: ban the words "on-device", "real-time" | Allowed — but **never without an attached measured number** | They are the PS's own vocabulary; the sin is the unbacked claim, not the word |
| §37: internship portfolio layer | Deferred until after Gate 8 | A distraction during build; trivially assembled afterwards from real artifacts |
| — (absent from prompt) | **Added: Category = Hardware implication** | Materially changes what must be demonstrated |
| — (absent from prompt) | **Added: dataset contamination as risk #1** | The most likely single cause of this project failing |

---

## 9. Unanswered questions blocking implementation

1. **Deadline.** Internal hackathon or SIH grand finale? How many weeks?
2. **Hardware.** Do you have, or can you get, an RB3 Gen 2 or any Snapdragon device? Budget? A Snapdragon Android phone is a legitimate fallback Level C target.
3. **Team.** How many people, and what can each actually do (ML / embedded / frontend / hardware)?
4. **Sensors.** Any physical sensors on hand — soil moisture probe, DHT22, and so on?
5. **Crop focus.** One crop deeply, or generic? Regional relevance affects both dataset and judge reception.
6. **Prior work.** Is anything in the existing `SIH_AI_Classification_Model` tree reusable, or is this greenfield?

---

## 10. Immediate next actions (once Q1–Q3 are answered)

- [ ] **SPIKE-0:** sign up for AI Hub, confirm the free-tier reality, compile a stock MobileNetV3 for QCS6490, run one hosted profile job, record real latency. *Retires R3. Target: hours, not days.*
- [ ] `docs/01_problem_statement_analysis.md` — formalize section 1 above
- [ ] `docs/02_requirements.md` — MUST / SHOULD / DEFER against actual team capacity
- [ ] `docs/03_use_case_prioritization.md` — select the three capabilities to build deeply
- [ ] Sensor simulator exposing the same interface the physical sensors will use
