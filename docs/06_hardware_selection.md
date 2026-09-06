# 06 — Hardware Selection

Evaluation of candidate hardware for the field node. Prices verified 2026-09-02;
sources linked. Estimated prices are marked **(est.)** and must be confirmed before any
cost claim is made to judges.

---

## 1. The constraint that determines the topology

**A Qualcomm Linux SoC board has no general-purpose analog input for user sensors.**

Capacitive soil moisture sensors — the correct choice for field deployment — output an
analog voltage. The RB3 Gen 2 expansion connectors expose SPI, UART, I2C, PCIe, USB and
MIPI, but not user ADC channels. This is the same situation as a Raspberry Pi, where the
sensor vendor's own documentation states an ADC converter is required, while an ESP32
reads the sensor directly.

So the soil sensors cannot simply be wired to the Qualcomm board. There are two ways out:

| Option | Assessment |
|---|---|
| **I²C ADC** (ADS1115) cabled to the board | Works, minimal parts. But every sensor must be physically cabled back to one box. |
| **MCU sensor node** (ESP32) reporting over the network | Extra component, but the sensors become independent nodes. |

**We choose the MCU sensor node, and not merely as a workaround** — it is the correct
field topology for four independent reasons, set out in §2.

---

## 2. Recommended topology: two tiers

```
   TIER 1 — sensor nodes (many, cheap, battery + solar)
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │ ESP32 node   │  │ ESP32 node   │  │ ESP32 node   │
   │ soil moisture│  │ soil moisture│  │ soil moisture│
   │ temp/humidity│  │ temp/humidity│  │ temp/humidity│
   │ deep sleep   │  │ deep sleep   │  │ deep sleep   │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │  Wi-Fi / LoRa   │                 │
          └─────────────────┼─────────────────┘
                            ▼
   TIER 2 — compute node (one, shared)
   ┌──────────────────────────────────────────────┐
   │  Qualcomm QCS6490                            │
   │  camera → vision model            [NPU]      │
   │  MQTT broker ← sensor nodes       [CPU]      │
   │  fusion engine                    [CPU]      │
   │  local queue + advisory                      │
   └──────────────────────────────────────────────┘
```

**Why two tiers is right, not a compromise:**

1. **Spatial coverage.** Soil moisture varies across a field. A single probe beside the
   compute box measures one spot and generalizes badly. Cabling ten probes back to one
   enclosure across an acre is not a field-viable install.
2. **Power.** An ESP32 in deep sleep draws microamps between readings and runs for months
   on a small battery and panel. A Snapdragon SoC cannot duty-cycle that aggressively
   while remaining responsive.
3. **Unit economics, and this is the decisive one.** A ₹50,000 compute node per
   smallholder plot is impossible. One compute node per cooperative, plus ₹3,000 sensor
   nodes per plot, is plausible — and it maps *exactly* onto the PS's own scaling
   requirement (D20: smallholder → cooperative → enterprise).
4. **It makes MQTT genuinely justified.** In a single-box design a message broker is
   decorative architecture. With distributed nodes it is the actual transport.

The compute node is where the money and the Qualcomm relevance sit; the sensor tier is
deliberately cheap and replaceable.

---

## 3. Tier 2 — compute node candidates

| Candidate | AI compute | Camera | Sensor I/O | Connectivity | Cost | Qualcomm proof | Verdict |
|---|---|---|---|---|---|---|---|
| **RB3 Gen 2 Vision Kit** | Hexagon 770 NPU, up to 12 dense TOPS | IMX577 12MP + OV9282 1MP included | SPI/UART/I²C/PCIe/USB/MIPI, **no user ADC** | Wi-Fi 6E, BT 5.2, **no cellular** | $599 US · **₹50,000 India** | ✅ strongest | **Primary, next round** |
| **RB3 Gen 2 Core Kit** | same | none included | same | same | $399 US | ✅ strong | Only if a camera is sourced separately |
| **RB3 Gen 2 Lite** | QCS5430, lower | varies | same | same | ₹50,000 India | ✅ | No cost advantage in India — skip |
| **Snapdragon Android phone** | Snapdragon NPU | ✅ built in, good | ❌ none — needs Tier 1 anyway | ✅ Wi-Fi **+ cellular = SMS** | **₹0 — already owned** | ✅ real Qualcomm silicon | **Recommended for this round** |
| **Raspberry Pi 5** | ❌ no NPU | add-on | no ADC either | Wi-Fi, no cellular | ~₹8,000 | ❌ none | Rejected |
| **NVIDIA Jetson Orin Nano** | strong GPU | add-on | GPIO | Wi-Fi | ~₹40,000 | ❌ **wrong sponsor** | Rejected |

### On the Snapdragon phone

This deserves more attention than it usually gets. A mid-range Snapdragon Android phone
is **real Qualcomm silicon with a real NPU**, and it already has a camera, a display, a
battery, and — critically — **a cellular radio**.

The RB3 Gen 2 has no onboard cellular, yet the PS explicitly names SMS as a delivery
channel (D17). A phone solves that natively. It is also free, available today, and
requires no import.

Its weakness is real: no sensor I/O, no weatherproofing, and it is not a "field device"
in the way a judge pictures one. But **the sensor tier is separate anyway**, which
removes most of that objection.

### On Jetson

Technically capable and often the reflexive choice for edge vision. It is the wrong
answer here for a non-technical reason that dominates: **NVIDIA is not the sponsor.** The
entire Qualcomm-relevance argument evaporates. Note this explicitly in the deck if asked.

---

## 4. Tier 1 — sensor node components

