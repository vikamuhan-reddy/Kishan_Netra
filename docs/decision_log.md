# Decision Log

Every significant architectural choice, its alternatives, and the condition under which
we would revisit it. A decision without a revisit condition is a decision nobody can
challenge later with evidence.

---

## DR-001 — Crop: cotton

**Decision:** Focus the entire project on cotton, one crop deeply.

**Alternatives:** tomato · rice · generic multi-crop

**Why:**
- Field-realistic Indian cotton datasets exist (2025 in-field sets, one with 14 classes built for Indian agricultural context), which is what makes honest lab-vs-field evidence possible at all
- Blanket pesticide spraying in Indian cotton is the PS's D6 written as a documented national problem — we are addressing a known crisis, not inventing a use case
- Cotton leaf reddening/chlorosis is genuinely ambiguous between nitrogen deficiency, water stress, and leaf curl virus, so the core differentiator has a real instance
- Higher value per acre than rice, which makes the device unit economics defensible

**Rejected — tomato:** PlantVillage has 10 tomato classes, which makes training trivially
easy and is exactly why competing teams will choose it. Training on the contaminated lab
set is the trap documented in `00_initial_technical_assessment.md` §4.

**Rejected — rice:** IRDD exists and Indian relevance is high, but rice is flooded, which
weakens the soil-moisture disambiguation story, and low value per acre makes a
$399–599 device harder to justify.

**Trade-off:** No PlantVillage cotton class, so we depend entirely on the newer field
datasets. If access fails, we have no lab baseline for comparison.

**Evidence:** Dataset search 2026-09-02. **Access and licence not yet verified.**

**Revisit if:** cotton dataset download or licence fails → fall back to rice (IRDD).
**The crop is not locked until data is on disk.** Owner: T1.

---

## DR-002 — Architecture: corroborated diagnosis

**Decision:** Vision emits a ranked differential; sensor history resolves it. Not a
classifier with a dashboard beside it.

**Alternatives:**
- **A — classifier + dashboard:** camera → CNN → label → app, sensors as charts
- **C — predictive risk engine:** forecast disease/pest pressure windows before symptoms

**Why:** Architecture A is what most teams will build and is indistinguishable from
hundreds of public repositories — it scores 1 on novelty and leaves both the Hardware
category and PS section 5 unaddressed. Architecture B makes sensor fusion load-bearing:
the system resolves an ambiguity that neither modality can resolve alone.

**Rejected — C as primary:** strongly aligned with "before they become large-scale crop
failures," but validating a forecast needs longitudinal ground truth unavailable in
hackathon timeframes. Adopted as a bounded rule-based layer instead (DR-005).

**Trade-off:** Requires paired vision and sensor context at inference time. A photo with
no sensor history degrades to plain classification.

**Evidence:** Working implementation; `test_identical_image_yields_different_action_per_field`.

**Revisit if:** field testing shows the two causes are separable by vision alone — the
premise would then be false and the architecture unjustified.

---

## DR-003 — Fusion method: decision-level

**Decision:** Decision-level fusion — sensor-derived agronomic likelihoods reweight the
vision distribution.

**Alternatives:** rule-based · feature-level · temporal/learned

**Why:** Needs no paired image+sensor training data (which does not exist for Indian
cotton), is explainable term by term, and degrades gracefully under sensor loss.

**Rejected — feature-level:** the textbook answer and the highest ceiling, but it
requires paired training data we would have to fabricate. Fabricated data is not
evidence.

**Rejected — pure rule-based:** cannot express "vision thinks X, sensors make X
unlikely" as a degree; collapses to a decision tree that discards vision confidence.

**Partially adopted — temporal:** trend features computed explicitly (least-squares
moisture slope), but no learned sequence model.

**Trade-off:** Multipliers are hand-set from agronomy, not fitted to data. This is the
limitation most likely to be challenged.

**Evidence:** [`iot/fusion/engine.py`](../iot/fusion/engine.py); [09_sensor_fusion.md](09_sensor_fusion.md) §2.

**Revisit if:** real paired field data becomes available — the architecture accepts
learned weights without modification.

---

## DR-004 — Vision model emits a distribution, not a label

**Decision:** The vision model's output contract is `VisionDifferential` — a validated
probability distribution over hypotheses. Argmax is never taken inside the model.

**Alternatives:** standard single-label classification output

**Why:** An argmax discards exactly the information fusion needs. This costs nothing at
inference time and is the enabling decision for the entire system — every other design
choice depends on it.

**Trade-off:** Downstream consumers must handle distributions. Mitigated by validating
the contract at construction: scores not summing to 1.0 raise immediately.

**Evidence:** `test_vision_scores_must_be_a_distribution`.

**Revisit if:** never, while DR-002 stands.

---

## DR-005 — Environmental risk stays rule-based

**Decision:** Implement environmental risk (D10–D12) as transparent agronomic threshold
rules. Do not present it as machine learning.

**Alternatives:** learned time-series risk model · omit entirely

**Why:** Established disease-pressure windows are transparent, need no training data, and
answer questions well. A learned predictor would need longitudinal ground truth we do not
have, and claiming a model we could not validate is the easiest available way to lose a
judging round.

