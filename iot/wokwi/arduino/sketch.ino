/* ===========================================================================
 * SMART FARM SENTINEL — sentinel MCU firmware
 * SIH PS 26180 · Qualcomm · fixed pole-mounted node
 *
 * WHAT THIS IS, ARCHITECTURALLY
 * ----------------------------
 * In the full system the sentinel has two processors:
 *
 *   ESP32  (this sketch) — ALWAYS ON, milliwatts. Reads soil and air sensors,
 *                          validates them, keeps the rolling history, scores
 *                          risk, makes the irrigation decision, drives the
 *                          local display and valve. Decides when the vision
 *                          stack is worth waking.
 *
 *   QCS6490 (not here)   — OFF by default. Wakes on this MCU's trigger, runs
 *                          the crop-disease model on the NPU, and returns a
 *                          result over UART.
 *
 * So this firmware does NOT run a CNN, and does not pretend to. Vision output
 * is an INPUT here, exactly as it is on the real board. See readVision().
 *
 * WHY THAT SPLIT: an always-on application SoC is not solar-feasible at
 * smallholder cost. Duty-cycling it is what makes the power budget work.
 *
 * CONTROLS IN THE SIMULATION
 *   Pot "soilA"  — soil moisture, shallow probe (100 mm)
 *   Pot "soilB"  — soil moisture, root zone (300 mm)
 *   Pot "tank"   — water tank level
 *   Pot "vision" — disease confidence arriving from the edge AI module
 *   DHT22        — air temperature + humidity
 *   LDR          — light level
 *   Btn RAIN     — toggle rain detected
 *   Btn NET      — cut / restore the cloud link
 *   Btn FAULT    — cycle: none -> probe STUCK -> probe FAILED -> none
 *
 * SERIAL COMMAND INTERFACE (the real integration point)
 *   Send  V,<disease_conf 0..1>,<pest_count>   e.g.  V,0.72,4
 *   This is the message the Qualcomm module sends after an inference. While
 *   a message is in force the vision potentiometer is ignored.
 * ======================================================================== */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DHT.h"

/* ---------------- pins ---------------- */
#define PIN_SOIL_SHALLOW 34
#define PIN_SOIL_DEEP    35
#define PIN_TANK         32
#define PIN_VISION       33
#define PIN_LIGHT        36   // VP
#define PIN_DHT          15
#define PIN_BTN_RAIN      4
#define PIN_BTN_NET       5
#define PIN_BTN_FAULT    13
#define PIN_LED_VALVE    18
#define PIN_LED_ALERT    19
#define PIN_LED_EDGE     23

/* ---------------- agronomic thresholds ----------------
 * General cotton agronomy on medium-textured soil. These are STARTING POINTS,
 * not calibrated field constants. No field-accuracy claim is defensible until
 * per-soil calibration is done. Mirrors iot/fusion/engine.py FusionConfig. */
const float MOISTURE_STRESS      = 20.0;
const float MOISTURE_ADEQUATE    = 28.0;
const float MOISTURE_WATERLOGGED = 45.0;
const float DRYING_TREND_PER_H   = -0.5;   // %/hour
const float HEAT_STRESS_C        = 38.0;
const float BLIGHT_HUMIDITY      = 80.0;
const float TANK_MIN_PCT         = 15.0;   // below this the valve stays shut
const float LIGHT_MIN_LUX        = 120.0;  // below this a frame is too dark to trust

/* plausible ranges — a reading outside these is a FAULT, not a measurement */
const float MOISTURE_MIN = 0.0,  MOISTURE_MAX = 100.0;
const float TEMP_MIN    = -10.0, TEMP_MAX     = 60.0;
const float HUM_MIN     = 0.0,   HUM_MAX      = 100.0;

const uint8_t HIST_N     = 24;   // rolling window
const uint8_t FROZEN_RUN = 6;    // identical samples that mean "stuck"

/* ---------------- peripherals ---------------- */
DHT dht(PIN_DHT, DHT22);
Adafruit_SSD1306 oled(128, 64, &Wire, -1);

