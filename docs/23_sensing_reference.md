# 23 — Sensing Reference

Every sensor on the sentinel: what it measures, **how it physically works**, why this
system needs it, what it cannot tell you, and what decision breaks without it.

This is the document to read before the Wokwi simulation
([`iot/wokwi/`](../iot/wokwi/)) makes sense, and the one to answer from when a judge asks
*"why do you need that many sensors?"*

---

## 0. The one-paragraph answer to "why so many sensors?"

Because **every sensor here has a blind spot that another one covers.** A camera sees
symptoms but not cause. A moisture probe sees water but not a lesion. A thermometer sees
weather but not the plant. History sees change but not why.

The system exists because a yellowing cotton leaf is ambiguous between nitrogen
deficiency, water stress and viral infection — and **no single instrument can separate
them.** Each sensor below is on the node because removing it would make a specific
diagnosis impossible, not because more data is better.

If you can't name the decision a sensor enables, it shouldn't be on the mast.

---

## 1. Soil moisture — capacitive, two depths

**The primary signal. Everything else is context.**

| | |
|---|---|
| Measures | Volumetric water content (% VWC) |
| Principle | Dielectric permittivity |
| Part | Capacitive probe (corrosion-resistant), ×2 |
| Wokwi | Potentiometers on GPIO 34 (shallow) and 35 (root zone) |
| Depths | 100 mm and 300 mm |

### How it actually works

The probe forms a **capacitor with the soil as its dielectric**. Relative permittivity
(εr) differs enormously between the three things in soil:

| Material | εr |
|---|---|
| Air | 1 |
| Dry mineral soil | ~4 |
| **Water** | **~80** |

So capacitance is dominated by water content. The sensor drives an oscillator whose
frequency shifts with that capacitance, then rectifies it to an analog voltage. More
water → higher capacitance → lower frequency → different voltage.

**The electrodes are coated and never touch the soil.** That single design choice is why
we specify capacitive and not resistive — see [DR-011](decision_log.md).

### Why capacitive, not resistive

A resistive probe passes current between two bare metal pins and measures resistance.
Two failures follow directly from that:

1. **Galvanic corrosion.** Current through wet soil electrolyses the electrodes. They
   degrade in weeks to months. Ours are buried and unattended for a season.
2. **Ionic interference.** Resistance depends on dissolved *salts* as much as water.
   In fertilized or saline soil this produces **20–40% VWC error** — and every field we
   deploy in is fertilized.

A 20–40% error in this specific measurement would not degrade gracefully. It would
**invert the diagnosis** and send the farmer to buy the wrong input.

### Why two depths, not one

This is the part most teams skip, and it carries real information:

| Depth | Answers |
|---|---|
| **100 mm (shallow)** | *Did water arrive?* Responds within minutes to rain or irrigation. |
| **300 mm (root zone)** | *Can the plant drink?* Where cotton actually feeds. Slow to change. |

A single probe confuses **"I watered the top"** with **"the crop has water."** After a
light shower the shallow probe reads healthy while the root zone is still dry — the crop
is still in stress, and a one-probe system would say everything is fine.

**The root-zone probe drives the decision.** The shallow one is context.

### What it cannot tell you

- Nothing about disease, pests or nutrients.
- Nothing accurate **until calibrated for the specific soil.** Low-cost capacitive probes
  match laboratory-grade sensors only *after* soil-specific calibration. Our thresholds
  are general cotton agronomy, not calibrated constants. **No field-accuracy claim is
  defensible until that calibration is done.**

### Failure modes we handle

| Failure | Detection | Response |
|---|---|---|
| Out-of-range value (floating pin, short) | Plausibility band 0–100% | Treated as **missing**, never as data |
| **Stuck probe** (dead but still reporting) | 6 bit-identical consecutive readings | Channel excluded, probe named for service |
| Total loss | Value is `None` | Confidence drops to 0.35, decision becomes *manual check* |

