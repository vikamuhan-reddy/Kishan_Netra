# Wokwi Board — Component Reference

Every part on the simulation canvas: what it is, which pin, what it stands for, and what
to turn during a demo.

**Companion documents**
- [`docs/23_sensing_reference.md`](../../docs/23_sensing_reference.md) — the *physics*: how each sensor works and why the system needs it
- [`README.md`](README.md) — how to run the simulation
- This file — **what you are looking at on the canvas**

---

## 1. The five potentiometers

They are identical on screen and this is the question everyone asks. **Left to right along
the top row:**

| # | Position | Pin | Represents | Reads as | Watch for |
|---|---|---|---|---|---|
| 1 | far left | **GPIO 34** | Soil moisture — **surface, 100 mm** | 0–60 % | `surf` in serial |
| 2 | second | **GPIO 35** | Soil moisture — **root zone, 300 mm** | 0–60 % | `soil` in serial |
| 3 | middle | **GPIO 32** | **Soil pH** | 4.0–9.0 | `pH` in serial |
| 4 | fourth | **GPIO 39 (VN)** | **Electrical conductivity** | 0–5 dS/m | `EC` in serial |
| 5 | far right | **GPIO 33** | **Vision disease confidence** | 0.0–1.0 | risk `D:` in serial |

### Why potentiometers at all

Wokwi has no capacitive soil probe, no pH electrode, no EC meter and no camera. A
potentiometer is an honest stand-in because these are all **analog sensors read on an
ADC** — the firmware's code path is identical whether the voltage comes from a knob or a
probe. What is *not* simulated is the sensor's own physics and error behaviour, which is
why nothing here is a field measurement.

### Pot 2 is the important one

**The root-zone probe drives every irrigation decision.** Pot 1 (surface) is context only.

That split exists because a single probe confuses *"I watered the top"* with *"the crop has
water."* After a light shower the surface reads healthy while the root zone is still dry.
Turn pot 1 up and nothing happens to the decision; turn pot 2 down and the system acts.

### Thresholds each pot crosses

| Pot | Value | What changes |
|---|---|---|
| **2 — root moisture** | below **20 %** | Water stress climbs sharply → **IRRIGATE NOW** |
| | 28 % | Considered adequate; nitrogen explanations become plausible |
| | above **45 %** | Saturated → **WATERLOGGING** |
| **3 — pH** | outside **5.6 – 7.8** | Nutrient lock-out → contributes to **SOIL TEST** |
| **4 — EC** | below **0.8** | Nitrogen indication reads LOW (see the proxy warning below) |
| | above **3.0** | Salinity → **SALINITY CHECK** when moisture is adequate |
| **5 — vision** | see below | Disease risk, but **never on its own** |

### Pot 5 cannot raise an alarm by itself — by design

Disease risk is `vision_confidence × 55`, and the alert threshold is **60**. So even at
100 % confidence the camera reaches only 55 and **no alert fires**. It needs environmental
corroboration:

| Environment | Confidence needed for **INSPECT ZONE** |
|---|---|
| Humidity > 80 % **and** temp 26–34 °C | **0.48** |
| Humidity > 80 % only | 0.70 |
| Temp in band only | 0.88 |
| Neither | **impossible** — caps at 55 |

*(Verified against the firmware, not derived on paper.)*

This is the whole architecture expressed as one arithmetic constraint. A camera sees
symptoms but not cause, so it is not permitted to trigger an intervention alone.

---

## 2. Real sensor parts

These are actual Wokwi components with real behaviour, not stand-ins.

### DHT22 — air temperature and humidity
**Pin:** GPIO 15 (single-wire) · **Click it** in the sim to set temperature and humidity.

Does three separate jobs: scales water-stress urgency (22 % moisture is a different
problem at 43 °C than at 30 °C), triggers **HEAT STRESS** above 38 °C, and supplies the
environmental half of the disease call via humidity.

> Turn temperature to 44 °C → **HEAT STRESS**.
> Turn humidity above 80 % → disease risk gains +22, which is what lets pot 5 matter.

### DS18B20 — soil temperature
**Pin:** GPIO 14 (1-Wire, with the 4.7 kΩ pull-up beside it)