/* ---------------- state ---------------- */
enum Fault { FAULT_NONE = 0, FAULT_STUCK, FAULT_FAILED };
Fault  fault      = FAULT_NONE;
bool   rainFlag   = false;
bool   online     = true;
uint32_t queued   = 0;

float  histM[HIST_N];
uint8_t histCount = 0, histHead = 0;
float  heldMoisture = NAN;          // value a stuck probe keeps repeating

float  visionConf = 0.0;            // disease confidence, 0..1
int    pestCount  = 0;
uint32_t visionRxMs = 0;            // when the last serial vision msg arrived

bool   valveOpen  = false;
float  litres     = 0;

uint8_t page = 0;
uint32_t lastSample = 0, lastPage = 0, lastEdgeBlink = 0;
bool edgeLedState = false;

/* debounce */
uint32_t lastBtn[3] = {0, 0, 0};

/* ---------------- sensor reading ---------------- */

/* Wokwi's ADC is mathematically ideal. A real capacitive probe in soil always
 * jitters by a fraction of a percent. We add that dither back so the
 * stuck-sensor detector below is testing the same signal property it would in
 * the field — a dead probe is detectable precisely because it stops jittering. */
float dither() { return (random(-25, 26)) / 1000.0f; }

float readMoisturePct(int pin) {
  int raw = analogRead(pin);
  return (raw * 60.0f / 4095.0f) + dither();
}

float readTankPct() {
  return analogRead(PIN_TANK) * 100.0f / 4095.0f;
}

/* Vision result. On real hardware this arrives over UART from the QCS6490
 * after the NPU inference. Serial takes priority; the potentiometer is the
 * fallback so the board demonstrates standalone. */
void readVision() {
  if (millis() - visionRxMs < 15000 && visionRxMs != 0) return;  // serial still fresh
  visionConf = analogRead(PIN_VISION) / 4095.0f;
  pestCount  = 0;
}

void pollSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      line.trim();
      if (line.startsWith("V,")) {
        int c1 = line.indexOf(',', 2);
        if (c1 > 0) {
          visionConf = constrain(line.substring(2, c1).toFloat(), 0.0, 1.0);
          pestCount  = line.substring(c1 + 1).toInt();
          visionRxMs = millis();
          Serial.print(F("[edge-ai] vision accepted: disease="));
          Serial.print(visionConf, 2);
          Serial.print(F(" pest="));
          Serial.println(pestCount);
        }
      }
      line = "";
    } else if (line.length() < 40) {
      line += c;
    }
  }
}

/* ---------------- history + fault detection ---------------- */
void pushHistory(float v) {
  histM[histHead] = v;
  histHead = (histHead + 1) % HIST_N;
  if (histCount < HIST_N) histCount++;
}

float histAt(uint8_t i) {   // i = 0 is oldest retained
  uint8_t start = (histHead + HIST_N - histCount) % HIST_N;
  return histM[(start + i) % HIST_N];
}

/* Six bit-identical consecutive readings mean the probe died while still
 * reporting. This is the most dangerous sensor failure the system faces,
 * because it looks like healthy data: value in range, reading present, and a
 * trend of a clean, convincing zero — which reads as "moisture is fine, so
 * this is not water" and would send a farmer to buy fertilizer for a crop
 * dying of thirst. */
bool moistureStuck() {
  if (histCount < FROZEN_RUN) return false;
  float last = histAt(histCount - 1);
  for (uint8_t i = 2; i <= FROZEN_RUN; i++)
    if (fabs(histAt(histCount - i) - last) > 0.0005f) return false;
  return true;
}

/* Least-squares slope in %/hour. Returns NAN when there is too little data —
 * never a fabricated zero, which would read as "stable" and skew the
 * diagnosis toward a nutrient explanation. */
float moistureTrendPerHour() {
  if (histCount < 4) return NAN;
  float sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (uint8_t i = 0; i < histCount; i++) {
    float x = i * 0.5f;             // one sample per simulated half hour
    float y = histAt(i);
    sx += x; sy += y; sxx += x * x; sxy += x * y;
  }
  float n = histCount, d = n * sxx - sx * sx;
  if (fabs(d) < 1e-6) return NAN;
  return (n * sxy - sx * sy) / d;
}

