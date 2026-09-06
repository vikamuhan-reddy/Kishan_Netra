# 13 — Failure Modes

Written from a hostile-reviewer stance: what breaks this device in a field, and what
does it do when it breaks?

**Status legend**

- ✅ **tested** — behaviour is asserted by a passing test, named in the row
- 🔨 **implemented, untested** — code path exists, no test yet
- ⬜ **not handled** — known gap, stated openly

A field device is judged on its worst day, not its best. The relevant question is never
"does it work?" but "what does it do when it doesn't?"

---

## 1. Sensor failures

| Failure | Behaviour | Status |
|---|---|---|
| **Partial dropout** (probe intermittently returns nothing) | Above 30% incomplete readings the window is flagged `degraded`, every sensor multiplier is pulled toward 1.0 at 25% influence, and the reduction is stated in the output. Confidence measurably drops: 67% → 59% on the same underlying conclusion. | ✅ `test_degraded_sensors_reduce_their_own_influence` |
| **Total sensor loss** (every channel null) | Falls back to the vision prior, flags `degraded`, and sets `needs_human_review`. Does not crash, does not silently pretend the sensors agreed. | ✅ `test_total_sensor_loss_falls_back_to_vision_without_crashing` |
| **Empty window** (no readings at all) | Returns a valid diagnosis from vision alone rather than raising. | ✅ `test_empty_window_does_not_raise` |
| **Too few readings to fit a trend** | `moisture_trend_pct_per_day` returns `None` rather than a fabricated `0.0`. A false "stable" reading would actively push the diagnosis toward nitrogen deficiency — this is a correctness bug, not a cosmetic one. | ✅ `test_too_few_readings_gives_no_trend_rather_than_a_fake_zero` |
| **Physically impossible values** (moisture 247%, temp −40°C) | Range-checked against `PLAUSIBLE_RANGES` at the contract boundary. Out-of-range values are treated as **missing, not as data**, and count toward the dropout ratio. A floating ADC pin is a fault, not a measurement. | ✅ `TestImplausibleValues` (6 cases) |
| **Frozen sensor** (identical value repeated, probe dead but reporting) | Detected. Six bit-identical consecutive readings on a channel flag it stuck; the channel is excluded from all derived features and the diagnosis names the dead probe. | ✅ `TestStuckSensor` (5 tests) |
| **Sensor drift** (slow calibration loss) | Not detected. Would require reference comparison or periodic recalibration. | ⬜ accepted limitation |

### The stuck probe, and why it was the worst gap

A dead probe that keeps reporting was the most dangerous failure this system faced,
because it looks like healthy data: the value is in range, the reading is present, and
the trend is a clean, convincing **zero**. Nothing else in the pipeline could catch it.

Read at face value, perfectly stable moisture means "not water-driven", which resolves
the differential toward **nitrogen deficiency** — sending a farmer to buy fertilizer for
a crop that may be dying of thirst. The wrong input, and the real problem left untreated.

**Detection exploits the one thing a dead sensor cannot fake: noise.** A live capacitive
probe in soil always jitters. Bit-identical values in a row mean the sensor died while
still reporting.

Observed behaviour on the `dying_probe` scenario — soil drying at 4.5%/day, probe frozen
24 h ago at an adequate-looking value:

```
soil moisture now : unavailable        (channel excluded)
moisture trend    : unavailable
after fusion      : water_stress (42%)
ACTION            : inspect manually - evidence is not conclusive
[!] stuck sensor detected (soil_moisture_pct) - probe needs service
[!] top-two margin 0.06 below 0.15 - not committing to a single cause
```

It does not give the dangerous confident answer, and it does not substitute a different
confident answer either. It says what it cannot know, and it names the part to replace.

---

## 2. Vision failures

| Failure | Behaviour | Status |
|---|---|---|
| **Low-confidence prediction** | If the post-fusion top-two margin falls below 0.15, the diagnosis is flagged `needs_human_review` and the action becomes *"inspect manually — evidence is not conclusive."* | ✅ `test_low_margin_declines_to_commit` |
| **Malformed distribution** (scores not summing to 1.0) | `VisionDifferential` raises `ValueError` at construction. A contract violation is a bug, not a warning to be logged and ignored. | ✅ `test_vision_scores_must_be_a_distribution` |
| **Unseen disease** (a pathogen outside the trained classes) | The model will distribute mass across known classes and may look confident. **Not handled.** Requires an out-of-distribution check. | ⬜ **gap — see action A3** |
| **Blurred / poorly lit / occluded image** | Not handled. No input quality gate exists yet. | ⬜ **gap — see action A4** |
| **Dust or water on the lens** | Not handled. Degrades silently. | ⬜ accepted for this round |

**Gap A3 is the one a judge is most likely to probe.** "What happens when a farmer
photographs a disease you never trained on?" The honest current answer is: the model
produces a confident wrong differential, and fusion cannot rescue it because fusion only
reweights hypotheses it was given. An OOD confidence gate is the mitigation.