**Trade-off:** Scores low on novelty (1) and Qualcomm relevance (1). Accepted — it is
cheap, the PS asks for it, and it is honest.

**Evidence:** [03_use_case_prioritization.md](03_use_case_prioritization.md) UC4.

**Revisit if:** a multi-season dataset becomes available.

---

## DR-006 — Advisory only; no actuation

**Decision:** The system recommends. It does not switch pumps, open valves, or trigger
sprayers.

**Alternatives:** automatic irrigation control on high-confidence water-stress detection

**Why:** With frozen-sensor detection unimplemented (failure mode A2) and no
out-of-distribution gate on the vision model (A3), an actuation path could irrigate on a
dead probe's word. Advisory-only bounds the worst case to a farmer ignoring bad advice
rather than a field flooded overnight.

**Trade-off:** Less impressive as a demo than closing the loop on hardware.

**Evidence:** [13_failure_modes.md](13_failure_modes.md) §6.

**Revisit if:** A2 and A3 are closed **and** a farmer-approval step gates the action.
Even then, prefer approval-gated actuation over autonomous.

---

## DR-007 — Defer pest detection, reserve the architectural slot

**Decision:** Do not build pest detection this round. Document where it plugs in.

**Why:** It needs a second model, an annotated detection dataset, and its own
quantization and profiling pass — inside 12 days that comes directly out of the three
MUST capabilities. It scores 2 on feasibility and 2 on data availability.

**Why it is safe to defer:** D6 ("targeted intervention rather than blanket pesticide")
is satisfied *without* the pest model, through correct cause attribution. Not spraying
for a disease that is actually thirst is targeted intervention.

**Trade-off:** Leaves a visible PS section unimplemented. Mitigated by stating the choice
openly — "we chose depth on three over shallowness on eight" reads as engineering
judgement; hidden, it reads as a gap.

**Evidence:** [03_use_case_prioritization.md](03_use_case_prioritization.md) UC2.

**Revisit if:** selected for the next round with more time.

---

## DR-008 — Validation ceiling is Level B this round

**Decision:** Target Qualcomm AI Hub hosted device cloud (Level B) as the sole source of
Qualcomm-specific evidence. Make no Level C physical-deployment claim.

**Alternatives:** buy an RB3 Gen 2 now ($399 Core / $599 Vision) · Snapdragon phone as a
physical target · claim nothing about Qualcomm

**Why:** No board is available this round; boards come if selected for the next. AI Hub
is free for developers (verified 2026-09-02) and profiles on real Snapdragon silicon,
which is genuine on-device evidence rather than simulation.

**Trade-off:** No power measurements, no real camera or sensor I/O, no field conditions.

**Consequence:** SPIKE-0 becomes the highest-priority task in the project, scheduled
day 1 — it is the *entire* Qualcomm proof, and if the compile path fails we must know
immediately rather than at day 9.

**Evidence:** [01_plan_12_days.md](01_plan_12_days.md) §1.

**Revisit if:** a board becomes available → Level C additions, with every claim relabelled.

---

## DR-009 — Documentation is a maintained deliverable

**Decision:** Maintain written documentation alongside the code for the duration of the
project.

**Context:** The team's master prompt specified 25 markdown documents to be produced
before implementation began. The initial engineering recommendation was to cut this
sharply, on the grounds that hackathon judges read none of them and that an earlier
project of the team's accumulated fourteen design documents beside a single working
service. **The team decided documentation is required regardless.**

**Resolution:** Both concerns are satisfied by tying documentation to evidence rather
than dropping it — document a component once it is built and tested, cite real measured
output instead of projected numbers, and mark anything unevidenced as explicitly blocked
on what would justify it. Documents describing software nobody has written are the
failure mode; documents recording what exists are not.

**Trade-off:** Documentation time is real time. Managed by keeping documents tied to
completed work so they are written once, from fact, rather than rewritten as the design
moves.

**Revisit if:** the team says otherwise.

---

## DR-010 — Two-tier hardware: ESP32 sensor nodes + one shared Qualcomm compute node

**Decision:** Distributed ESP32 sensor nodes reporting to a single Qualcomm compute node,
rather than all sensors cabled to one board.

**Alternatives:** single-box design with an I²C ADC (ADS1115) · Raspberry Pi 5 · NVIDIA
Jetson Orin Nano

**Why:**
- **Forced by the hardware.** A Qualcomm Linux SoC exposes I²C, SPI, UART, PCIe, USB and MIPI but **no user analog input**. Capacitive soil moisture sensors are analog. An ESP32 reads them natively; the board cannot.
- **Spatial coverage.** Soil moisture varies across a field. One probe beside the compute box measures one spot; cabling ten across an acre is not a field-viable install.
- **Power.** ESP32 deep sleep draws microamps between readings — months unattended on a small panel and cell. A Snapdragon SoC cannot duty-cycle that hard while staying responsive.
- **Unit economics, decisive.** ₹50,000 per smallholder plot is not a product. One node per cooperative plus ₹3,400 sensor nodes per plot is — and it maps directly onto PS D20 (smallholder → cooperative → enterprise). **The hardware topology is the business model.**
- Makes MQTT genuinely justified rather than decorative architecture.

