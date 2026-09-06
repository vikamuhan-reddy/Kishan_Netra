# 01 — Execution Plan (12 days, 5 people, no physical Qualcomm board)

**Constraints as given, 2026-09-02:**

- Deadline: **under 2 weeks**
- Hardware: **simulation only this round.** Physical boards available *if selected for the next round.*
- Team: **4–6 people**
- Scope: **one crop, deeply**

**Therefore the deliverable this round is: a working prototype demo + a deck that gets us selected.** Not a field deployment. Plan accordingly, and say so honestly.

---

## 1. The validation-level reality (this is the honesty spine)

| Level | Available this round? | What we can legitimately claim |
|---|---|---|
| **A — laptop simulation** | ✅ yes | Sensor behaviour, fusion logic, offline queue, farmer UI, end-to-end flow |
| **B — Qualcomm hosted device cloud** | ✅ **yes, and free** | **Real inference latency, memory and model size on real Snapdragon silicon.** This is genuine on-device evidence, not simulation. |
| **C — physical board in a field** | ❌ not this round | Nothing. We will not claim it. Stated as next-round work. |

**The single most important consequence:** Level B is the *entire* Qualcomm-specific proof available to us, and it is free. It is therefore the highest-priority task in the project, and it runs on **day 1**, before any model training.

Most competing teams will present Level A and describe it with Level C language. We present Level B and label it precisely. That contrast is worth more than any feature.

---

## 2. Crop selection: **Cotton** (RECOMMENDED)

| Criterion | Why cotton wins |
|---|---|
| **Field-realistic dataset exists** | Multiple 2025 Indian in-field cotton datasets, including a 14-class set built for Indian agricultural context. Directly enables the honest lab-vs-field evidence that is our #1 differentiator. |
| **PS alignment on D6** | The PS says "targeted intervention rather than blanket pesticide application." Blanket pesticide spraying in Indian cotton is *the* textbook case — pink bollworm resistance is a documented national problem. We are not inventing a use case; we are addressing a known one. |
| **Judge recognition** | Cotton farmer distress is nationally understood. No explanation needed. |
| **Ambiguity story works** | Cotton leaf reddening/yellowing is genuinely ambiguous between nitrogen deficiency, water stress, and leaf curl virus. Our differentiator has a real instance here. |
| **Water argument** | Cotton is water-intensive; irrigation savings are quantifiable and meaningful. |

**Rejected alternatives:**

- **Tomato** — PlantVillage has 10 tomato classes, which makes training trivially easy *and* is exactly why every other team will use it. Training on the contaminated lab set is the trap described in `00_initial_technical_assessment.md` §4.
- **Rice** — IRDD exists and Indian relevance is high, but rice is flooded, which weakens the soil-moisture story, and value per acre makes device unit economics harder to defend.

⚠️ **Action before locking:** verify actual download access and licence for the cotton datasets. If access fails, fall back to rice (IRDD). Do not lock the crop until data is on disk. Owner: T1, day 1.

---

## 3. Scope decision — build 3 deeply, declare the rest

The PS lists eight capability groups and explicitly permits "some or all."

| PS group | Decision | Rationale |
|---|---|---|
| 1. Crop health (disease + deficiency) | **MUST — build deep** | Core of the differentiator |
| 3. Smart irrigation / water stress | **MUST — build deep** | The disambiguating signal; makes fusion load-bearing |
| 5. Edge AI processing | **MUST — build deep** | The Qualcomm proof; the reason this PS exists |
| 6. Farmer advisory | **SHOULD — build simple but real** | Cheap, high demo impact, PS-verbatim advisory strings |
| 4. Environmental risk | **SHOULD — bounded rule-based** | Honest agronomic risk windows, clearly labelled as rules |
| 2. Pest detection | **DEFER — architect for it, show the slot** | Needs a second model + annotation budget we do not have in 12 days. Show where it plugs in. |
| 7. Analytics dashboard | **DEFER — minimal trends view only** | Judges spend little time here; it is not what wins |
| 8. Scalable deployment | **DEFER — architecture slide only** | Design it on paper, do not build fleet management |

**Deferring pest detection is a deliberate, defensible call, not an omission.** Stated openly ("we chose depth on three over shallowness on eight") it reads as engineering judgement. Hidden, it reads as a gap.

---

## 4. Track assignment (5 people, parallel from day 1)

| Track | People | Owns |
|---|---|---|
| **T1 — Vision/ML** | 2 | Dataset acquisition, training, held-out-condition evaluation, honest domain-gap numbers |
| **T2 — Qualcomm edge** | 1 | AI Hub signup, compile, INT8 quantization, hosted-device profiling, benchmark tables |
| **T3 — IoT + fusion** | 1 | Sensor simulator, fusion/risk engine, offline queue, advisory generation |
| **T4 — Interface + narrative** | 1 | Farmer UI, demo script, fallbacks, deck |

T2 and T3 are not blocked by T1. That is the point of the ordering.

---

## 5. Day-by-day

| Day | T1 Vision | T2 Qualcomm | T3 IoT/Fusion | T4 Interface |
|---|---|---|---|---|
| **1** | Acquire + verify cotton datasets. Lock crop. | **SPIKE-0:** AI Hub signup → compile stock MobileNetV3 for QCS6490 → hosted profile job → **record a real latency number** | Sensor simulator running; data contract frozen | Demo storyboard drafted |
| **2** | Baseline training run | Repeat spike with our own architecture; confirm QNN op support | Fusion engine v1 (rules) | UI skeleton |
| **3** | First honest eval; measure the lab→field gap | INT8 quantization path working | Offline queue + reconnect sync | Advisory string set (PS-verbatim) |
| **4** | Improve on field data | Benchmark table: FP32 vs INT8, latency/size/memory | Fusion v2 — the differential-resolution logic | Farmer view working |
| **5** | Freeze model | Final hosted-device numbers captured | End-to-end wiring | Trends view |
| **6** | Domain-shift stress tests (blur, sun, occlusion) | Package the deployment artifact | Failure modes: sensor dropout, bad values | Demo rehearsal v1 |
| **7** | Buffer / retrain if needed | Buffer | Buffer | Deck v1 |
| **8** | — | — | Integration hardening | Demo rehearsal v2 + recorded fallbacks |
| **9** | Evidence review: every claim traced to a number | | | Deck v2 |
| **10** | Mock judge interrogation (all 30 questions) | | | |
| **11–12** | Buffer. Rehearse. Do not add features. | | | |

**Days 11–12 are buffer, not build time.** Every hackathon overruns. A rehearsed working demo of three things beats a broken demo of eight.

---

## 6. Definition of done for this round

- [ ] One real latency/memory number measured on Qualcomm hosted silicon (Level B), with the device named
- [ ] FP32 vs INT8 trade-off measured, not asserted
- [ ] Lab-split accuracy **and** held-out-field accuracy both reported, gap explained
- [ ] Same leaf image + two sensor histories → two different recommendations, live
- [ ] Network disconnected mid-demo → inference and alerts continue → reconnect → queue syncs
- [ ] Every Level A / B / C claim explicitly labelled in the deck
- [ ] Recorded fallback exists for every demo stage

---

## 7. What we will explicitly tell judges we did *not* do

Stating these first removes their power as attacks:

1. No physical field deployment this round — hosted Qualcomm silicon only, labelled as such.
2. Pest detection is architected but not trained — a deliberate depth-over-breadth choice.
3. Yield-risk forecasting is rule-based agronomy, not a validated learned predictor. We do not have the longitudinal ground truth to claim otherwise.
4. Environmental risk uses established disease-pressure windows, not a novel model.