Read **asynchronously** — a conversion takes up to 750 ms and blocking on that would stall
the control loop, so it is triggered at the end of one cycle and read at the start of the
next. Its lag behind air temperature is a free cross-check on soil moisture: wet soil has
high thermal mass and swings less.

### HC-SR04 — water tank level
**Pins:** TRIG GPIO 26, ECHO GPIO 27 · **Click it** to set the measured distance.

Real time-of-flight: distance = (speed of sound × echo time) / 2, and the firmware
**compensates for speed of sound varying ~0.6 m/s per °C using the DHT22 reading** — one
sensor improving another.

Tank height is 50 cm, sensor at the top, so `level% = (50 − distance) / 50 × 100`.

> Distance **above ~42.5 cm** → level below 15 % → **TANK REFILL**, valve held shut.
> Set distance so no echo returns → **MANUAL CHECK — tank level unknown**. The system
> will not actuate on an unverifiable supply.

### Photoresistor — light level
**Pin:** GPIO 36 (VP) · **Click it** to change illumination.

The **image-quality gate**. Below 120 lux the frame is treated as unusable, the vision term
is discounted to 35 %, confidence drops, and the advisory reads *"Frame too dark —
discounted"* instead of quoting a number it shouldn't trust.

> A CNN handed a dark image doesn't say "I can't see" — it returns a confident distribution
> over classes it knows. This is a hardware mitigation for a machine-learning failure mode.

---

## 3. Buttons — fault and scenario injection

| Button | Colour | Pin | Effect |
|---|---|---|---|
| **RAIN** | blue | GPIO 4 | Toggles rain detected |
| **NET** | green | GPIO 5 | Cuts / restores the cloud link |
| **FAULT** | red | GPIO 13 | Cycles soil probe: GOOD → STUCK → FAILED → GOOD |

All three use `INPUT_PULLUP` with the far side to ground, so pressed reads LOW.

**RAIN** is a safety gate. With the soil dry it produces **DELAY IRRIGATION** — the weather
is already supplying water. With the soil saturated it contributes to **WATERLOGGING**.

**FAULT** demonstrates the two failure modes that matter:
- **STUCK** — the probe dies but keeps reporting its last value. Detected by loss of jitter
  (a live probe in soil always jitters; identical readings mean it died still reporting).
  This is the dangerous one: it *looks* like healthy data.
- **FAILED** — reading is `None`. **No value is substituted.** Confidence drops and the
  decision becomes **MANUAL CHECK**.

---

## 4. Outputs

| Part | Pin | Meaning |
|---|---|---|
| **Relay module** | GPIO 25 | The solenoid valve driver — the one controlled action in the system |
| **LED "VALVE"** (blue) | GPIO 18 | Mirrors the relay, visible at a glance |
| **LED "ALERT"** (red) | GPIO 19 | An advisory is active |
| **LED "EDGE"** (green) | GPIO 23 | **Heartbeat — deliberately independent of network state** |
| **Buzzer** | GPIO 2 | Chirps ~140 ms on a *new* alert only |
| **OLED SSD1306** | GPIO 21 SDA / 22 SCL | Local field display, 5 rotating pages |
| **LCD 20×4** (below the circuit) | same I²C bus, addr 0x27 | **Demo-only large mirror** of those pages — the OLED is unreadable across a room |

**The EDGE heartbeat is the point of the whole demo.** Press NET, watch the OLED show
`CLOUD:DN`, and watch that green LED keep blinking. Decisions never stop.

**The buzzer chirps once per new alert, not continuously.** A field device that sounds
constantly gets muted or unplugged, which destroys the alerting channel entirely.

### OLED pages (rotate every 3.2 s)

| Page | Name | Shows |
|---|---|---|
| 1 | DECISION | Decision + up to three reasons |
| 2 | SOIL+AIR | Soil (root/surface), air temp, soil temp, humidity |
| 3 | CHEMISTRY | pH, EC, nitrogen indication, lux, rain |
| 4 | RISK BANDS | Water, disease, pest, nutrient, flood |
| 5 | SUPPLY | Tank, flow delivered, queued records |