**The stuck probe is the dangerous one.** It looks like perfect health: value in range,
reading present, trend a clean zero — which reads as *"moisture is fine, so this is not
water"* and resolves toward nitrogen deficiency. Detection works by exploiting the one
thing a dead sensor cannot fake: **a live probe in soil always jitters.** Bit-identical
readings mean it died while still reporting.

> In Wokwi the ADC is mathematically ideal, so a stationary potentiometer would
> false-trigger this. `_dither()` adds back the ±0.025% jitter a real probe has, so the
> detector exercises the genuine signal property rather than a simulator artifact.

---

## 2. Air temperature

| | |
|---|---|
| Measures | Ambient air temperature (°C) |
| Principle | Band-gap semiconductor / thermistor |
| Part | SHT31 preferred, DHT22 acceptable |
| Wokwi | DHT22 on GPIO 15 |

### How it works

A **band-gap sensor** exploits the fact that the forward voltage of a silicon junction
falls predictably (~2 mV/°C) with temperature. Two junctions at different current
densities give a difference voltage proportional to absolute temperature, which is
ratiometric and therefore stable against supply drift. The result is digitised on-chip.

### Why we need it — three separate jobs

1. **Evapotranspiration driver.** Water leaves the crop faster when it's hot. Moisture at
   22% is a different urgency at 30 °C than at 43 °C, so temperature scales the water-stress
   score rather than just adding to it.
2. **Heat-stress threshold.** Cotton suffers above ~38 °C independently of soil water.
   That's its own risk, with its own advisory.
3. **Pathogen activity band.** Bacterial blight is most active roughly 26–34 °C. Outside
   that band, the same visual evidence means less.

### What breaks without it

Water-stress scoring loses its urgency scaling, heat risk disappears entirely, and the
disease call loses one of its two environmental corroborators.

---

## 3. Relative humidity

| | |
|---|---|
| Measures | Relative humidity (% RH) |
| Principle | Capacitive polymer film |
| Part | SHT31 / DHT22 (same package as temperature) |

### How it works

A **hygroscopic polymer** sits between two electrodes as the dielectric of a capacitor.
The polymer absorbs water vapour in equilibrium with the air; absorbed water raises its
dielectric constant, so **capacitance tracks relative humidity**. Typically a few
picofarads of change across 0–100% RH, measured by an on-chip oscillator.

### Why we need it — this is the disease half

Humidity is our **leaf-wetness proxy**, and leaf wetness is what bacterial and fungal
pathogens actually need. Spores require a film of free water to germinate and infect.
Sustained RH above ~80% means the canopy stays wet long enough for infection.

This is the environmental evidence that turns *"the camera saw something suspicious"* into
*"conditions favour that pathogen right now."* Neither alone is a diagnosis.

It also works in the other direction: **below 50% RH, bacterial spread is implausible**,
so humidity actively *contradicts* a blight hypothesis. Evidence that can disconfirm is
worth more than evidence that can only confirm.

Secondary use: low humidity increases evaporative demand, feeding water stress.

### Limits

RH is not leaf wetness. A dedicated leaf-wetness sensor would be better; humidity is the
affordable proxy, and we should say so rather than imply we measure the real quantity.

### Why SHT31 over DHT22

| | DHT22 | **SHT31** |
|---|---|---|
| Accuracy | ±0.5 °C, ±2–5% RH | ±0.2 °C, ±2% RH |
| Interface | Single-wire, timing-critical, no error checking | **I²C with CRC** |
| Long-term drift | Noticeable | Low |
| Cost | Lower | ~₹600 more |

The CRC matters most. On a node nobody visits, a corrupted reading that *looks* valid is
worse than a reading that announces itself as failed.

---

## 4. Soil temperature

| | |
|---|---|
| Measures | Root-zone temperature (°C) |
| Principle | Thermistor (NTC) or DS18B20 digital probe |

**How it works:** an NTC thermistor is a semiconductor whose resistance falls
exponentially with temperature. A digital probe like the DS18B20 does the same conversion
on-chip and reports over 1-Wire, which avoids running an analog signal down a long buried
cable.