| Component | Selected part | Why | Price (India) | Source |
|---|---|---|---|---|
| MCU + radio | **ESP32 + LoRa SX1278, OLED** | Built-in ADC reads the analog soil sensor directly; Wi-Fi for short range, LoRa for field range; deep sleep | **₹1,650–2,899** | [Robu.in](https://robu.in/product/esp32-lora-sx1278-0-96-inch-blue-oled-display-bt-wifi-module-for-arduino/) |
| Soil moisture | **Capacitive sensor V1.2 / V2.0** | See §5 — this choice is not optional | **₹83** | [Robokits](https://robokits.co.in/sensors/water-moisture/capacitive-soil-moisture-sensor-v1.2) |
| Temp + humidity | **SHT31** (I²C, outdoor variant) | Higher accuracy and far better long-term stability than DHT22; I²C avoids the DHT single-wire timing fragility | ~₹700 **(est.)** | [DFRobot SEN0385](https://wiki.dfrobot.com/sen0385/) |
| Power | 6V 2W solar panel + 18650 cell + TP4056 charger | Months of unattended operation with deep sleep | ~₹600 **(est.)** | — |
| Enclosure | IP65 junction box + cable glands | Monsoon, dust, insects | ~₹400 **(est.)** | — |
| **Per-node total** | | | **≈ ₹3,400–4,700** | |

---

## 5. Soil moisture sensor: capacitive, not resistive

This is the single most consequential component choice in Tier 1, and it is not close.

| | Resistive | Capacitive |
|---|---|---|
| Electrode exposure | Bare metal in wet soil | Sealed, no exposed electrodes |
| Corrosion | Degrades in weeks to months | Long service life |
| Salinity / fertilizer interference | **20–40% VWC error** in fertilized or saline soil | Resistant |
| Accuracy | Lower | Matches secondary-standard sensors **after soil-specific calibration** |
| Cost | Cheaper | ₹83 |

Resistive sensors fail specifically in **fertilized soil** — which is every field this
system is deployed in. A ₹40 saving that produces 20–40% VWC error would corrupt the
exact signal our fusion engine depends on to distinguish water stress from nitrogen
deficiency. The entire differentiator rests on this measurement being trustworthy.

⚠️ **Calibration caveat, and it is important.** The literature is clear that low-cost
capacitive sensors match good sensors *after soil-specific calibration* — not out of the
box. This directly corroborates the warning in
[09_sensor_fusion.md](09_sensor_fusion.md) §4 that our moisture thresholds are
uncalibrated. **We must not claim field accuracy until per-soil calibration is done.**

---

## 6. Connectivity and the SMS problem

The RB3 Gen 2 provides Wi-Fi 6E and Bluetooth 5.2 and **no cellular radio**, but PS D17
names SMS as a delivery channel. Options:

| Option | Cost | Assessment |
|---|---|---|
| **Snapdragon phone as the compute node** | ₹0 | Cellular is native. Solves D17 for free. **Best for this round.** |
| USB LTE dongle on the board | ~₹1,500 **(est.)** | Straightforward; adds power draw |
| LoRa to a village gateway with one cellular uplink | varies | Best at cooperative scale — one SIM serves many farms |
| Store-and-forward over intermittent Wi-Fi | ₹0 | Already required by the offline design; insufficient alone for SMS |

The LoRa-to-gateway option is the most credible *field* answer and reinforces the
two-tier economics: one connectivity subscription amortized across a cooperative rather
than one per farmer.

---

## 7. Camera

| Option | Cost | Notes |
|---|---|---|
| IMX577 12MP, included in Vision Kit | in kit price | Best quality; MIPI CSI; needs the Vision Kit not the Core Kit |
| Phone camera | ₹0 | Good sensor, autofocus, already integrated |
| USB webcam | ~₹1,200 **(est.)** | Works with Core Kit; lower quality, easiest to source |

Leaf-lesion diagnosis needs close focus and reasonable resolution. Autofocus matters more
than megapixels — which is another point in the phone's favour for this round.

---

## 8. Cost summary by deployment tier

| Tier | Configuration | Hardware cost |
|---|---|---|
| **This round (demo)** | Snapdragon phone (owned) + 2 ESP32 sensor nodes | **≈ ₹7,000–9,500** |
| **Smallholder** (shared) | 1 compute node per cooperative ÷ ~20 farms + 1 sensor node per plot | **≈ ₹6,000 per farm** |
| **Cooperative** | 1 RB3 Gen 2 Vision Kit + 20 sensor nodes | **≈ ₹1,20,000** |
| **Enterprise** | Multiple compute nodes + gateway + fleet management | scales linearly |

**The most expensive component is the compute node (₹50,000), by an order of magnitude.**
The lower-cost alternative is exactly the tiering above: share it across a cooperative,
or use a Snapdragon phone where a ruggedized box is not required.

⚠️ Note the India price premium: the Core Kit is **$399 (~₹35,000) in the US** but the
kits list at **₹50,000 in India** ([IndiaMART, Chennai](https://www.indiamart.com/proddetail/thundercomm-qualcomm-rb3-gen-2-development-kit-2854743101897.html)); also stocked by
[Fab.to.Lab](https://www.fabtolab.com/96boards-qualcomm-rb3-gen-2-development-kit-core-vision). Quote the India figure, not the US one.

---

## 9. Availability risk

| Risk | Assessment |
|---|---|
| RB3 Gen 2 lead time to India | **Domestically stocked** (Chennai, Fab.to.Lab), so import delay is avoidable — but stock is thin and unconfirmed |
| Budget | ₹50,000 is significant for a student team; not committed this round |
| ESP32 / sensors | Widely stocked, next-day delivery, negligible risk |

**Mitigation:** nothing on the critical path this round depends on the RB3 Gen 2.
Qualcomm evidence comes from AI Hub hosted devices (Level B), and the phone provides a
physical Snapdragon target if one is wanted. See
[decision_log.md](decision_log.md) DR-008.