/* ---------------- risk engine ---------------- */
struct Risks {
  float water, disease, pest, heat, flood;
  float confidence;
  bool  moistureValid;
  bool  imageUsable;
};

Risks computeRisks(float m, float t, float h, float trend, float lightLux) {
  Risks R = {0, 0, 0, 0, 0, 1.0, true, true};

  bool mOk = !isnan(m) && m >= MOISTURE_MIN && m <= MOISTURE_MAX;
  bool tOk = !isnan(t) && t >= TEMP_MIN     && t <= TEMP_MAX;
  bool hOk = !isnan(h) && h >= HUM_MIN      && h <= HUM_MAX;
  R.moistureValid = mOk;

  /* --- water stress --- */
  if (!mOk) {
    R.confidence = 0.35;              // primary signal missing; say so
  } else {
    if      (m < MOISTURE_STRESS)       R.water += 55;
    else if (m < MOISTURE_ADEQUATE - 4) R.water += 34;
    else if (m < MOISTURE_ADEQUATE + 1) R.water += 15;
    if (!isnan(trend) && trend < DRYING_TREND_PER_H) R.water += 18;
    if (tOk && t > 36) R.water += 18; else if (tOk && t > 32) R.water += 8;
    if (hOk && h < 45) R.water += 8;
    if (rainFlag)      R.water -= 25;
  }

  /* --- disease: vision + environment, neither sufficient alone ---
   * A frame captured in the dark is not evidence. Rather than trust a
   * confident-looking inference on an underexposed image, we discount the
   * vision term and lower the overall confidence, so the decision layer can
   * say why it is unsure instead of quietly acting on a bad frame. */
  R.imageUsable = (lightLux >= LIGHT_MIN_LUX);
  float visionWeight = R.imageUsable ? 1.0f : 0.35f;
  if (!R.imageUsable) R.confidence = min(R.confidence, 0.6f);

  R.disease = visionConf * 55.0f * visionWeight;
  if (hOk && h > BLIGHT_HUMIDITY) R.disease += 22;
  else if (hOk && h > 70)         R.disease += 10;
  if (tOk && t > 26 && t < 34)    R.disease += 12;

  R.pest  = min(100.0f, pestCount * 6.5f);
  R.heat  = tOk ? constrain((t - 33.0f) * 11.0f, 0.0f, 100.0f) : 0;
  R.flood = mOk ? constrain((rainFlag ? 45.0f : 0.0f) +
                            (m > MOISTURE_WATERLOGGED ? (m - MOISTURE_WATERLOGGED) * 6.0f : 0.0f),
                            0.0f, 100.0f) : 0;

  R.water   = constrain(R.water, 0, 100);
  R.disease = constrain(R.disease, 0, 100);
  return R;
}

const char* band(float v) { return v >= 60 ? "HIGH" : v >= 32 ? "MED" : "LOW"; }

/* ---------------- decision engine ---------------- */
struct Decision {
  const char* title;
  const char* detail;
  String reasons[4];
  uint8_t nReasons;
  bool irrigate;
  bool alert;
};