---

## 3. Connectivity and power

| Failure | Behaviour | Status |
|---|---|---|
| **Internet unavailable** | Inference, fusion and alerting are entirely local by design — no cloud call is on the critical path. | 🔨 by architecture; end-to-end demo not yet built |
| **Internet returns** | Queued data synchronizes and state reconciles. | ⬜ **not built — required for D14** |
| **Local storage full** | Not handled. Needs a ring buffer with oldest-first eviction. | ⬜ gap |
| **Power interruption mid-inference** | Not handled. | ⬜ accepted for this round |
| **Device restart** | Not handled — no state persistence yet. | ⬜ gap |
| **No cellular radio for SMS** | RB3 Gen 2 has Wi-Fi 6E and Bluetooth 5.2 but **no onboard cellular** (verified 2026-09-02). SMS delivery (D17) needs an explicit backhaul: USB LTE dongle, LoRa to a village gateway, or store-and-forward. | ⬜ **design decision open** |

The offline queue is the largest single gap against a MUST requirement. It is scheduled
for T3, day 3 in [01_plan_12_days.md](01_plan_12_days.md).

---

## 4. Model deployment

| Failure | Behaviour | Status |
|---|---|---|
| **Unsupported operator under QNN** | Unknown until SPIKE-0 runs. This is precisely why the spike is scheduled on day 1 rather than day 9. | ⏳ blocked on SPIKE-0 |
| **Quantization accuracy collapse** | FP32 vs INT8 must be measured, not assumed. If INT8 costs too much accuracy, FP16 is the fallback. | ⏳ blocked on SPIKE-0 |
| **Hosted device unavailable** | Spike script falls back to the first device the account can reach rather than failing outright. | 🔨 implemented |
| **Physical board unavailable** | Not a dependency this round. Level B hosted-device evidence stands alone. | ✅ by plan |

---

## 5. Demo failures

| Failure | Mitigation | Status |
|---|---|---|
| **Non-deterministic demo output** | Simulator is seeded; identical replay every run. A demo that behaves differently on stage than in rehearsal is a demo that fails on stage. | ✅ `test_simulator_is_deterministic` |
| **Live demo crashes on stage** | Recorded fallback for every stage. | ⬜ scheduled day 8 |
| **Network demo fails** | Offline mode should be shown by physically disabling the interface, not by a mocked flag — but a mocked path must exist as fallback. | ⬜ scheduled |

---

## 6. Safety posture

Every output of this system is **advisory**. There is no actuation path: the device does
not switch pumps, open valves, or trigger sprayers.

```
prediction → confidence → fusion → explanation → recommendation → FARMER DECIDES
```

This is a deliberate constraint, not an unfinished feature. The failure modes above
demonstrate why: with a frozen probe undetected (A2) and no out-of-distribution check
(A3), an automatic actuation path could irrigate on a dead sensor's word. Advisory-only
means the worst case is a farmer ignoring bad advice, not a field flooded overnight by a
confident wrong prediction.

See [decision_log.md](decision_log.md) DR-006.

---

## 7. Open actions, ranked

| ID | Action | Severity | Owner | Status |
|---|---|---|---|---|
| ~~A2~~ | ~~Detect frozen/stuck sensor readings~~ | ~~HIGH~~ | T3 | ✅ **closed** |
| ~~A1~~ | ~~Validate physically impossible sensor values~~ | ~~HIGH~~ | T3 | ✅ **closed** |
| **A3** | Out-of-distribution gate on the vision differential | **HIGH** — most likely judge question | T1 | ⬜ open |
| — | Offline queue and reconnect reconciliation | **HIGH** — MUST requirement D14 | T3 | ⬜ open |
| **A4** | Input quality gate (blur, exposure, occlusion) | MEDIUM | T1 | ⬜ open |
| — | Storage ring buffer with oldest-first eviction | MEDIUM | T3 | ⬜ open |
| — | State persistence across restart | LOW this round | T3 | ⬜ open |

**A3 is now the highest open risk.** It is the mirror image of the stuck-probe problem,
on the vision side: asked about a disease it was never trained on, the model distributes
mass across known classes and can look confident. Fusion cannot rescue it, because fusion
only reweights hypotheses it was given. Expect the question *"what happens when a farmer
photographs something you never trained on?"* and have an answer better than the current
one.

---

## 8. Test coverage summary

**23 tests pass** (`python -m pytest tests/ -q`), covering four headline-claim behaviours
and thirteen failure modes across sensor loss, stuck channels, implausible values,
low-confidence vision, and contract violations.

**Coverage is honest but partial.** Connectivity, power, storage and model-deployment
failures are still untested, and A3 remains open. State that ratio plainly rather than
hiding it behind the passing count — a suite that only tests what already works is
decoration.
