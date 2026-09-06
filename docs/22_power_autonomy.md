# 22 — Power and Autonomy

The node is installed once and left in the field for a season. Nobody visits it, nobody
holds a phone to a leaf, nobody presses anything. This document is the engineering that
has to be true for that to work.

⚠️ **Every number below marked (est.) is an engineering estimate, not a measurement.**
The SoC active power figure is the one that dominates the budget and it must be replaced
with a measured value from SPIKE-0 or a datasheet before any claim is made. The *method*
is what is being asserted here, not the figures.

---

## 1. Why autonomy changes the architecture

An always-on application SoC is not solar-feasible at smallholder cost. At an assumed
6 W continuous that is **144 Wh/day**, which needs roughly a 60–80 W panel and a 300 Wh
battery — several times the cost of the compute itself, on a mast that now needs guying
against wind load.

So the SoC cannot be always on. The architecture that follows:

```
  ┌──────────────────────────────────────────────────────────┐
  │  SENTINEL  - ESP32-class MCU, ALWAYS ON, ~mW             │
  │                                                          │
  │  every 15 min:  read soil moisture x2, temp, humidity    │
  │                 append to rolling window                 │
  │                                                          │
  │  decide:        is there anything worth looking at?      │
  └───────────────────────────┬──────────────────────────────┘
                              │ power-enable (MOSFET / load switch)
                              ▼
  ┌──────────────────────────────────────────────────────────┐
  │  COMPUTE  - Snapdragon QCS6490, OFF by default           │
  │                                                          │
  │  boot → capture frames → NPU inference → fuse with the   │
  │  sentinel's window → advisory → transmit → power off     │
  └──────────────────────────────────────────────────────────┘
```

**The elegant part:** the sentinel's trigger conditions are the *same* stress conditions
the fusion engine reasons about. The camera fires when there is something to look at.
Power optimization and diagnostic logic turn out to be the same rule set, which is why
this is a design rather than a hack.

---

## 2. Wake triggers

| Trigger | Rationale |
|---|---|
| **Scheduled** — dawn and mid-morning | Consistent illumination gives comparable images day to day, which matters more for a trend than a single frame does |
| Soil moisture crosses below the stress threshold | A water-stress hypothesis just became plausible; look at the plant |
| Moisture trend steeper than the drying threshold | Developing stress, before it is visible to a person |
| Sustained humidity above the blight-favourable window | Disease pressure window opened |
| Peak temperature above heat-stress threshold | Heat event |
| Inbound farmer request (SMS / app) | On demand |

Baseline **2 scheduled wakes/day**, plus an assumed **2 event wakes/day** average.

---

## 3. Energy budget

Assumptions, all **(est.)** unless stated:

| Item | Assumption |
|---|---|
| Sentinel deep sleep | 0.5 mW including regulator losses |
| Sentinel sample + log | 150 mW for 3 s, every 15 min (96×/day) |
| LoRa transmit | 400 mW for 2 s, 24×/day |
| **SoC active** | **6 W — DOMINATES THE BUDGET, MUST BE MEASURED** |
| SoC session | 25 s boot + 60 s capture/inference/transmit = 85 s |
| Wakes per day | 4 (2 scheduled + 2 event) |

**Daily consumption:**

| Load | Calculation | Wh/day |
|---|---|---|
| Sentinel sleep | 0.5 mW × 24 h | 0.012 |
| Sentinel sampling | 150 mW × 3 s × 96 | 0.012 |
| LoRa | 400 mW × 2 s × 24 | 0.005 |
| **SoC sessions** | **6 W × 85 s × 4** | **0.57** |
| Conversion and quiescent losses (~30%) | | 0.18 |
| **Total** | | **≈ 0.8 Wh/day** |

Even trebling the SoC assumption to 18 W and doubling the wakes puts the total under
**5 Wh/day**. The budget is comfortable *because* of duty-cycling, and hostage to it
without.

---

## 4. Solar sizing

Sizing on the **monsoon worst case**, not the annual average — a device that dies every
July is not autonomous.

| | Peak sun hours | Derate (dust, angle, temperature, ageing) | Harvest from 10 W |
|---|---|---|---|
| Clear season | ~5.5 h | 0.70 | 38 Wh/day |
| **Monsoon overcast** | **~1.2 h** | **0.60** | **7.2 Wh/day** |