**Why:** root activity and nutrient uptake are temperature-dependent, and soil temperature
**lags air temperature** with an amplitude that depends on moisture. Wet soil has high
thermal mass and swings less. That lag is a free cross-check: if soil temperature tracks
air temperature too closely, the soil is probably drier than the moisture probe claims.

**Priority:** SHOULD, not MUST. It refines; it doesn't decide.

---

## 5. Rain detection

| | |
|---|---|
| Measures | Rain present / absent (binary) |
| Principle | Conductive grid or capacitive plate |
| Wokwi | Pushbutton on GPIO 4 (toggle) |

**How it works:** interleaved conductive traces on a board. A water droplet bridges them
and drops the resistance across the gap, read as a digital threshold. Capacitive versions
detect the permittivity change instead and avoid corroding traces — the same argument as
the soil probe.

### Why we need it — it is a safety gate, not a data point

**Rain is the reason we don't irrigate.** Without it the system will happily schedule
irrigation during a downpour, because soil moisture takes time to respond to rainfall
while the rain sensor responds in seconds.

In the decision engine, rain is checked **before** water stress:

```
if flood risk high and water stress high  ->  DELAY IRRIGATION
                                              "adding water = root anoxia"
```

Waterlogged soil suffocates roots. Irrigating into saturation is not merely wasteful, it
is actively harmful — which is why this gate sits above the irrigation branch rather than
being a modifier inside it.

**Priority: MUST.** A cheap binary sensor that prevents an expensive, harmful mistake.

---

## 6. Light level

| | |
|---|---|
| Measures | Illuminance (lux) |
| Principle | Photoconductivity |
| Part | LDR here; **BH1750 digital lux sensor for deployment** |
| Wokwi | Photoresistor on GPIO 36 (VP) |

**How it works:** an LDR is a cadmium-sulphide film. Incident photons with enough energy
promote electrons to the conduction band, creating charge carriers, so **resistance falls
as illumination rises** — roughly a power law, not linear.

### Why we need it — the image-quality gate

This is the sensor whose purpose is least obvious and most defensible.

**A frame captured in the dark is not evidence.** But a CNN handed an underexposed image
does not return "I can't see" — it returns a confident-looking distribution over classes
it knows. That is exactly how a system produces a wrong, confident, expensive advisory.

So light level gates the vision term:

```python
R.image_usable = lux >= LIGHT_MIN_LUX          # 120 lux
weight = 1.0 if R.image_usable else 0.35
R.disease = vision.confidence * 55.0 * weight
```

and the advisory says **"Frame too dark — discounted"** instead of quoting a confidence it
shouldn't trust. It is a **hardware mitigation for a machine-learning failure mode**, and
it costs almost nothing.

Secondary uses: diurnal phase (schedule captures at consistent illumination so day-to-day
images are comparable), and a rough PAR proxy for growth-stage tracking.

### Limits — say these before a judge does

LDRs are slow (hundreds of ms), non-linear, temperature-dependent, vary widely part to
part, and **cadmium is RoHS-restricted**. Fine for a simulation and a bench demo; a real
deployment uses a photodiode-based digital lux sensor such as the BH1750.

---

## 7. Water tank level

| | |
|---|---|
| Measures | Remaining volume (%) |
| Principle | Ultrasonic time-of-flight, or pressure |
| Wokwi | Potentiometer on GPIO 32 |

**How it works:** an ultrasonic sensor emits a ~40 kHz burst and times the echo. Distance
= (speed of sound × time) / 2, and level = tank height − distance. Speed of sound varies
with temperature (~0.6 m/s per °C), so an accurate installation compensates using the air
temperature we already measure — a nice example of one sensor improving another.

A submersible pressure transducer is the alternative: hydrostatic pressure is proportional
to head height, and it doesn't care about foam or surface turbulence.

### Why we need it — protecting the pump, not the crop

**A pump run dry destroys itself in minutes.** The impeller relies on pumped water for
cooling and lubrication. Replacing it costs more than the entire sensor node.

