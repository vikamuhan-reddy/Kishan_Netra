# 07 — Hardware Decision

Decision summary. Full evaluation in [06_hardware_selection.md](06_hardware_selection.md).

---

> ## ⚠️ Revision — autonomy requirement
>
> An earlier version of this document recommended a **Snapdragon Android phone as the
> product's compute node**. That was wrong and is withdrawn.
>
> The phone was chosen for cost, for its NPU, and because its cellular radio solved SMS
> delivery. All of that is true, and none of it matters: **a phone is not autonomous
> hardware.** It must be placed and retrieved by a person, it is not weather-sealed, it
> cannot survive a season in a field, and it cannot trigger its own captures.
>
> The product is a device installed once and left for a season. The phone remains useful
> as a *validation shortcut* — a real Snapdragon NPU to run inference on — but it is not
> the product, and it must never be presented as one.
>
> Power budgeting and duty-cycling follow from this and are now first-class concerns:
> see [22_power_autonomy.md](22_power_autonomy.md).

## Selected platform

**An autonomous two-tier field station.** Installed once, solar-powered, self-triggering.

| Tier | Role | Part |
|---|---|---|
| **Sentinel** | Always on, milliwatts. Reads soil and air sensors every 15 min, decides when a capture is warranted, and switches the compute rail. | ESP32-class MCU + LoRa |
| **Compute** | **Off by default.** Wakes on the sentinel's trigger, captures, runs NPU inference, fuses, transmits, powers down. | Qualcomm QCS6490 (RB3 Gen 2 class) in a sealed enclosure |
| **Power** | 10–20 W tilted panel, MPPT controller, **LiFePO4** 40–50 Wh, load switch on the SoC rail | — |
| **Sensing** | 2 × capacitive soil probes at 100 mm and 300 mm, SHT31 air temp/humidity | — |
| **Vision** | Sealed fixed camera with sun hood, aimed 35° down at the canopy | IMX577 class |

**Why the SoC is off by default:** at an assumed 6 W continuous it would need ~144 Wh/day,
implying a 60–80 W panel and a 300 Wh battery — several times the cost of the compute
itself. Duty-cycled to four ~85 s sessions per day the whole station runs on an estimated
**0.8 Wh/day**. Autonomy is not a feature bolted on; it is what makes the bill of
materials possible.

**Validation configuration this round** (not the product): AI Hub hosted devices for
Qualcomm measurements, plus a Snapdragon phone if a physical NPU is wanted, plus 2 ESP32
sensor nodes ≈ **₹7,000–9,500**.

---

## Why selected

**1. The board cannot read the soil sensors directly.** A Qualcomm Linux SoC exposes
I²C, SPI, UART, PCIe, USB and MIPI — but no user analog input. Capacitive soil moisture
sensors are analog. An ESP32 reads them natively. The sensor tier is therefore required
regardless of which compute node we pick, so we designed around it rather than bolting
on an ADC.

**2. Two tiers is the only affordable deployment model.** A ₹50,000 compute node per
smallholder plot is not a product. One shared across a cooperative plus ₹3,400 nodes per
plot is — and it maps directly onto the PS's own scaling requirement (D20: smallholder →
cooperative → enterprise). The hardware topology *is* the business model.

**3. Sensors must be spatially distributed.** Soil moisture varies across a field. One
probe beside the compute box measures one spot and generalizes badly; cabling ten probes
across an acre back to one enclosure is not a field-viable install.

**4. Power.** ESP32 deep sleep draws microamps between readings — months of unattended
operation on a small panel and cell. A Snapdragon SoC cannot duty-cycle that hard while
staying responsive.

**5. The phone solves the SMS problem for free.** The RB3 Gen 2 has Wi-Fi 6E and
Bluetooth but **no cellular radio**, while PS D17 names SMS as a delivery channel. A
Snapdragon phone has a cellular radio, a camera, a display, a battery and a real NPU, at
zero cost and zero lead time.