**Rejected — single-box with ADC:** solves the analog problem only; leaves spatial
coverage, power duty-cycling, and per-plot cost unaddressed.

**Rejected — Raspberry Pi 5 and Jetson Orin Nano:** both technically usable, both
eliminate the Qualcomm relevance the entire project rests on. Jetson is the reflexive
edge-vision choice and is rejected for a non-technical reason that dominates: **NVIDIA is
not the sponsor.**

**Trade-off:** an extra component class to build, provision and debug, plus a wireless
link that can fail. Accepted — the offline queue already assumes unreliable links.

**Evidence:** [06_hardware_selection.md](06_hardware_selection.md),
[07_hardware_decision.md](07_hardware_decision.md). Prices verified 2026-09-02.

**Revisit if:** a Qualcomm platform exposing user ADC is selected, or the deployment
target narrows to single-plot installs where spatial variation does not matter.

---

## DR-011 — Capacitive soil moisture sensor, never resistive

**Decision:** Capacitive soil moisture sensors (₹83) throughout.

**Alternatives:** resistive sensors (cheaper by roughly ₹40)

**Why:** Resistive probes expose bare metal to wet soil, corrode within months, and
suffer **20–40% VWC error in fertilized or saline soil** — that is, in every field this
system would deploy in. Capacitive sensors seal the electrodes and, after soil-specific
calibration, match secondary-standard sensors.

**Why it matters more here than usual:** the entire differentiator (DR-002) rests on
distinguishing water stress from nitrogen deficiency using soil moisture. A 20–40% error
in that exact measurement would not degrade the system gracefully — it would invert the
diagnosis and send the farmer to buy the wrong input. This is the cheapest component in
the BOM and the one with the highest leverage on correctness.

**Trade-off:** requires soil-specific calibration to be accurate, which we have not done.

**Consequence:** **no field-accuracy claim about moisture is defensible until calibration
is performed.** This independently corroborates the uncalibrated-threshold limitation in
[09_sensor_fusion.md](09_sensor_fusion.md) §4 — two separate parts of the system land on
the same caveat, and it should be stated before a judge finds it.

**Evidence:** [06_hardware_selection.md](06_hardware_selection.md) §5.

**Revisit if:** budget allows industrial-grade probes with factory calibration.

---

## DR-012 — The field node is autonomous; the SoC is off by default

**Decision:** The product is a solar-powered, self-triggering station installed once and
left for a season. An always-on low-power MCU (the "sentinel") watches the sensors and
switches power to the Snapdragon compute module only when a capture is warranted.

**Supersedes:** the Snapdragon-phone-as-compute-node recommendation in DR-008 and
[07_hardware_decision.md](07_hardware_decision.md).

**Context — this was a correction from the team.** The phone was recommended because it
was free, already owned, carried a real Qualcomm NPU, and uniquely solved SMS delivery
with its cellular radio. That reasoning was sound on cost and convenience and wrong on
the thing that mattered: **a phone is not autonomous hardware.** It has to be placed and
retrieved by a person, is not weather-sealed, cannot survive a season outdoors, and
cannot trigger its own captures. The phone survives only as a validation shortcut — a
physical Snapdragon NPU to measure on — never as the product.

**Why the SoC must be duty-cycled:** at an assumed 6 W continuous the compute node alone
needs ~144 Wh/day, implying a 60–80 W panel and ~300 Wh of battery — several times the
cost of the compute, on a mast that then needs guying against wind load. Duty-cycled to
four ~85 s sessions per day, the entire station is estimated at **0.8 Wh/day**. Autonomy
is what makes the bill of materials possible, not a feature added to it.

**The part that makes this a design rather than a hack:** the sentinel's wake triggers
are the *same* stress conditions the fusion engine reasons about — moisture crossing the
stress threshold, a steep drying trend, a humidity window favourable to blight. The
camera fires when there is something worth looking at. Power optimization and diagnostic
logic turn out to be one rule set.

**Trade-offs:**
- Latency to a first look is bounded by the sentinel's 15-minute sample interval, not by inference speed. Acceptable — crop stress develops over hours and days.
- Boot time is now part of the energy cost, which pushes toward keeping the OS image small.
- A second processor to build, provision and debug.

**Consequent BOM changes:** LiFePO4 instead of 18650 Li-ion (sealed enclosures in Indian
summer exceed Li-ion's safe temperature range), MPPT instead of linear charging, a load
switch on the SoC rail, a pressure-equalising vent against condensation, and a sealed
fixed camera instead of a phone.

**Evidence:** [22_power_autonomy.md](22_power_autonomy.md). ⚠️ The SoC active-power
figure dominating the budget is an **estimate** and must be replaced with a measurement
from SPIKE-0 or the QCS6490 datasheet before the autonomy claim is made.

**Revisit if:** measured SoC power differs enough to change the panel or battery sizing,
or if a use case emerges that genuinely requires continuous vision.