So the tank gate is hard and sits *inside* the irrigation branch:

```
water stress HIGH  +  tank < 15%   ->  TANK REFILL, valve held shut
```

The crop stays stressed. That is the correct trade: the crop recovers from a delayed
irrigation, the pump does not recover from running dry, and a farmer with a dead pump has
no irrigation at all.

---

## 8. Water flow

| | |
|---|---|
| Measures | Delivered volume (litres) |
| Principle | Hall-effect turbine |
| Status | ⬜ not in the Wokwi wiring — modelled in firmware |

**How it works:** water spins a small impeller carrying a magnet. A Hall-effect sensor in
the housing outputs a pulse per revolution. Pulses are proportional to volume — typically
a few hundred pulses per litre — so counting pulses on an interrupt gives delivered volume,
and pulse *rate* gives flow rate.

### Why it matters more than it looks

Without flow measurement, irrigation is an **open loop**: we command a valve and assume
water arrived. Flow closes it, and catches three real failures a valve command cannot:

1. **Valve commanded open but nothing flowing** → blockage, or the solenoid failed.
2. **Flow with no valve command** → a leak or a stuck-open valve, silently draining the tank.
3. **Delivered volume ≠ target** → the difference between a claim and a measurement.

It is also the only honest basis for a water-saving figure. Any saving quoted without flow
measurement is arithmetic, not evidence — which is why the twin labels its number
**SIMULATED DEMONSTRATION VALUE**.

---

## 9. Soil pH

| | |
|---|---|
| Measures | Soil acidity/alkalinity |
| Principle | Ion-selective potentiometry |

**How it works:** a glass electrode has a membrane selectively permeable to H⁺ ions. The
activity difference between the soil solution and a reference buffer inside generates a
potential across it, following the Nernst equation at about **59 mV per pH unit** at 25 °C.
A high-impedance amplifier reads that against a reference electrode.

### Why we need it — nutrients can be present and unavailable

pH controls **nutrient availability**, not nutrient quantity. Outside roughly 6.0–7.5,
phosphorus locks into insoluble compounds and micronutrients precipitate. The soil test
says the nutrient is there; the plant still cannot take it up.

So pH changes the *advice*: a deficiency at pH 8.2 is a pH problem, and adding fertilizer
would waste money without fixing it. That is the same class of error the whole project
exists to prevent — buying the wrong input.

**Practical caveat:** glass electrodes need regular recalibration and don't survive
permanent burial well. Realistically this is a periodic manual measurement entered into
the system, not a continuously logged channel. **We should not imply it is continuous.**

---

## 10. Nitrogen, phosphorus, potassium — with an honest warning

| | |
|---|---|
| Measures | Nominal N / P / K levels |
| Status | ⚠️ **Read the caveat before quoting these** |

### The caveat that must be stated

**Cheap "NPK sensors" sold for hobby and low-cost agriculture do not perform true
ion-selective measurement of nitrogen, phosphorus and potassium.** They almost universally
measure bulk **electrical conductivity** and apply a vendor correlation to output three
numbers that look like nutrient values. Those correlations are soil-specific, generally
uncalibrated, and not traceable to a laboratory soil test.

Presenting such a reading as a measured nitrogen level is the kind of claim that collapses
under one informed question — and an agronomist on a judging panel will know.

### How we use them honestly

As a **coarse relative indicator** (LOW / NORMAL) contributing to a nutrient *risk* score,
never as an absolute nutrient value and never as the basis for a fertilizer prescription.
The advisory is *"possible nitrogen deficiency — inspect and soil-test this zone."*

**The system's actual nitrogen-deficiency reasoning does not depend on an NPK sensor at
all.** It works by *exclusion*: chlorosis under adequate, stable soil moisture is not
explained by water. That inference uses the moisture probe — which we trust — rather than
a sensor we would have to overclaim.

True laboratory-grade N/P/K needs wet chemistry or spectroscopy. Neither fits on a mast.

---

## 11. Electrical conductivity (EC)