Decision decide(float m, float t, float h, float trend, float tank, Risks R) {
  Decision d;
  d.irrigate = false; d.alert = false; d.nReasons = 0;

  /* 1. A failed primary sensor is not a diagnosis. Never substitute a value. */
  if (!R.moistureValid) {
    d.title  = "MANUAL CHECK";
    d.detail = "soil probe unavailable";
    d.reasons[d.nReasons++] = "Soil moisture: FAILED";
    d.reasons[d.nReasons++] = "No value substituted";
    d.reasons[d.nReasons++] = "Water confidence LOW";
    d.alert = true;
    return d;
  }

  /* 2. A stuck probe is worse than a missing one — it looks healthy. */
  if (moistureStuck()) {
    d.title  = "MANUAL CHECK";
    d.detail = "soil probe stuck";
    d.reasons[d.nReasons++] = "Readings unchanging";
    d.reasons[d.nReasons++] = "Channel excluded";
    d.reasons[d.nReasons++] = "Probe needs service";
    d.alert = true;
    return d;
  }

  /* 3. Never irrigate into saturated soil. */
  if (R.flood >= 45 && R.water >= 45) {
    d.title  = "DELAY IRRIGATION";
    d.detail = "soil already saturated";
    d.reasons[d.nReasons++] = rainFlag ? "Rain detected" : "Recent rainfall";
    d.reasons[d.nReasons++] = String("Moisture ") + String(m, 0) + "% at saturation";
    d.reasons[d.nReasons++] = "Adding water = root anoxia";
    d.alert = true;
    return d;
  }

  /* 4. Water stress, gated on tank safety. */
  if (R.water >= 55) {
    if (tank < TANK_MIN_PCT) {
      d.title  = "TANK REFILL";
      d.detail = "irrigation blocked";
      d.reasons[d.nReasons++] = String("Water stress ") + String(band(R.water));
      d.reasons[d.nReasons++] = String("Tank ") + String(tank, 0) + "% < 15%";
      d.reasons[d.nReasons++] = "Valve held shut";
      d.alert = true;
      return d;
    }
    d.title  = "IRRIGATE NOW";
    d.detail = "zone water stress";
    d.reasons[d.nReasons++] = String("Moisture ") + String(m, 0) + "% below thresh";
    if (!isnan(trend))
      d.reasons[d.nReasons++] = String("Trend ") + String(trend, 2) + " %/h falling";
    d.reasons[d.nReasons++] = String("Air temp ") + String(t, 0) + "C";
    d.reasons[d.nReasons++] = rainFlag ? "Rain: YES" : "Rain: none";
    d.irrigate = true;
    return d;
  }

  /* 5. Disease / pest — advisory only, never an automatic chemical. */
  if (R.disease >= 60 || R.pest >= 60) {
    d.title  = "INSPECT ZONE";
    d.detail = R.pest > R.disease ? "pest activity rising" : "disease risk high";
    d.reasons[d.nReasons++] = R.imageUsable
        ? String("Vision conf ") + String(visionConf * 100, 0) + "%"
        : String("Frame too dark - discounted");
    d.reasons[d.nReasons++] = String("Humidity ") + String(h, 0) + "%";
    d.reasons[d.nReasons++] = String("Temp ") + String(t, 0) + "C in band";
    d.reasons[d.nReasons++] = "Advisory - no spray Rx";
    d.alert = true;
    return d;
  }

  /* 6. Heat. */
  if (R.heat >= 60) {
    d.title  = "HEAT STRESS";
    d.detail = "monitor closely";
    d.reasons[d.nReasons++] = String("Air temp ") + String(t, 0) + "C";
    d.reasons[d.nReasons++] = String("Above ") + String(HEAT_STRESS_C, 0) + "C threshold";
    d.alert = true;
    return d;
  }

  d.title  = "NO ACTION";
  d.detail = "all signals normal";
  d.reasons[d.nReasons++] = String("Moisture ") + String(m, 0) + "% ok";
  d.reasons[d.nReasons++] = String("Temp ") + String(t, 0) + "C ok";
  d.reasons[d.nReasons++] = "No visual evidence";
  return d;
}

/* ---------------- buttons ---------------- */
bool pressed(int pin, uint8_t slot) {
  if (digitalRead(pin) == LOW && millis() - lastBtn[slot] > 300) {
    lastBtn[slot] = millis();
    return true;
  }
  return false;
}

