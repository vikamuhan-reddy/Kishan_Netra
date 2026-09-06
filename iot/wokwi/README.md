# Wokwi simulation — Smart Farm Sentinel MCU

Runnable ESP32 firmware for the sentinel's **always-on MCU**, wired up in
[Wokwi](https://wokwi.com). This is the same decision logic as
[`iot/fusion/engine.py`](../fusion/engine.py) and the
[digital twin](../../viz/sentinel_twin.html), compiled for a real microcontroller.

---

## What this is, architecturally

The sentinel has two processors, and this sketch is the small one:

| | Role | In this sim |
|---|---|---|
| **ESP32** | **Always on**, milliwatts. Sensors, validation, history, risk scoring, irrigation decision, local display. Decides when vision is worth waking. | ✅ this firmware |
| **QCS6490** | **Off by default.** Wakes on the MCU's trigger, runs the crop-disease model on the NPU, returns a result over UART. | ⬜ modelled as an input |

**This firmware does not run a CNN and does not pretend to.** Vision confidence is an
*input*, exactly as it is on the real board — either from the `vision` potentiometer or
pushed over serial. That is the honest representation, and it is also the interface a
judge will ask about.

Why the split: an always-on application SoC is not solar-feasible at smallholder cost.
Duty-cycling it is what makes the power budget close — see
[`docs/22_power_autonomy.md`](../../docs/22_power_autonomy.md).

---

## Two firmware variants

A Wokwi project is either Arduino or MicroPython, so each lives in its own folder with
its own copy of the wiring. **They behave identically** — same thresholds, same fault
handling, same decision order. All ten agronomic constants are verified equal.

| | Folder | Sensors | Networking | Use it when |
|---|---|---|---|---|
| **Arduino C++** | [`arduino/`](arduino/) | 6 channels | none — modelled | You want a demo nothing external can break |
| **MicroPython** | [`micropython/`](micropython/) | **12 channels** | **live MQTT** | You want the full sensing stack and a real IoT showcase |

The MicroPython build is the fuller one: it adds soil temperature, ultrasonic tank level,
pH, EC, an EC-derived nitrogen indication, modelled flow, a relay-driven valve and a
buzzer, and it prints a **sensing-stack inventory at boot** explaining what each channel
is and why it's on the mast.

Keeping both honest matters: the Python reference engine, the MicroPython firmware and
the C++ firmware are three expressions of one decision policy. If they drift, a demo
starts disagreeing with the documentation.

### Running the Arduino version

1. [wokwi.com](https://wokwi.com) → **New Project** → **ESP32**
2. Replace `diagram.json` and `sketch.ino` with the copies in `arduino/`
3. **Library Manager** tab → add the four libraries in [`arduino/libraries.txt`](arduino/libraries.txt)
4. ▶ — the OLED boots and the serial monitor starts reporting

### Running the MicroPython version — with live MQTT

1. [wokwi.com](https://wokwi.com) → **New Project** → **ESP32** → **MicroPython**
2. Replace `diagram.json` with the copy in `micropython/`
3. Paste [`micropython/main.py`](micropython/main.py) as `main.py`
4. ▶ — **no extra files needed.** The SSD1306 driver is embedded in `main.py`.

> **Why the driver is embedded.** MicroPython doesn't bundle one and Wokwi has no library
> manager for MicroPython, so depending on an external `ssd1306.py` meant the display
> silently failed for anyone who forgot to add it. ~50 lines of command sequence removes
> that failure mode; the drawing comes free from the built-in `framebuf`.
>
> On boot the firmware prints the I²C scan — `[i2c] devices found: ['0x3c']` — so if the
> OLED is miswired you see it immediately instead of guessing.

### What you should see, and when

The **serial monitor is the panel below the diagram** in Wokwi — if it's collapsed, drag
its divider up.

**The OLED is mirrored twice** — once onto a 20×4 character LCD sitting in the empty
canvas space below the circuit (same I²C bus, address 0x27, so it costs two wires), and
once into the monitor as text. The small panel is what a real node would carry; the big
one is there so the display is legible in a screenshot or from the back of a room.

**The monitor mirror.** Wokwi's display is 128×64 px and unreadable in
a screenshot, so every page the node paints on the glass is also printed as a framed
16-column block — the same width as the real screen, so what you read in the log is
literally what a farmer would read in the field:

```
   .----------------.   OLED 1/5  DECISION
   |EDGE:OK CLOUD:DN|
   |----------------|
   |IRRIGATE NOW    |
   |zone water stres|
   |----------------|
   |-Moisture 17% be|
   |-Trend -1.40 %/h|
   |-Air temp 32C   |
   '----------------'
```

One function, `screen_rows()`, describes a page and both renderers consume it, so the
monitor text cannot drift away from the glass. The block reprints on every page rotation
(3.2 s), which also means the pages advance on the display even between the 2-second
sensing cycles.

| Time | Serial | OLED |
|---|---|---|
| ~0 s | Banner, then the 12-channel sensing stack | — |
| ~1 s | `[i2c] devices found: ['0x3c']`, `[display] SSD1306 ready` | splash |
| **~2 s** | **First reading and decision** | **live data** |
| ~3 s | `first decision made locally - now raising the optional cloud link` | live |
| ~3–11 s | WiFi dots, then MQTT connect or a clean timeout | live, still updating |

**The loop runs before the network does — deliberately.** An earlier version connected
WiFi at boot, which left the node blind for the first ~12 seconds while the one thing it
exists to prove sat waiting on a link. Now the first decision is made and displayed before
anything touches the radio, and the cloud is raised afterwards (retrying every 30 s if it
fails). If WiFi never comes up, the serial says `no network - the node runs anyway, this
is the point` and everything else carries on.

Every optional import is guarded too. A firmware build missing `onewire` or `umqtt`
prints what it lost and keeps running, rather than dying at import with a blank screen.

### Testing the logic without a board

```bash
cd micropython
python test_firmware.py main.py        # decision logic, 15 field states
python check_micropython.py main.py    # portability
```

**Both, always.** `test_firmware.py` runs the firmware on CPython, which is
excellent for the decision engine and useless for portability: CPython has
`str.ljust`, MicroPython does not, and the difference only surfaces as an
`AttributeError` on the board halfway through drawing a screen. That bug cost a
demo once. `check_micropython.py` scans for the constructs the ESP32 port is
known to omit — the missing `str` methods, absent modules, f-strings, nested
format widths, and the two-argument `next()`.

The firmware can't be unit-tested on the device, but its decision logic is pure Python.
[`test_firmware.py`](micropython/test_firmware.py) stubs the MicroPython modules and drives
`compute_risks`/`decide` through 15 field states — dry, saturated, saline, pH lock-out,
failed probe, stuck probe, dead tank sensor, dark frame.

**It has already caught one real bug:** a waterlogged field (47% moisture, raining) was
reporting *"no action — all signals normal."* Saturation is now decided by the soil rather
than the weather, and there is a distinct **WATERLOGGING** advisory. Rain on dry ground is
still good news, not a hazard.

This variant connects to `Wokwi-GUEST` and publishes to the HiveMQ public broker
`broker.mqttdashboard.com`:

| Topic | Direction |
|---|---|
| `sih26180/sentinel-01/telemetry` | published — sensor state, fault status, trend |
| `sih26180/sentinel-01/decision` | published — advisory, reasons, risk scores, valve state |
| `sih26180/sentinel-01/vision` | **subscribed** — the edge AI module posts its result here |

**To watch and drive it:** open the
[HiveMQ websocket client](http://www.hivemq.com/demos/websocket-client/) → Connect →
subscribe to `sih26180/sentinel-01/#`.

To inject a vision result — this is what the Qualcomm module does after an NPU inference —
publish to `sih26180/sentinel-01/vision`:

```json
{"disease": 0.85, "pests": 6}
```

Disease risk jumps and the decision becomes **INSPECT ZONE**, advisory only. The
potentiometer takes over again after 20 seconds, so the board still demonstrates with no
network at all.

> ⚠️ The broker is **public and unauthenticated**, which is fine for a demo and wrong for a
> deployment. Anyone can read your telemetry or publish a fake vision result to your topic.
> A real fleet needs per-device credentials and TLS.

**MQTT is deliberately off the decision path.** Every publish happens *after* the decision
is already made; the radio is not touched until the node has already decided and displayed
a result once; WiFi then has an 8-second timeout and retries every 30 s; and the queue is
bounded at 50 records — a field node has finite storage, so old telemetry is dropped
oldest-first rather than pretending it all survives.

---

## Wiring — and why each part is on the mast

> **📘 What am I looking at? → [`COMPONENTS.md`](COMPONENTS.md)** — every part on the
> canvas, which of the five identical potentiometers is which, and a demo cheat-sheet.
>
> **📗 How does each sensor work? → [`docs/23_sensing_reference.md`](../../docs/23_sensing_reference.md)**
> — the physical operating principle of every sensor, why the system needs it, what it
> cannot tell you, and the decision that breaks without it.

### MicroPython — full stack (12 channels)

| Part | Pin | Represents | Why it's here |
|---|---|---|---|
| Pot `soilB` | 35 | Soil moisture, **root zone (300 mm)** | *Can the plant drink?* **Drives the decision** |
| Pot `soilA` | 34 | Soil moisture, surface (100 mm) | *Did water arrive?* Responds in minutes to rain |
| **DS18B20** | 14 | Soil temperature (1-Wire) | Root activity; its lag behind air temp cross-checks moisture |
| DHT22 | 15 | Air temperature + humidity | Evaporative demand, heat stress, infection window |
| **HC-SR04** | 26/27 | Water tank level (ultrasonic) | Pump-safety gate — a dry run destroys the pump |
| Pot `ph` | 32 | Soil pH | Nutrient *availability* — nutrients can be present and locked out |
| Pot `ec` | 39 (VN) | Electrical conductivity | Salinity and osmotic stress: wilting in wet soil |
| LDR | 36 (VP) | Light level | **Image-quality gate** — a dark frame is not evidence |
| Pot `vision` | 33 | Disease confidence from the edge AI module | Symptom evidence, from the QCS6490 |
| Btn **RAIN** | 4 | Rain detector | Suppresses irrigation into saturated soil |
| Btn **NET** | 5 | Cut / restore the cloud link | Proves decisions are local |
| Btn **FAULT** | 13 | Probe fault: none → stuck → failed | Proves faults are detected, not absorbed |
| **Relay** | 25 | Solenoid valve driver | The one controlled action |
| **Buzzer** | 2 | Local audible alert | Chirps on *new* alerts only |
| LEDs | 18/19/23 | Valve · Alert · **Edge heartbeat** | The heartbeat never stops when the network drops |
| OLED | 21/22 | Local field display, 5 pages | The farmer's readout works with no connectivity |

⚠️ **Every analog channel is on ADC1 (GPIO 32–39).** ADC2 pins cannot be read while WiFi
is active on the ESP32 — a real constraint that would fail silently the moment MQTT came
up, so the pin allocation avoids it entirely.

Nitrogen, phosphorus and potassium are **derived from EC**, not measured — see the warning
below. Water flow is **modelled in firmware** from valve state; no Wokwi part exists for a
Hall-effect turbine.

The Arduino build uses the reduced 6-channel wiring in [`arduino/diagram.json`](arduino/diagram.json).

### The three choices worth defending

**Two soil probes at two depths is not redundancy.** A single probe confuses *"I watered
the top"* with *"the crop has water."* After a light shower the shallow probe reads healthy
while the root zone is still dry — and a one-probe system would say everything is fine
while the crop stays in stress.

**Capacitive, never resistive.** Resistive probes pass current between bare electrodes, so
they corrode within months and carry **20–40% VWC error in fertilized or saline soil** —
that is, in every field we'd deploy in. That error wouldn't degrade gracefully; it would
*invert* the water-stress vs nitrogen-deficiency call and send the farmer to buy the wrong
input.

**The LDR looks decorative and isn't.** A CNN handed an underexposed image doesn't return
"I can't see" — it returns a confident distribution over classes it knows. Below 120 lux
the firmware discounts the vision term to 35% and the advisory reads *"Frame too dark —
discounted."* It's a hardware mitigation for a machine-learning failure mode.

### ⚠️ The NPK warning — say this before a judge does

Cheap "NPK sensors" sold for low-cost agriculture **do not perform ion-selective
measurement** of nitrogen, phosphorus or potassium. They measure bulk electrical
conductivity and apply a vendor correlation. Those correlations are soil-specific,
uncalibrated, and not traceable to a laboratory soil test.

This firmware models exactly that — `npk_proxy()` derives the nitrogen indication from EC
and the telemetry payload carries `"n_note": "EC-derived proxy, not ion-selective"`. It
feeds a nutrient *risk* score and an advisory to soil-test. It never produces a fertilizer
prescription.

**The system's real nitrogen reasoning doesn't depend on it at all.** It works by
exclusion: chlorosis under adequate, stable soil moisture is not explained by water. That
inference rests on the moisture probe, which we can defend.

### What the boot output gives you

The MicroPython build prints a **sensing-stack inventory** before it starts — every
channel with its operating principle and the decision it enables — and publishes the same
structure to `sih26180/sentinel-01/inventory`. The simulation explains itself rather than
needing a narrator:

```
  Soil moisture (root 300mm)  [%]
    how : Capacitive - soil dielectric permittivity (water 80, dry soil 4, air 1)
    why : PRIMARY SIGNAL. Separates water stress from nitrogen deficiency.

  Light level  [lux]
    how : Photoconductivity: photons free carriers, resistance falls
    why : IMAGE-QUALITY GATE. A dark frame is not evidence.
```

### Two new decision branches the extra sensors unlock

**SALINITY CHECK** — high EC with *adequate* moisture. The plant is wilting because it
cannot osmotically extract water, not because the soil is dry. Irrigating would waste water
and concentrate salts further. Without EC this looks like a sensor fault.

**MANUAL CHECK — tank level unknown** — the ultrasonic sensor returns no echo. The supply
is unverifiable, so the valve stays shut. The system does not actuate on an unknown supply.

---

## Demo script — about 90 seconds

| # | Do this | What to point at |
|---|---|---|
| 1 | Let it run | OLED cycles five pages, each one mirrored into the serial monitor. EDGE heartbeat blinking. |
| 2 | Turn `soilB` **down** below ~22% | Water stress climbs, decision becomes **IRRIGATE NOW**, VALVE LED lights, and the OLED lists the reasons — moisture, trend, temperature, rain. |
| 3 | Turn `tank` **down** below 15% | Decision flips to **TANK REFILL**, valve shuts. The system will not run a pump dry. |
| 4 | Restore tank, then press **RAIN** | Decision becomes **DELAY IRRIGATION**. It will not irrigate into saturated soil. |
| 5 | Press **NET** | Serial says the link is down. **Everything keeps deciding.** Page 4 shows records queueing locally. Press again — the queue replays. |
| 6 | Press **FAULT** once (STUCK) | The probe freezes. The detector notices the readings stopped changing and returns **MANUAL CHECK — soil probe stuck**, naming the part to service. |
| 7 | Press **FAULT** again (FAILED) | Reading shows `FAILED`. **No value is substituted**, confidence drops, decision is **MANUAL CHECK**. |
| 8 | Feed a vision result — Arduino: send `V,0.85,6` in the monitor; MicroPython: turn the `vision` pot up, or publish `{"disease":0.85,"pests":6}` to the vision topic | Result arrives from the "edge AI module". With humidity above 80% the disease risk goes HIGH → **INSPECT ZONE**, advisory only, no chemical prescribed. |

Steps 5–7 are the ones worth rehearsing. They are the difference between a dashboard and
a field device.

---

## The vision interface

This is the real integration point with the Qualcomm module.

**Arduino build** — a line on the serial port:

```
V,<disease_confidence 0..1>,<pest_count>

V,0.85,6      disease 85%, six pests detected
V,0.05,0      clean frame
```

**MicroPython build** — a JSON message on MQTT, because that build has a live link and
reading `stdin` under Wokwi's MicroPython blocks the loop:

```
topic: <base>/vision
{"disease": 0.85, "pests": 6}
```

Either way a message holds for 15–20 seconds, then the firmware falls back to the
`vision` potentiometer so the board still demonstrates standalone. Replacing the mock with
real inference means writing to this one interface — nothing else in the firmware
changes.

---

## Design decisions the code makes deliberately

- **Implausible values are faults, not data.** A reading outside its physical range is
  treated as missing. A floating ADC pin reading 247% moisture is a fault; acting on it
  would be worse than having no reading.
- **A stuck probe is detected by loss of noise.** A live capacitive probe in soil always
  jitters; bit-identical readings mean it died while still reporting. Since Wokwi's ADC is
  mathematically ideal, `dither()` adds back the jitter a real probe has, so the detector
  exercises the same signal property it would in the field.
- **Trend returns `NAN`, never a fabricated zero.** A false "stable" would read as *not
  water-driven* and skew the diagnosis toward a nutrient explanation.
- **The tank gate is hard.** Below 15% the valve stays shut regardless of crop stress.
- **Advisory, not prescriptive.** Disease and pest findings recommend inspection. The
  firmware never prescribes a chemical. The valve is the single controlled action.

---

## Honest limits

- Sensor values come from potentiometers. **Nothing here is a field measurement.**
- Agronomic thresholds are general cotton starting points, **not calibrated constants**.
  No field-accuracy claim is defensible until per-soil calibration is done.
- The ESP32 does no vision. Disease confidence is simulated input.
- **This is not running on Qualcomm silicon.** It is an ESP32 simulation of the sentinel's
  low-power MCU. Qualcomm-specific numbers must come from an AI Hub profiling job.
- **The Arduino variant has no networking**, by choice: the cloud link is modelled with the
  NET button and a local queue, so the demo cannot be broken by a flaky gateway. The
  MicroPython variant uses real MQTT, which is the better *IoT* showcase but adds a live
  dependency. Pick the one that suits the room — they make the same argument.
- The MQTT broker is public and unauthenticated. Fine for a demo, wrong for a fleet.