| | |
|---|---|
| Measures | Total dissolved salts (dS/m) |
| Principle | AC conductivity between electrodes |

**How it works:** an **alternating** current is applied between two electrodes and the
resulting current measured. AC is essential — DC would electrolyse the soil solution and
polarise the electrodes, which is the same physics that destroys resistive moisture
probes. Conductivity rises with dissolved ion concentration.

**Why:** salinity is a genuine yield constraint in irrigated Indian cotton, particularly
with groundwater irrigation. High EC also causes **osmotic stress** — the plant wilts even
though soil moisture reads adequate, because it cannot extract the water.

That is an important edge case for us: **EC explains a water-stressed-looking plant in wet
soil.** Without it, that combination looks like a sensor fault or a disease.

EC is also the confounder that makes resistive moisture probes fail, which is worth
mentioning as the reason we chose capacitive.

---

## 12. Camera — the vision channel

| | |
|---|---|
| Measures | Leaf and canopy imagery |
| Processed by | **QCS6490 NPU — not the ESP32** |
| Wokwi | Potentiometer on GPIO 33, or MQTT injection |

### Why it isn't in the MCU firmware

The sentinel has two processors, and this is the split that makes the power budget work:

| | Role | Duty cycle |
|---|---|---|
| **ESP32** | Sensors, validation, history, risk, decisions, valve | **Always on**, milliwatts |
| **QCS6490** | Crop-disease inference on the NPU | **Off by default**, woken on trigger |

An always-on application SoC is not solar-feasible at smallholder cost. So the MCU decides
*when a capture is worth the energy*, and the vision result arrives back as an **input** —
over UART on the real board, over MQTT in the simulation.

**This is why the firmware does not run a CNN and does not pretend to.**

### What vision contributes, and what it cannot

Vision provides the **symptom evidence** — lesions, chlorosis, pest instances. What it
cannot do, and no larger model fixes, is separate causes that look alike. A single RGB
frame does not contain the information that distinguishes nitrogen deficiency from water
stress. **A three-day soil-moisture trend does.**

That information limit is the reason this whole sensor stack exists.

### The open risk

**Out-of-distribution inputs.** Shown a disease it was never trained on, the model spreads
probability across classes it knows and can look confident. Fusion cannot rescue it,
because fusion only reweights hypotheses it was handed. This is tracked as **A3** in
[13_failure_modes.md](13_failure_modes.md) and is currently the highest open risk in the
project.

---

## 13. How the sensors combine — the actual mechanism

Sensors do not feed parallel dashboards. Each stage below consumes the one above it:

```
   CAMERA          SOIL PROBES         ENVIRONMENT        TIME HISTORY
   symptoms        water available     weather            rate of change
      |                  |                  |                  |
      +------------------+------------------+------------------+
                                |
                        VALIDATION LAYER
              plausibility bands · stuck detection · fault flags
                                |
                          SENSOR FUSION
                 corroborate, contradict, or abstain
                                |
                           RISK ENGINE
            water · disease · pest · nutrient · heat · flood
                                |
                         DECISION ENGINE
                   safety gates first, advisory second
                                |
                +---------------+---------------+
                |                               |
          LOCAL ADVISORY                  VALVE CONTROL
          always available              the one controlled action
                                |
                          OPTIONAL CLOUD
```

### The blind-spot table — why each sensor survives review

| Sensor | Sees | Blind to | Covered by |
|---|---|---|---|
| Camera | Symptoms | Cause, soil state | Soil probes |
| Soil moisture | Water availability | Lesions, pests | Camera |
| Air temp | Evaporative demand | Plant condition | Camera + soil |
| Humidity | Infection conditions | Whether infection occurred | Camera |
| Rain | Incoming water | Root-zone effect | Deep probe |
| Light | Image usability | The crop itself | Camera |
| Tank | Supply | Demand | Soil probes |
| Flow | Delivery | Whether it was needed | Soil probes |
| pH / EC | Nutrient availability | Nutrient quantity | Lab test |
| Time history | Rate and direction | Cause | All of the above |

