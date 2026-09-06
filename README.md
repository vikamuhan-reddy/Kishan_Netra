# Smart Farming Assistant — Edge AI Crop Diagnosis

**SIH 2026 · Problem Statement 26180 · Qualcomm Inc · Category: Hardware**
**Theme:** Agriculture, FoodTech & Rural Development

An edge-AI field assistant that diagnoses cotton crop stress by **resolving an ambiguous
visual differential against field sensor history**, and delivers an explained
recommendation to the farmer without requiring an internet connection.

---

## The problem this solves that a classifier cannot

A cotton leaf showing chlorosis or reddening might be suffering from nitrogen
deficiency, water stress, or a viral infection. **These look alike to a camera.** This
is not a weakness of the vision model that a bigger model would fix — a single RGB
frame does not contain the information needed to separate them.

A three-day soil-moisture trend does.

So the vision model emits a ranked **differential** rather than a label, and the sensor
layer disambiguates it:

```
                    identical vision output
        nitrogen_deficiency 41% · water_stress 37% · ...
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
   moisture 21%, −4.5%/day         moisture 32%, stable
   43 °C, 120 h since irrigation   irrigated yesterday
            │                               │
            ▼                               ▼
     WATER STRESS (67%)          NITROGEN DEFICIENCY (71%)
     → irrigate                  → soil test, then nitrogen
```

A plain classifier stops at the argmax and gives both farmers the same advice. One of
them fertilizes a plant that is dying of thirst — paying twice, once for the wrong
input and again for the problem left untreated. That is the PS's own "lower input
costs" objective (requirement D6) made concrete.

This is why sensor fusion in this system is **load-bearing rather than decorative.**

---

## Current status — read this before making any claim

| Validation level | Status | What we may claim |
|---|---|---|
| **A — laptop simulation** | ✅ working | Fusion logic, sensor behaviour, advisory generation, degraded-mode handling |
| **B — Qualcomm hosted device cloud** | ⏳ SPIKE-0 not yet run | Nothing yet. Once run: real latency, memory and compute-unit split on real Snapdragon silicon. |
| **C — physical board in a field** | ❌ not this round | Nothing. Boards are next-round work if selected. |

**No performance claim in this repository is measured yet.** The fusion engine is
tested; the Qualcomm numbers do not exist until `edge/spike0_aihub.py` runs
successfully. Do not put a latency figure on a slide before then.

---

## Architecture

```
   CAMERA                    SOIL / TEMP / HUMIDITY PROBES
      │                                   │
      ▼                                   ▼
 ┌─────────────────────────────────────────────────────┐
 │  EDGE DEVICE  (Qualcomm QCS6490 target)             │
 │                                                     │
 │  vision model ──► VisionDifferential      [NPU]     │
 │  sensor driver ─► SensorWindow            [CPU]     │
 │                    │                                │
 │                    ▼                                │
 │              FusionEngine                 [CPU]     │
 │           differential resolution                   │
 │                    │                                │
 │                    ▼                                │
 │         Diagnosis + Evidence + Action               │
 │                    │                                │
 │              local queue (offline-safe)             │
 └────────────────────┬────────────────────────────────┘
                      │
                      ▼
            FARMER INTERFACE  (app / display / SMS)
                      │
             ─ ─ ─ intermittent ─ ─ ─
                      │
                      ▼
              OPTIONAL CLOUD (trends, model updates)
```

Everything required to produce a recommendation runs on the device. The cloud layer is
optional by design, not degraded-optional: with the network down, inference, fusion,
and alerting all continue and data queues locally.

---

## Repository map

| Path | Contents | State |
|---|---|---|
| [`iot/contracts.py`](iot/contracts.py) | Data contracts shared by simulator, hardware driver and fusion | ✅ frozen |
| [`iot/fusion/engine.py`](iot/fusion/engine.py) | Differential-resolution fusion engine | ✅ built, tested |
| [`iot/simulator/field.py`](iot/simulator/field.py) | Seeded field scenario simulator | ✅ built, tested |
| [`demo/differential_demo.py`](demo/differential_demo.py) | The headline demonstration | ✅ runs |
| [`edge/spike0_aihub.py`](edge/spike0_aihub.py) | Qualcomm AI Hub compile + profile spike | ⏳ needs a Qualcomm ID |
| [`tests/test_fusion.py`](tests/test_fusion.py) | 12 tests locking demo claims | ✅ passing |
| [`hardware/cad/`](hardware/cad/) | Parametric OpenSCAD: fixed sentinel station, sensor node enclosure | ✅ renders, STL export |
| `ai/` | Vision model training and evaluation | ⬜ not started |
| `benchmarks/` | Measured results only | ⬜ created when SPIKE-0 produces numbers |

---

## Quickstart

```bash
# See the core claim demonstrated
python -m demo.differential_demo

# Run the test suite
python -m pytest tests/ -q
```

The simulator is seeded, so the demo replays identically every time. A demo that
behaves differently on stage than in rehearsal is a demo that fails on stage.

### Running the Qualcomm spike

```bash
pip3 install qai-hub torch torchvision
qai-hub configure --api_token <YOUR_TOKEN>   # free Qualcomm ID, see aihub.qualcomm.com
python edge/spike0_aihub.py
```

---

## Documentation index

| Document | Purpose |
|---|---|
| [00 — Initial technical assessment](docs/00_initial_technical_assessment.md) | PS decomposition, evaluation clues, risk register, verified Qualcomm resource map |
| [01 — 12-day execution plan](docs/01_plan_12_days.md) | Track assignment, day-by-day schedule, scope cuts |
| [02 — Requirements](docs/02_requirements.md) | PS requirement → engineering requirement, with priority and acceptance test |
| [03 — Use case prioritization](docs/03_use_case_prioritization.md) | Scored comparison of the four candidate use cases |
| [06 — Hardware selection](docs/06_hardware_selection.md) | Candidate evaluation, component choices, India-verified BOM |
| [07 — Hardware decision](docs/07_hardware_decision.md) | Selected platform, rejections, provable claims, fallback plan |
| [09 — Sensor fusion](docs/09_sensor_fusion.md) | How the fusion engine works and why it is designed this way |
| [22 — Power and autonomy](docs/22_power_autonomy.md) | Energy budget, solar and battery sizing, duty-cycle architecture |
| [23 — Sensing reference](docs/23_sensing_reference.md) | Every sensor: operating principle, why it's needed, what breaks without it |
| [CAD — Mechanical design](hardware/cad/README.md) | Parts, renders, regeneration commands, embedded design decisions |
| [13 — Failure modes](docs/13_failure_modes.md) | Hostile-reviewer cases and the tested behaviour under each |
| [Decision log](docs/decision_log.md) | Every significant choice, its alternatives, and its revisit condition |

---

## Scope: three capabilities deeply, not eight shallowly

The PS lists eight capability groups and explicitly permits *"some or all."* We build
three deeply (crop health, irrigation intelligence, edge processing), two simply
(farmer advisory, environmental risk), and defer three (pest detection, full analytics,
fleet management) with the architecture slot visible.

**Deferring pest detection is a deliberate call, not an omission.** Stated openly it
reads as engineering judgement; hidden, it reads as a gap. See
[docs/02_requirements.md](docs/02_requirements.md) for the full priority table.