Top row is always `EDGE:OK` and `CLOUD:UP`/`CLOUD:DN` — the status line never depends on
the network.

Because a 128×64 panel is unreadable across a room, the same pages go to **two other
places**: a 20×4 character LCD sitting in the free canvas space below the circuit, and a
16-column ASCII box in the serial monitor:

```
   .----------------.   OLED 4/5  RISK BANDS
   |EDGE:OK CLOUD:DN|
   |----------------|
   |Water    HIGH   |
   |Disease  HIGH   |
   |Pest     LOW    |
   |Nutrient HIGH   |
   |Flood    LOW    |
   '----------------'
```

The LCD gets 20 columns, so it pairs two fields per row rather than dropping any:

```
+--------------------+
|SOIL+AIR 2/5    C:DN|
|Root 17.0%  Srf 24% |
|Air 32.0C Soil 28.4C|
|Humidity 84.0%      |
+--------------------+
```

**The LCD is a demonstration aid, not part of the product.** A field node carries the
small low-power panel; the 20×4 exists so a judge standing two metres away can read what
the node decided. All three renderers are driven from the same page description, so none
of them can disagree with the others.

---

## 5. Passive components

| Part | Value | Purpose |
|---|---|---|
| 3 × resistor | 220 Ω | LED current limiting |
| 1 × resistor | 4.7 kΩ | **1-Wire pull-up** for the DS18B20 — the bus idles high and devices pull it low; without this the sensor is never found |

---

## 6. Demo cheat-sheet

Each row produces a different decision. Watch the serial monitor below the diagram.

| Do this | Result |
|---|---|
| Turn **pot 2** down until `soil` reads under 20 % | **IRRIGATE NOW** — relay closes, VALVE LED on |
| While irrigating, set **HC-SR04** distance past ~43 cm | **TANK REFILL** — valve shuts. Won't run a pump dry |
| Turn **pot 2** above 45 % | **WATERLOGGING** — drainage advisory |
| Dry soil, then press **RAIN** | **DELAY IRRIGATION** — the rain is doing it |
| **Pot 4 (EC)** above 3.0 with `soil` ≥ 28 % | **SALINITY CHECK** — osmotic stress, not drought |
| **Pot 3 (pH)** above 7.8, **pot 4** below 0.8 | **SOIL TEST** — nutrient lock-out |
| **DHT22** temperature to 44 °C | **HEAT STRESS** |
| **DHT22** humidity > 80 %, then **pot 5** past ~0.5 | **INSPECT ZONE** — corroborated disease |
| Darken the **photoresistor**, keep pot 5 high | Alert disappears, `(dark)` appears — frame discounted |
| Press **FAULT** once | **MANUAL CHECK — soil probe stuck** |
| Press **FAULT** again | **MANUAL CHECK — soil probe unavailable**, `FAILED`, no substitute value |
| Press **NET** | `CLOUD:DN`, queue grows, **every decision continues** |
| Press **NET** again | Queue replays |

The last three rows are the ones worth rehearsing. They are the difference between a
dashboard and a field device.

---

## 7. What the board does not simulate

State these before someone asks:

1. **Nothing here is a field measurement.** Potentiometers and clickable sensors.
2. **Sensor physics is not modelled** — no drift, no hysteresis, no calibration error, no
   temperature dependence of the probes themselves.
3. **NPK is derived from EC**, exactly as cheap "NPK sensors" actually do. It is labelled a
   proxy in the telemetry (`"n_note": "EC-derived proxy, not ion-selective"`) and never
   produces a fertilizer prescription.
4. **Water flow is modelled in firmware**, not measured — Wokwi has no Hall-effect turbine
   part. A real node needs one to close the irrigation loop.
5. **No vision model runs on the ESP32.** Disease confidence is an input, arriving from
   pot 5 or over MQTT, exactly as it would arrive over UART from the QCS6490.
6. **This is not Qualcomm hardware.** It is an ESP32 simulation of the sentinel's low-power
   MCU. Qualcomm figures must come from an AI Hub profiling job.
7. **Agronomic thresholds are general cotton starting points**, not calibrated constants.