---

## Why alternatives were rejected

| Rejected | Reason |
|---|---|
| **Raspberry Pi 5** | No NPU, no analog input either, and — decisively — **no Qualcomm relevance**. The entire sponsor argument disappears. |
| **NVIDIA Jetson Orin Nano** | Technically capable and the reflexive edge-vision choice. Rejected because **NVIDIA is not the sponsor**. Same objection as the Pi, for the same reason. |
| **RB3 Gen 2 Lite** | Lists at the same ₹50,000 in India as the full kit with lower capability. No advantage. |
| **RB3 Gen 2 Core Kit** | $399 vs $599, but ships without cameras. By the time a camera is sourced the Vision Kit is better value. |
| **Resistive soil moisture sensor** | Corrodes in months and carries **20–40% VWC error in fertilized or saline soil** — i.e. in every field we would deploy in. It would corrupt the exact signal the fusion engine depends on, to save ₹40. |
| **DHT22 for temp/humidity** | Cheaper, but poorer accuracy and long-term stability, and its single-wire timing protocol is fragile. SHT31 over I²C for ~₹600 more. |
| **Single-tier design** (everything cabled to one box) | Requires an ADC, cannot cover a field spatially, cannot duty-cycle power, and produces unaffordable per-plot economics. |

---

## What we can actually prove

Stated by validation level, per [00_initial_technical_assessment.md](00_initial_technical_assessment.md) §5.

| Claim | Level | Status |
|---|---|---|
| Inference latency, memory, compute-unit split on Snapdragon silicon | **B** — AI Hub hosted device | ⏳ SPIKE-0 not yet run |
| Fusion logic, degraded-mode behaviour, advisory generation | **A** — simulation | ✅ 12 tests passing |
| On-device inference on a physical Snapdragon NPU | **C** — phone | ⬜ available if we choose to |
| Real soil probe readings in real soil | **C** — sensor node | ⬜ not this round |
| Power consumption in the field | **C** | ❌ cannot claim |
| Field accuracy of soil moisture readings | **C** + calibration | ❌ **cannot claim — see below** |

⚠️ **The calibration caveat.** Low-cost capacitive sensors match good sensors only *after
soil-specific calibration*. Until that is done, no field-accuracy claim about moisture is
defensible — which directly corroborates the uncalibrated-threshold warning in
[09_sensor_fusion.md](09_sensor_fusion.md) §4. Two independent parts of this system land
on the same limitation, and we should say so plainly rather than let a judge connect it.

---

## Hardware availability risk

| Risk | Severity | Note |
|---|---|---|
| RB3 Gen 2 stock in India | MEDIUM | **Domestically stocked** in Chennai and via Fab.to.Lab, so import delay is avoidable — but availability is thin and unconfirmed by us |
| ₹50,000 budget | MEDIUM | Significant for a student team; deliberately not committed this round |
| India price premium | LOW but note it | $399 (~₹35,000) US vs ₹50,000 India. **Quote the India figure.** |
| ESP32, sensors, power parts | LOW | Widely stocked, next-day delivery |

---

## Fallback plan

Ordered by preference, each independently sufficient for this round:

1. **Primary — AI Hub hosted device (Level B).** Free, no hardware, real Snapdragon
   silicon. This is the entire Qualcomm proof and requires nothing to arrive.
2. **If a physical target is wanted — Snapdragon phone (Level C).** Free, owned, has
   camera, NPU and cellular.
3. **If sensor nodes are wanted — ESP32 tier.** ≈₹3,400 each, next-day delivery.
4. **Only if funded and selected — RB3 Gen 2 Vision Kit.** Best story, but never on the
   critical path.

**Nothing in the current plan blocks on hardware arriving.** That is deliberate: a
hackathon plan whose demo depends on a ₹50,000 import landing on time is a plan with a
single point of failure the team does not control.