/* ---------------- display ---------------- */
void drawPage(float m, float t, float h, float trend, float tank,
              Risks R, Decision d) {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  /* status strip is always visible: the point of an edge device is that this
     line never depends on the network */
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print(F("EDGE:OK"));
  oled.setCursor(58, 0);
  oled.print(online ? F("CLOUD:UP") : F("CLOUD:DOWN"));
  oled.setCursor(118, 0);
  oled.print(page + 1);
  oled.drawLine(0, 9, 127, 9, SSD1306_WHITE);

  if (page == 0) {                       /* decision */
    oled.setTextSize(1);
    oled.setCursor(0, 14);
    oled.print(d.title);
    oled.setCursor(0, 24);
    oled.print(d.detail);
    oled.drawLine(0, 33, 127, 33, SSD1306_WHITE);
    for (uint8_t i = 0; i < d.nReasons && i < 3; i++) {
      oled.setCursor(0, 36 + i * 9);
      oled.print(F("- "));
      oled.print(d.reasons[i]);
    }
  } else if (page == 1) {                /* sensors */
    oled.setCursor(0, 14);
    if (!R.moistureValid || moistureStuck()) {
      oled.print(F("Soil : "));
      oled.print(moistureStuck() ? F("STUCK") : F("FAILED"));
    } else {
      oled.print(F("Soil : ")); oled.print(m, 1); oled.print(F(" %"));
    }
    oled.setCursor(0, 24); oled.print(F("Temp : ")); oled.print(t, 1); oled.print(F(" C"));
    oled.setCursor(0, 34); oled.print(F("Hum  : ")); oled.print(h, 0); oled.print(F(" %"));
    oled.setCursor(0, 44); oled.print(F("Rain : ")); oled.print(rainFlag ? F("YES") : F("NO"));
    oled.setCursor(0, 54); oled.print(F("Tank : ")); oled.print(tank, 0); oled.print(F(" %"));
  } else if (page == 2) {                /* risk */
    oled.setCursor(0, 14); oled.print(F("Water   ")); oled.print(band(R.water));
    oled.print(F(" ")); oled.print(R.water, 0);
    oled.setCursor(0, 24); oled.print(F("Disease ")); oled.print(band(R.disease));
    oled.print(F(" ")); oled.print(R.disease, 0);
    oled.setCursor(0, 34); oled.print(F("Pest    ")); oled.print(band(R.pest));
    oled.setCursor(0, 44); oled.print(F("Heat    ")); oled.print(band(R.heat));
    oled.setCursor(0, 54); oled.print(F("Flood   ")); oled.print(band(R.flood));
  } else {                               /* link */
    oled.setCursor(0, 14);
    oled.print(online ? F("Cloud connected") : F("Cloud UNAVAILABLE"));
    oled.setCursor(0, 26); oled.print(F("Queued: ")); oled.print(queued);
    oled.drawLine(0, 36, 127, 36, SSD1306_WHITE);
    oled.setCursor(0, 40); oled.print(F("Sensing  ACTIVE"));
    oled.setCursor(0, 50); oled.print(F("Decision ACTIVE"));
  }
  oled.display();
}

/* ---------------- setup / loop ---------------- */
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BTN_RAIN,  INPUT_PULLUP);
  pinMode(PIN_BTN_NET,   INPUT_PULLUP);
  pinMode(PIN_BTN_FAULT, INPUT_PULLUP);
  pinMode(PIN_LED_VALVE, OUTPUT);
  pinMode(PIN_LED_ALERT, OUTPUT);
  pinMode(PIN_LED_EDGE,  OUTPUT);

  dht.begin();
  Wire.begin(21, 22);
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("OLED not found"));
  }
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 20);
  oled.println(F("SMART FARM"));
  oled.println(F("SENTINEL"));
  oled.println(F("edge booting..."));
  oled.display();
  delay(1200);

  Serial.println(F("\n=== SMART FARM SENTINEL — edge node online ==="));
  Serial.println(F("Vision input: send  V,<conf>,<pests>   e.g.  V,0.72,4"));
  Serial.println(F("Buttons: RAIN | NET (cut cloud) | FAULT (stuck -> failed)\n"));
}