**No row is self-sufficient. That is the argument for the whole stack.**

---

## 14. Sensor → decision map

The test any sensor must pass: name the decision it enables.

| Sensor | Enables | Breaks without it |
|---|---|---|
| **Soil moisture (root zone)** | Irrigate / don't. Water-stress vs nitrogen separation. | The core differentiator. Nothing works. |
| Soil moisture (shallow) | Distinguishes surface wetting from root-zone recharge | System irrigates on a light shower |
| Air temperature | Heat-stress advisory; urgency scaling | No heat risk; water stress mis-scaled |
| Humidity | Disease-favourable window; disconfirms blight when dry | Disease call rests on vision alone |
| Rain | Suppresses irrigation into wet soil | Irrigates during rainfall |
| Light | Image-quality gate | Confident diagnoses from dark frames |
| Tank level | Pump-safety gate | Pump destroyed running dry |
| Flow | Verifies delivery; leak detection | Irrigation is an open loop |
| pH | Distinguishes deficiency from lock-out | Wrong advice: fertilizer that won't be taken up |
| EC | Osmotic stress; salinity | Wilting in wet soil is unexplainable |
| Camera | Symptom evidence | No disease or pest detection at all |

---

## 15. Sensor status model

Every channel carries a state, and the system never substitutes a value for a missing one.

| Status | Meaning | System response |
|---|---|---|
| **GOOD** | In range, changing plausibly | Full weight in fusion |
| **DEGRADED** | Intermittent, or conditions unfavourable (dark frame) | Reduced weight, stated in the advisory |
| **FAILED** | Missing, implausible, or stuck | **Excluded.** Confidence lowered, decision may become *manual check* |

Three rules the implementation enforces:

1. **An implausible value is a fault, not data.** A floating ADC pin reading 247% moisture
   is treated as missing.
2. **A missing value is never replaced with an estimate.** Substituting a plausible-looking
   number hides the failure and produces confident wrong advice.
3. **Insufficient data returns "unknown", never a default.** The trend function returns
   `None` rather than a fabricated zero, because a false "stable" reads as *not
   water-driven* and skews the diagnosis toward a nutrient explanation.

---

## 16. Simulation mapping

| Real part | Wokwi stand-in | Fidelity note |
|---|---|---|
| Capacitive soil probe ×2 | Potentiometers, GPIO 34 / 35 | Manual control; `_dither()` restores the ADC jitter a real probe has |
| SHT31 | DHT22, GPIO 15 | Same interface shape, lower accuracy |
| Rain sensor | Pushbutton, GPIO 4 | Binary, which is what the real one is |
| Photoresistor | LDR sensor, GPIO 36 | Same physics, same limits |
| Ultrasonic tank | Potentiometer, GPIO 32 | Level only; no temperature compensation modelled |
| Flow sensor | — | Modelled in firmware, not wired |
| pH / NPK / EC | — | Simulated in the digital twin only |
| Camera + NPU | Potentiometer GPIO 33, or MQTT | Vision is an **input**; no model runs on the ESP32 |
| Solenoid valve | LED, GPIO 18 | State only |

⚠️ **Nothing in the simulation is a field measurement.** Sensor values come from
potentiometers and mock inference. Agronomic thresholds are general cotton starting points,
not calibrated constants.

---

## 17. What we do not claim

State these before someone finds them:

1. **No calibration has been performed.** Capacitive probes match good sensors only after
   soil-specific calibration. Our thresholds are literature starting points.
2. **NPK values are conductivity-derived proxies**, not laboratory nutrient measurements.
3. **pH is realistically a periodic manual reading**, not a continuously logged channel.
4. **Humidity is a leaf-wetness proxy**, not leaf wetness.
5. **No IP rating is claimed** — none has been tested. The enclosure is *designed for*
   outdoor environmental protection.
6. **No sensor has been deployed in a field.** Every number in the simulation and the twin
   is generated for explanation.
7. **The ESP32 runs no vision model.** Disease confidence is a simulated input.