**A 10 W panel covers the worst case with ~9× margin against the 0.8 Wh/day estimate,
and still clears 5 Wh/day comfortably.**

**Recommendation: 10 W minimum, 20 W if budget allows.** The oversizing buys tolerance for
dust accumulation, partial shading from a growing canopy, and panel degradation — none of
which anyone will be present to correct.

**Tilt is not cosmetic.** The panel is mounted at ~22° (roughly site latitude) facing
south. A horizontal panel in an Indian field silts up with dust within weeks and loses
most of its output; a tilted one sheds rain, and the rain washes it.

---

## 5. Battery — and why the obvious chemistry is wrong

**Autonomy target: 5 consecutive overcast days with no meaningful harvest.**

- 5 days × 5 Wh/day (conservative) = 25 Wh
- At 80% usable depth of discharge → **31 Wh minimum**
- Recommended: **40–50 Wh** for ageing and cold-start margin

⚠️ **Use LiFePO4, not the 18650 Li-ion in the original BOM.**

This matters more than it looks. A sealed dark enclosure in an Indian summer field
reaches internal temperatures well above ambient — plausibly 55–65 °C on a 45 °C day.
Standard Li-ion (LiCoO2 / NMC) degrades rapidly above ~45 °C, swells, and in a sealed
box that is both a reliability failure and a safety one.

| | Li-ion 18650 | **LiFePO4** |
|---|---|---|
| High-temperature tolerance | Poor above 45 °C | Good to ~60 °C |
| Cycle life | ~500 | 2,000–3,000 |
| Thermal runaway risk | Real | Substantially lower |
| Energy density | Higher | Lower — irrelevant here, we have mast space |
| Cost | Lower | Higher |

Energy density is the only axis where Li-ion wins, and it is the axis that does not
matter for a pole-mounted box. **This supersedes the 18650 selection in
[06_hardware_selection.md](06_hardware_selection.md) §4.**

---

## 6. Thermal

The same heat that rules out Li-ion also threatens the SoC and the image sensor.

| Measure | Note |
|---|---|
| Light-coloured or reflective enclosure | Absorbs far less than the dark box in the render |
| Sun shield / ventilated outer skin | Air gap between an outer shade and the sealed inner box |
| Duty-cycling as thermal management | The SoC is off ~99.6% of the time, so peak junction temperature is a transient, not a steady state — autonomy and thermal design solve each other |
| Gore-type pressure vent | A sealed box that heats and cools daily pumps moisture past its own gasket. A vent membrane equalises pressure while blocking liquid water. **Without this, IP65 alone will not prevent internal condensation.** |

---

## 7. What must be measured before any of this is claimed

| Unknown | How to close it | Blocks |
|---|---|---|
| **SoC active power** | SPIKE-0 profile job, or QCS6490 datasheet | The whole budget |
| Boot-to-first-inference time | Measure on target | Session energy |
| Enclosure internal temperature rise | Thermocouple in a sealed box in sun | Battery chemistry and lifetime |
| Real panel harvest under monsoon | Field logging across a season | Autonomy claim |
| Sentinel sleep current | Bench measurement | Minor |

Until the first row is measured, this document describes a **design**, not a validated
system. Say exactly that.

---

## 8. Revised BOM delta for autonomy

Changes from [06_hardware_selection.md](06_hardware_selection.md):

| Change | From | To | Reason |
|---|---|---|---|
| Compute node | Snapdragon phone | **Qualcomm SoM in a sealed enclosure** | A phone cannot be deployed unattended for a season |
| Battery | 1× 18650 Li-ion | **LiFePO4 pack, 40–50 Wh** | Heat tolerance in a sealed field enclosure |
| Panel | 6 V 2 W | **10–20 W, tilted ~22°** | Sized on monsoon worst case, not average |
| Power path | TP4056 linear charger | **MPPT solar charge controller** | Linear charging wastes a large fraction of harvest |
| — | — | **Load switch on the SoC rail** | The mechanism that makes duty-cycling real |
| — | — | **Pressure-equalising vent** | Prevents condensation from daily thermal cycling |
| Soil probe | 1 | **2, at 100 mm and 300 mm** | Separates "the surface got wet" from "the root zone has water" — the distinction the fusion engine depends on |
| Camera | Phone camera | **Sealed fixed camera with sun hood** | Unattended operation; hood mitigates the glare-driven domain shift |