void loop() {
  pollSerial();

  /* buttons */
  if (pressed(PIN_BTN_RAIN, 0)) {
    rainFlag = !rainFlag;
    Serial.print(F("[sensor] rain = ")); Serial.println(rainFlag ? "YES" : "NO");
  }
  if (pressed(PIN_BTN_NET, 1)) {
    online = !online;
    if (online) {
      Serial.print(F("[cloud] link restored — replaying "));
      Serial.print(queued); Serial.println(F(" queued records"));
      queued = 0;
    } else {
      Serial.println(F("[cloud] link DOWN — edge continues, records queue locally"));
    }
  }
  if (pressed(PIN_BTN_FAULT, 2)) {
    fault = (Fault)((fault + 1) % 3);
    heldMoisture = NAN;
    Serial.print(F("[fault] soil probe = "));
    Serial.println(fault == FAULT_NONE ? "GOOD" : fault == FAULT_STUCK ? "STUCK" : "FAILED");
  }

  /* edge heartbeat — deliberately independent of network state */
  if (millis() - lastEdgeBlink > 900) {
    lastEdgeBlink = millis();
    edgeLedState = !edgeLedState;
    digitalWrite(PIN_LED_EDGE, edgeLedState);
  }

  /* sample + decide */
  if (millis() - lastSample > 1000) {
    lastSample = millis();

    float mShallow = readMoisturePct(PIN_SOIL_SHALLOW);
    float mDeep    = readMoisturePct(PIN_SOIL_DEEP);

    /* Root-zone probe drives the decision. The shallow one tells you what the
       surface did after rain or irrigation; only the deep one tells you what
       the plant can actually drink. */
    float m = mDeep;
    if (fault == FAULT_FAILED) {
      m = NAN;
    } else if (fault == FAULT_STUCK) {
      if (isnan(heldMoisture)) heldMoisture = m;
      m = heldMoisture;                      // dead probe repeats its last value
    }

    float t = dht.readTemperature();
    float h = dht.readHumidity();
    float tank     = readTankPct();
    float lightLux = analogRead(PIN_LIGHT) * 1200.0f / 4095.0f;
    readVision();

    if (!isnan(m)) pushHistory(m);
    float trend = moistureTrendPerHour();

    Risks R = computeRisks(m, t, h, trend, lightLux);
    Decision d = decide(m, t, h, trend, tank, R);

    /* actuation — advisory system, but the valve is the one controlled action */
    if (d.irrigate && tank >= TANK_MIN_PCT) {
      valveOpen = true;
      litres += 0.35;
      if (litres >= 10.0) { valveOpen = false; litres = 0; }
    } else {
      valveOpen = false;
    }
    digitalWrite(PIN_LED_VALVE, valveOpen);
    digitalWrite(PIN_LED_ALERT, d.alert);

    if (!online) queued++;

    /* serial report */
    Serial.print(F("soil="));
    if (isnan(m)) Serial.print(F("FAILED"));
    else { Serial.print(m, 1); Serial.print(F("%")); if (moistureStuck()) Serial.print(F("(STUCK)")); }
    Serial.print(F("  shallow=")); Serial.print(mShallow, 1);
    Serial.print(F("%  T=")); Serial.print(t, 1);
    Serial.print(F("C  RH=")); Serial.print(h, 0);
    Serial.print(F("%  tank=")); Serial.print(tank, 0);
    Serial.print(F("%  rain=")); Serial.print(rainFlag ? "Y" : "N");
    Serial.print(F("  lux=")); Serial.print(lightLux, 0);
    if (!R.imageUsable) Serial.print(F("(dark)"));
    Serial.print(F("  | water=")); Serial.print(band(R.water));
    Serial.print(F(" disease=")); Serial.print(band(R.disease));
    Serial.print(F("  => ")); Serial.print(d.title);
    Serial.print(F(" ["));    Serial.print(d.detail); Serial.print(F("]"));
    if (!online) { Serial.print(F("  offline q=")); Serial.print(queued); }
    Serial.println();

    drawPage(m, t, h, trend, tank, R, d);
  }

  /* rotate display pages */
  if (millis() - lastPage > 3500) {
    lastPage = millis();
    page = (page + 1) % 4;
  }
}
