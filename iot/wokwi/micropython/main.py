"""
SMART FARM SENTINEL - sentinel MCU firmware (MicroPython / ESP32)
SIH PS 26180 - Qualcomm - fixed pole-mounted node

Full sensing stack. Every channel below is documented in
docs/23_sensing_reference.md: operating principle, why the system needs it,
what it cannot tell you, and the decision that breaks without it. The same
rationale is carried in the SENSORS registry here and printed at boot, so the
running simulation explains itself.

ARCHITECTURE
------------
    ESP32   (this file)  ALWAYS ON, milliwatts. Sensing, validation, rolling
                         history, risk scoring, irrigation decision, local
                         display, MQTT sync. Decides when vision is worth waking.

    QCS6490 (not here)   OFF by default. Wakes on this MCU's trigger, runs the
                         crop-disease model on the NPU, publishes the result.

This firmware runs no CNN and does not pretend to. Vision confidence is an
INPUT, exactly as it is on the real board.

MQTT  (broker.mqttdashboard.com - public HiveMQ)
    sih26180/sentinel-01/inventory   <- published once at boot: the sensor stack
    sih26180/sentinel-01/telemetry   <- sensor state every cycle
    sih26180/sentinel-01/decision    <- advisory + reasons
    sih26180/sentinel-01/vision      -> SUBSCRIBED: {"disease":0.85,"pests":6}

WATCH IT: http://www.hivemq.com/demos/websocket-client/
          subscribe to  sih26180/sentinel-01/#
"""

# Print before touching hardware: a silent board is impossible to debug.
print()
print("=" * 66)
print(" SMART FARM SENTINEL  -  edge node booting (MicroPython)")
print("=" * 66)

import time
import json
import framebuf

from machine import Pin, ADC, SoftI2C, PWM, time_pulse_us
import dht

# Optional modules. A field node must not fail to boot because one peripheral
# library is missing from the firmware build - it should say so and carry on
# with whatever it does have.
try:
    import onewire
    import ds18x20
    HAS_ONEWIRE = True
except ImportError as _e:
    HAS_ONEWIRE = False
    print("[boot] 1-Wire unavailable ({}) - soil temperature disabled".format(_e))

try:
    import network
    from umqtt.simple import MQTTClient
    HAS_NET = True
except ImportError as _e:
    HAS_NET = False
    print("[boot] networking unavailable ({}) - running edge-only".format(_e))

# --------------------------------------------------------------------------
# identity / network
# --------------------------------------------------------------------------
NODE_ID = "sentinel-01"
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""
MQTT_BROKER = "broker.mqttdashboard.com"
MQTT_CLIENT_ID = "sih26180-" + NODE_ID
TOPIC_BASE = "sih26180/" + NODE_ID
TOPIC_INVENTORY = TOPIC_BASE + "/inventory"
TOPIC_TELEMETRY = TOPIC_BASE + "/telemetry"
TOPIC_DECISION = TOPIC_BASE + "/decision"
TOPIC_VISION = TOPIC_BASE + "/vision"
WIFI_TIMEOUT_S = 8
QUEUE_MAX = 50

# --------------------------------------------------------------------------
# pins
#
# NOTE: every analog channel is on ADC1 (32-39). ADC2 pins are unusable for
# analogRead while WiFi is active on ESP32 - a real constraint that would bite
# silently once MQTT came up, so the allocation avoids it entirely.
# --------------------------------------------------------------------------
PIN_SOIL_SHALLOW = 34     # ADC1
PIN_SOIL_DEEP = 35        # ADC1
PIN_PH = 32               # ADC1
PIN_EC = 39               # ADC1 (VN)
PIN_VISION = 33           # ADC1
PIN_LIGHT = 36            # ADC1 (VP)
PIN_DHT = 15
PIN_SOIL_TEMP = 14        # 1-Wire
PIN_TANK_TRIG = 26
PIN_TANK_ECHO = 27
PIN_BTN_RAIN = 4
PIN_BTN_NET = 5
PIN_BTN_FAULT = 13
PIN_VALVE_RELAY = 25
PIN_LED_VALVE = 18
PIN_LED_ALERT = 19
PIN_LED_EDGE = 23
PIN_BUZZER = 2

# --------------------------------------------------------------------------
# agronomic thresholds
#
# General cotton agronomy on medium-textured soil. STARTING POINTS, not
# calibrated field constants. Mirrors iot/fusion/engine.py FusionConfig.
# --------------------------------------------------------------------------
MOISTURE_STRESS = 20.0
MOISTURE_ADEQUATE = 28.0
MOISTURE_WATERLOGGED = 45.0
DRYING_TREND_PER_H = -0.5
HEAT_STRESS_C = 38.0
BLIGHT_HUMIDITY = 80.0
TANK_MIN_PCT = 15.0
LIGHT_MIN_LUX = 120.0
PH_LOW, PH_HIGH = 5.6, 7.8
EC_SALINE = 3.0           # dS/m - osmotic stress becomes plausible
TANK_HEIGHT_CM = 50.0     # sensor mounted at the top of the tank
IRRIGATION_TARGET_L = 10.0

HIST_N = 24
FROZEN_RUN = 6

FAULT_NONE, FAULT_STUCK, FAULT_FAILED = 0, 1, 2
FAULT_NAMES = ("GOOD", "STUCK", "FAILED")


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def pad(text, width):
    """Truncate or space-pad to an exact width.

    MicroPython's str has no ljust()/rjust()/center()/zfill() - they are
    omitted from the port to save flash. Every fixed-width field here goes
    through this instead, because a CPython-only method fails at runtime on
    the board while testing perfectly fine on a laptop.
    """
    text = text[:width]
    return text + " " * (width - len(text))


# --------------------------------------------------------------------------
# SENSOR REGISTRY
#
# The explanation lives with the code, not only in the docs. Printed at boot
# and published to the inventory topic, so anyone watching the simulation can
# see what each channel is and why it earns its place on the mast.
# --------------------------------------------------------------------------
class SensorSpec:
    __slots__ = ("key", "label", "unit", "principle", "why", "normal", "critical")

    def __init__(self, key, label, unit, principle, why, normal, critical):
        self.key = key
        self.label = label
        self.unit = unit
        self.principle = principle
        self.why = why
        self.normal = normal        # (lo, hi) - inside this is GOOD
        self.critical = critical    # (lo, hi) - outside this is implausible

    def quality(self, value):
        """GOOD / DEGRADED / FAILED. An implausible value is a fault, not data."""
        if value is None:
            return "FAILED"
        lo, hi = self.critical
        if not (lo <= value <= hi):
            return "FAILED"
        lo, hi = self.normal
        return "GOOD" if lo <= value <= hi else "DEGRADED"


SENSORS = (
    SensorSpec("soil_root", "Soil moisture (root 300mm)", "%",
               "Capacitive: soil dielectric permittivity (water 80, dry soil 4, air 1)",
               "PRIMARY SIGNAL. Separates water stress from nitrogen deficiency.",
               (28, 45), (0, 100)),
    SensorSpec("soil_shallow", "Soil moisture (surface 100mm)", "%",
               "Capacitive, same principle, shallower placement",
               "Did water arrive? Distinguishes surface wetting from root recharge.",
               (25, 50), (0, 100)),
    SensorSpec("air_temp", "Air temperature", "C",
               "Band-gap junction, ~2mV/C, ratiometric",
               "Evapotranspiration driver, heat-stress threshold, pathogen band.",
               (15, 36), (-10, 60)),
    SensorSpec("humidity", "Relative humidity", "%",
               "Capacitive polymer film; absorbed vapour raises dielectric constant",
               "Leaf-wetness proxy. The environmental half of the disease call.",
               (40, 80), (0, 100)),
    SensorSpec("soil_temp", "Soil temperature", "C",
               "DS18B20 1-Wire digital probe",
               "Root activity; its lag behind air temp cross-checks soil moisture.",
               (18, 34), (-10, 60)),
    SensorSpec("light", "Light level", "lux",
               "Photoconductivity: photons free carriers, resistance falls",
               "IMAGE-QUALITY GATE. A dark frame is not evidence.",
               (120, 1200), (0, 2000)),
    SensorSpec("tank", "Water tank level", "%",
               "Ultrasonic time-of-flight, 40kHz burst, echo timed",
               "Pump-safety gate. A pump run dry destroys itself in minutes.",
               (25, 100), (0, 100)),
    SensorSpec("ph", "Soil pH", "pH",
               "Ion-selective potentiometry, ~59mV per pH unit (Nernst)",
               "Nutrient AVAILABILITY. Nutrients can be present and locked out.",
               (6.0, 7.5), (3.0, 11.0)),
    SensorSpec("ec", "Electrical conductivity", "dS/m",
               "AC conductivity (AC, or DC would electrolyse the soil solution)",
               "Salinity and osmotic stress: wilting despite adequate moisture.",
               (0.4, 2.5), (0, 10)),
    SensorSpec("rain", "Rain detector", "bool",
               "Conductive grid bridged by droplets",
               "SAFETY GATE. Suppresses irrigation into saturated soil.",
               (0, 1), (0, 1)),
    SensorSpec("flow", "Water flow", "L",
               "Hall-effect turbine, pulses per revolution (MODELLED here)",
               "Closes the irrigation loop. Detects blockage, leak, stuck valve.",
               (0, 20), (0, 100)),
    SensorSpec("vision", "Crop vision (disease)", "conf",
               "CNN on the QCS6490 NPU - NOT on this MCU",
               "Symptom evidence. Cannot separate causes that look alike.",
               (0, 0.4), (0, 1)),
)


def print_inventory():
    print()
    print("-" * 66)
    print(" SENSING STACK - what is on the mast and why")
    print("-" * 66)
    for s in SENSORS:
        print("  {:<30} {}".format(s.label + " [" + s.unit + "]", s.why))
    print()
    print("-" * 66)
    print(" Every sensor here covers another one's blind spot. A camera sees")
    print(" symptoms but not cause; a probe sees water but not a lesion. If a")
    print(" sensor's decision cannot be named, it should not be on the mast.")
    print(" Operating principles for each: docs/23_sensing_reference.md")
    print("-" * 66)
    print()


def inventory_payload():
    return {"node": NODE_ID, "simulated": True,
            "sensors": [{"key": s.key, "label": s.label, "unit": s.unit,
                         "principle": s.principle, "why": s.why,
                         "normal": s.normal} for s in SENSORS]}


# --------------------------------------------------------------------------
# low-level drivers
# --------------------------------------------------------------------------
def make_adc(pin):
    """ADC setup differs across MicroPython builds - width() was removed in
    later ESP32 ports. Configure what the running firmware supports."""
    a = ADC(Pin(pin))
    for setter, const in (("atten", "ATTN_11DB"), ("width", "WIDTH_12BIT")):
        try:
            getattr(a, setter)(getattr(ADC, const))
        except (AttributeError, ValueError, OSError):
            pass
    return a


class Ultrasonic:
    """HC-SR04 tank level.

    Emits a 40 kHz burst and times the echo: distance = (speed of sound x t)/2.
    Speed of sound varies ~0.6 m/s per degree C, so we compensate using the air
    temperature this node already measures - one sensor improving another.
    """

    def __init__(self, trig, echo):
        self.trig = Pin(trig, Pin.OUT, value=0)
        self.echo = Pin(echo, Pin.IN)

    def distance_cm(self, air_temp_c=20.0):
        speed_m_s = 331.3 + 0.606 * (air_temp_c if air_temp_c is not None else 20.0)
        self.trig.value(0)
        time.sleep_us(5)
        self.trig.value(1)
        time.sleep_us(10)
        self.trig.value(0)
        try:
            us = time_pulse_us(self.echo, 1, 30000)
        except OSError:
            return None                       # no echo: sensor or wiring fault
        if us < 0:
            return None
        return (us * speed_m_s / 10000.0) / 2.0

    def level_pct(self, air_temp_c=20.0):
        d = self.distance_cm(air_temp_c)
        if d is None:
            return None
        return clamp((TANK_HEIGHT_CM - d) / TANK_HEIGHT_CM * 100.0, 0.0, 100.0)


class SoilTemp:
    """DS18B20, read asynchronously.

    A conversion takes up to 750 ms. Blocking on that would stall the control
    loop, so we trigger the conversion at the end of one cycle and read it at
    the start of the next - the 2 s cycle gives it ample time.
    """

    def __init__(self, pin):
        self.value = None
        self.rom = None
        self.ds = None
        if not HAS_ONEWIRE:
            return
        try:
            self.ds = ds18x20.DS18X20(onewire.OneWire(Pin(pin)))
            roms = self.ds.scan()
            self.rom = roms[0] if roms else None
            if self.rom is None:
                print("[sensor] DS18B20 not found on 1-Wire bus")
        except Exception as exc:
            self.ds = None
            print("[sensor] DS18B20 init failed:", exc)

    def start_conversion(self):
        if self.ds and self.rom:
            try:
                self.ds.convert_temp()
            except Exception:
                pass

    def read(self):
        if not (self.ds and self.rom):
            return None
        try:
            self.value = self.ds.read_temp(self.rom)
        except Exception:
            self.value = None
        return self.value


class Buzzer:
    """Short chirp on a NEW alert only. A continuously sounding field device
    gets muted or unplugged, which destroys the alerting channel entirely."""

    def __init__(self, pin):
        # One PWM instance for the life of the program. Repeatedly calling
        # PWM()/deinit() on the same pin is a known source of flakiness, so we
        # gate the sound with duty instead.
        self.pwm = None
        self.until = 0
        try:
            self.pwm = PWM(Pin(pin), freq=2200)
            self.pwm.duty(0)
        except Exception as exc:
            print("[buzzer] unavailable:", exc)

    def chirp(self, ms=140):
        if not self.pwm:
            return
        try:
            self.pwm.duty(350)
            self.until = time.ticks_add(time.ticks_ms(), ms)
        except Exception:
            pass

    def service(self):
        if self.pwm and self.until and time.ticks_diff(time.ticks_ms(), self.until) >= 0:
            try:
                self.pwm.duty(0)
            except Exception:
                pass
            self.until = 0


# --------------------------------------------------------------------------
# sensor hub
# --------------------------------------------------------------------------
class SensorHub:
    def __init__(self):
        self.soil_shallow = make_adc(PIN_SOIL_SHALLOW)
        self.soil_deep = make_adc(PIN_SOIL_DEEP)
        self.ph_adc = make_adc(PIN_PH)
        self.ec_adc = make_adc(PIN_EC)
        self.vision_adc = make_adc(PIN_VISION)
        self.light_adc = make_adc(PIN_LIGHT)
        self.dht22 = dht.DHT22(Pin(PIN_DHT))
        self.soil_temp = SoilTemp(PIN_SOIL_TEMP)
        self.tank = Ultrasonic(PIN_TANK_TRIG, PIN_TANK_ECHO)
        self._env = (None, None)
        self._env_ms = 0

    @staticmethod
    def _dither():
        """Wokwi's ADC is mathematically ideal. A real capacitive probe in soil
        always jitters by a fraction of a percent. We add that jitter back so
        the stuck-probe detector exercises the genuine signal property: a dead
        probe is detectable because it STOPS jittering."""
        return (time.ticks_us() % 51 - 25) / 1000.0

    def moisture(self, deep=True):
        raw = (self.soil_deep if deep else self.soil_shallow).read()
        return raw * 60.0 / 4095.0 + self._dither()

    def ph(self):
        return 4.0 + self.ph_adc.read() * 5.0 / 4095.0        # 4.0 .. 9.0

    def ec(self):
        return self.ec_adc.read() * 5.0 / 4095.0              # 0 .. 5 dS/m

    def lux(self):
        return self.light_adc.read() * 1200.0 / 4095.0

    def vision_pot(self):
        return self.vision_adc.read() / 4095.0

    def environment(self):
        """DHT22 throws on a failed read. Returning the previous sample would
        be substituting data, so on failure we return None and let the risk
        engine lower its own confidence."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._env_ms) < 2000:
            return self._env
        self._env_ms = now
        try:
            self.dht22.measure()
            self._env = (self.dht22.temperature(), self.dht22.humidity())
        except OSError as exc:
            print("[sensor] DHT22 read failed:", exc)
            self._env = (None, None)
        return self._env


def npk_proxy(ec):
    """Nitrogen indication, derived from conductivity.

    HONESTY NOTE, and this matters: cheap 'NPK sensors' sold for low-cost
    agriculture do NOT perform ion-selective measurement of N, P and K. They
    measure bulk electrical conductivity and apply a vendor correlation. We
    model exactly that, and label it a PROXY - never an absolute nutrient value,
    and never the basis for a fertilizer prescription.

    The system's real nitrogen reasoning does not depend on this at all: it
    works by exclusion, since chlorosis under adequate stable moisture is not
    explained by water. See docs/23_sensing_reference.md section 10.
    """
    if ec is None:
        return "UNKNOWN"
    if ec < 0.8:
        return "LOW"
    if ec < 2.2:
        return "NORMAL"
    return "HIGH"


# --------------------------------------------------------------------------
# rolling history
# --------------------------------------------------------------------------
class History:
    def __init__(self, n=HIST_N):
        self.n = n
        self.buf = []

    def push(self, value):
        if value is None:
            return
        self.buf.append(value)
        if len(self.buf) > self.n:
            self.buf.pop(0)

    def stuck(self):
        """Six bit-identical readings mean the probe died while still
        reporting. The most dangerous sensor failure this system faces, because
        it looks like healthy data: value in range, reading present, trend a
        clean convincing zero - which reads as 'moisture is fine, so this is not
        water' and would send a farmer to buy fertilizer for a crop that may be
        dying of thirst."""
        if len(self.buf) < FROZEN_RUN:
            return False
        tail = self.buf[-FROZEN_RUN:]
        return all(abs(v - tail[0]) < 0.0005 for v in tail)

    def trend_per_hour(self):
        """Least-squares slope in %/hour, or None when there is too little
        data. Never a fabricated zero - a false 'stable' reads as not
        water-driven and skews the diagnosis toward a nutrient explanation."""
        n = len(self.buf)
        if n < 4:
            return None
        xs = [i * 0.5 for i in range(n)]
        mx = sum(xs) / n
        my = sum(self.buf) / n
        den = sum((x - mx) ** 2 for x in xs)
        if den == 0:
            return None
        return sum((x - mx) * (y - my) for x, y in zip(xs, self.buf)) / den


# --------------------------------------------------------------------------
# cloud link - additive, never on the decision path
# --------------------------------------------------------------------------
class CloudLink:
    def __init__(self, on_vision):
        self.on_vision = on_vision
        self.client = None
        self.connected = False
        self.queue = []
        self.dropped = 0
        self.enabled = True

    def wifi(self):
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        if sta.isconnected():
            return True
        print("[wifi] connecting to", WIFI_SSID, end="")
        sta.connect(WIFI_SSID, WIFI_PASS)
        deadline = time.ticks_add(time.ticks_ms(), WIFI_TIMEOUT_S * 1000)
        while not sta.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                print(" timeout")
                print("[wifi] no network - the node runs anyway, this is the point")
                return False
            print(".", end="")
            time.sleep_ms(200)
        print(" connected:", sta.ifconfig()[0])
        return True

    def connect(self):
        if not self.enabled or not HAS_NET:
            return False
        try:
            if not self.wifi():
                return False
            print("[mqtt] contacting", MQTT_BROKER, "...")
            self.client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, keepalive=60)
            self.client.set_callback(self._on_message)
            self.client.connect()
            self.client.subscribe(TOPIC_VISION)
            self.connected = True
            print("[mqtt] connected to", MQTT_BROKER)
            print("[mqtt] publishing ->", TOPIC_BASE + "/#")
            print("[mqtt] listening  <-", TOPIC_VISION)
            return True
        except Exception as exc:
            print("[mqtt] connect failed:", exc, "- continuing offline")
            self.connected = False
            return False

    def _on_message(self, topic, msg):
        name = topic.decode() if isinstance(topic, bytes) else str(topic)
        if name != TOPIC_VISION:
            print("[mqtt] ignoring message on unexpected topic:", name)
            return
        try:
            data = json.loads(msg)
        except (ValueError, TypeError):
            print("[edge-ai] malformed vision payload ignored:", msg)
            return
        self.on_vision(data)

    def poll(self):
        if not (self.connected and self.client):
            return
        try:
            self.client.check_msg()
        except Exception as exc:
            print("[mqtt] link lost while polling:", exc)
            self.connected = False

    def publish(self, topic, payload):
        blob = json.dumps(payload)
        if not (self.enabled and self.connected and self.client):
            self._enqueue(topic, blob)
            return False
        try:
            self.client.publish(topic, blob)
            return True
        except Exception as exc:
            print("[mqtt] publish failed:", exc, "- queueing")
            self.connected = False
            self._enqueue(topic, blob)
            return False

    def _enqueue(self, topic, blob):
        """Bounded. Storage is finite on a field node, so old telemetry is
        dropped oldest-first rather than pretending it all survives."""
        self.queue.append((topic, blob))
        if len(self.queue) > QUEUE_MAX:
            self.queue.pop(0)
            self.dropped += 1

    def drain(self):
        if not (self.connected and self.client) or not self.queue:
            return
        print("[mqtt] replaying {} queued records".format(len(self.queue)))
        while self.queue:
            topic, blob = self.queue[0]
            try:
                self.client.publish(topic, blob)
                self.queue.pop(0)
            except Exception as exc:
                print("[mqtt] replay stalled:", exc)
                self.connected = False
                return
        if self.dropped:
            print("[mqtt] note: {} records dropped while offline (cap {})".format(
                self.dropped, QUEUE_MAX))
            self.dropped = 0

    def cut(self):
        self.enabled = False
        self.connected = False
        try:
            if self.client:
                self.client.disconnect()
        except Exception:
            pass
        self.client = None
        print("[cloud] link DOWN - edge continues, records queue locally")

    def restore(self):
        self.enabled = True
        print("[cloud] restoring link...")
        if self.connect():
            self.drain()


# --------------------------------------------------------------------------
# vision input - pluggable
# --------------------------------------------------------------------------
class VisionInput:
    HOLD_MS = 20000

    def __init__(self, hub):
        self.hub = hub
        self.confidence = 0.0
        self.pests = 0
        self._rx_ms = 0

    def accept(self, data):
        try:
            self.confidence = clamp(float(data.get("disease", 0.0)), 0.0, 1.0)
            self.pests = int(data.get("pests", 0))
        except (TypeError, ValueError):
            print("[edge-ai] vision fields unusable:", data)
            return
        self._rx_ms = time.ticks_ms()
        print("[edge-ai] vision accepted: disease={:.2f} pests={}".format(
            self.confidence, self.pests))

    def refresh(self):
        if not self.fresh:
            self.confidence = self.hub.vision_pot()
            self.pests = 0

    @property
    def fresh(self):
        return bool(self._rx_ms) and time.ticks_diff(
            time.ticks_ms(), self._rx_ms) < self.HOLD_MS

    @property
    def source(self):
        return "mqtt" if self.fresh else "pot"


# --------------------------------------------------------------------------
# risk engine
# --------------------------------------------------------------------------
class Risks:
    __slots__ = ("water", "disease", "pest", "nutrient", "heat", "flood",
                 "confidence", "moisture_valid", "image_usable", "osmotic")


def compute_risks(s, vision):
    """s is the sampled-state dict built in the main loop."""
    R = Risks()
    R.confidence = 1.0
    R.water = R.disease = R.pest = R.nutrient = R.heat = R.flood = 0.0
    R.osmotic = False

    m, t, h = s["m"], s["t"], s["h"]
    m_ok = SPEC["soil_root"].quality(m) != "FAILED"
    t_ok = SPEC["air_temp"].quality(t) != "FAILED"
    h_ok = SPEC["humidity"].quality(h) != "FAILED"
    R.moisture_valid = m_ok

    # --- water stress ---
    if not m_ok:
        R.confidence = 0.35
    else:
        if m < MOISTURE_STRESS:
            R.water += 55
        elif m < MOISTURE_ADEQUATE - 4:
            R.water += 34
        elif m < MOISTURE_ADEQUATE + 1:
            R.water += 15
        if s["trend"] is not None and s["trend"] < DRYING_TREND_PER_H:
            R.water += 18
        if t_ok and t > 36:
            R.water += 18
        elif t_ok and t > 32:
            R.water += 8
        if h_ok and h < 45:
            R.water += 8
        if s["rain"]:
            R.water -= 25

        # Osmotic stress: high salinity means the plant cannot extract water
        # even from adequate soil moisture. Without EC, a plant wilting in wet
        # soil looks like a sensor fault or a disease.
        if s["ec"] is not None and s["ec"] > EC_SALINE and m >= MOISTURE_ADEQUATE:
            R.water += 20
            R.osmotic = True

    # --- disease: vision + environment, neither sufficient alone ---
    R.image_usable = s["lux"] is not None and s["lux"] >= LIGHT_MIN_LUX
    weight = 1.0 if R.image_usable else 0.35
    if not R.image_usable:
        R.confidence = min(R.confidence, 0.6)

    R.disease = vision.confidence * 55.0 * weight
    if h_ok and h > BLIGHT_HUMIDITY:
        R.disease += 22
    elif h_ok and h > 70:
        R.disease += 10
    if t_ok and 26 < t < 34:
        R.disease += 12

    R.pest = min(100.0, vision.pests * 6.5)

    # --- nutrient: availability, not quantity ---
    if s["n_proxy"] == "LOW":
        R.nutrient += 40
    if s["ph"] is not None and not (PH_LOW <= s["ph"] <= PH_HIGH):
        R.nutrient += 30                      # lock-out, not absence
    if s["ec"] is not None and s["ec"] > EC_SALINE:
        R.nutrient += 15

    R.heat = clamp((t - 33.0) * 11.0, 0.0, 100.0) if t_ok else 0.0
    R.flood = clamp((45.0 if s["rain"] else 0.0) +
                    (max(0.0, m - MOISTURE_WATERLOGGED) * 6.0 if m_ok else 0.0),
                    0.0, 100.0)

    R.water = clamp(R.water, 0.0, 100.0)
    R.disease = clamp(R.disease, 0.0, 100.0)
    R.nutrient = clamp(R.nutrient, 0.0, 100.0)
    return R


def band(v):
    return "HIGH" if v >= 60 else "MED" if v >= 32 else "LOW"


# --------------------------------------------------------------------------
# decision engine - safety gates first
# --------------------------------------------------------------------------
class Decision:
    __slots__ = ("title", "detail", "reasons", "irrigate", "alert")

    def __init__(self, title, detail, reasons, irrigate=False, alert=False):
        self.title = title
        self.detail = detail
        self.reasons = reasons
        self.irrigate = irrigate
        self.alert = alert


def decide(s, R, hist, vision):
    m, t, h, tank = s["m"], s["t"], s["h"], s["tank"]

    # 1. A failed primary sensor is not a diagnosis. Never substitute a value.
    if not R.moisture_valid:
        return Decision("MANUAL CHECK", "soil probe unavailable",
                        ["Soil moisture: FAILED",
                         "No value substituted",
                         "Water confidence LOW"], alert=True)

    # 2. A stuck probe is worse than a missing one - it looks healthy.
    if hist.stuck():
        return Decision("MANUAL CHECK", "soil probe stuck",
                        ["Readings unchanging",
                         "Channel excluded",
                         "Probe needs service"], alert=True)

    # 3. Tank sensor lost: do not actuate on an unknown supply.
    if tank is None:
        return Decision("MANUAL CHECK", "tank level unknown",
                        ["Ultrasonic: no echo",
                         "Supply unverifiable",
                         "Valve held shut"], alert=True)

    # 4. Rain and saturation - two distinct situations, not one.
    #
    # Saturation is decided by the SOIL, not by the weather. Rain falling on
    # dry ground is good news, and treating it as a hazard would cry wolf; what
    # matters is whether the root zone is actually above field capacity.
    waterlogged = m > MOISTURE_WATERLOGGED
    if R.flood >= 45 or waterlogged:
        if R.water >= 45:
            # The crop wanted water and the weather is already supplying it.
            return Decision("DELAY IRRIGATION", "rain is supplying the crop",
                            ["Rain detected" if s["rain"] else "Recent rainfall",
                             "Moisture {:.0f}%, stress was building".format(m),
                             "Let the rain do it - valve stays shut"], alert=True)
        if waterlogged:
            # Nothing wanted water, but the root zone is saturated. That is its
            # own hazard - root anoxia and raised disease pressure - and
            # reporting "no action" here would be wrong.
            return Decision("WATERLOGGING", "drainage check advised",
                            ["Moisture {:.0f}% above saturation".format(m),
                             "Rain detected" if s["rain"] else "Soil not draining",
                             "Root anoxia and disease pressure rise",
                             "Irrigation suppressed"], alert=True)

    # 5. Osmotic stress, checked BEFORE irrigation.
    # A plant in saline soil wilts despite adequate moisture because it cannot
    # osmotically extract the water. Irrigating would waste water and
    # concentrate the salts further, so this gate sits above the water branch.
    if R.osmotic:
        return Decision("SALINITY CHECK", "high EC in moist soil",
                        ["EC {:.1f} dS/m above {:.1f}".format(s["ec"], EC_SALINE),
                         "Moisture {:.0f}% adequate".format(m),
                         "Osmotic stress, not drought",
                         "Irrigation would worsen salts"], alert=True)

    # 6. Water stress, gated on tank safety.
    if R.water >= 55:
        if tank < TANK_MIN_PCT:
            return Decision("TANK REFILL", "irrigation blocked",
                            ["Water stress " + band(R.water),
                             "Tank {:.0f}% < 15%".format(tank),
                             "Valve held shut - dry run kills the pump"], alert=True)
        reasons = ["Moisture {:.0f}% below thresh".format(m)]
        if s["trend"] is not None:
            reasons.append("Trend {:.2f} %/h falling".format(s["trend"]))
        reasons.append("Air temp {:.0f}C".format(t) if t is not None else "Temp n/a")
        reasons.append("Rain: none" if not s["rain"] else "Rain: YES")
        return Decision("IRRIGATE NOW", "zone water stress", reasons, irrigate=True)

    # 7. Disease / pest - advisory only, never an automatic chemical.
    if R.disease >= 60 or R.pest >= 60:
        return Decision(
            "INSPECT ZONE",
            "pest activity rising" if R.pest > R.disease else "disease risk high",
            ["Vision conf {:.0f}%".format(vision.confidence * 100)
             if R.image_usable else "Frame too dark - discounted",
             "Humidity {:.0f}%".format(h) if h is not None else "Humidity n/a",
             "Temp {:.0f}C in band".format(t) if t is not None else "Temp n/a",
             "Advisory - no spray Rx"], alert=True)

    # 8. Nutrient - advisory, and honest about what it rests on.
    if R.nutrient >= 55:
        reasons = []
        if s["ph"] is not None and not (PH_LOW <= s["ph"] <= PH_HIGH):
            reasons.append("pH {:.1f} outside {:.1f}-{:.1f}".format(
                s["ph"], PH_LOW, PH_HIGH))
            reasons.append("Nutrients may be locked out")
        if s["n_proxy"] == "LOW":
            reasons.append("N indication LOW (EC proxy)")
        reasons.append("Soil test before fertiliser")
        return Decision("SOIL TEST", "nutrient availability suspect",
                        reasons, alert=True)

    # 9. Heat.
    if R.heat >= 60:
        return Decision("HEAT STRESS", "monitor closely",
                        ["Air temp {:.0f}C".format(t),
                         "Above {:.0f}C threshold".format(HEAT_STRESS_C)], alert=True)

    return Decision("NO ACTION", "all signals normal",
                    ["Moisture {:.0f}% ok".format(m),
                     "Temp {:.0f}C ok".format(t) if t is not None else "Temp n/a",
                     "No visual evidence"])


# --------------------------------------------------------------------------
# display
# --------------------------------------------------------------------------
class SSD1306:
    """Minimal SSD1306 I2C driver, embedded on purpose.

    MicroPython does not bundle an SSD1306 driver, and Wokwi has no library
    manager for MicroPython - so depending on an external ssd1306.py means the
    display silently fails for anyone who forgets to add the file. Embedding
    ~50 lines removes that failure mode entirely.

    Drawing comes free from framebuf.FrameBuffer (text, fill, hline, pixel...);
    this class only adds the I2C command sequence and the RAM flush.
    """

    def __init__(self, i2c, width=128, height=64, addr=0x3C):
        self.i2c = i2c
        self.addr = addr
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        self.fb = framebuf.FrameBuffer(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _cmd(self, c):
        self.i2c.writeto(self.addr, bytes((0x80, c)))

    def _init_display(self):
        for c in (
            0xAE,                       # display off
            0xD5, 0x80,                 # clock divide / oscillator
            0xA8, self.height - 1,      # multiplex ratio
            0xD3, 0x00,                 # display offset
            0x40,                       # start line 0
            0x8D, 0x14,                 # charge pump ON (no external Vcc)
            0x20, 0x00,                 # horizontal addressing mode
            0xA1,                       # segment remap (left/right flip)
            0xC8,                       # COM scan direction (up/down flip)
            0xDA, 0x12,                 # COM pin config for 128x64
            0x81, 0xCF,                 # contrast
            0xD9, 0xF1,                 # pre-charge period
            0xDB, 0x40,                 # VCOMH deselect level
            0xA4,                       # output follows RAM
            0xA6,                       # normal (not inverted)
            0xAF,                       # display on
        ):
            self._cmd(c)
        self.fill(0)
        self.show()

    # framebuf pass-throughs
    def fill(self, c):
        self.fb.fill(c)

    def text(self, s, x, y, c=1):
        self.fb.text(s, x, y, c)

    def hline(self, x, y, w, c=1):
        self.fb.hline(x, y, w, c)

    def show(self):
        self._cmd(0x21); self._cmd(0); self._cmd(self.width - 1)    # column range
        self._cmd(0x22); self._cmd(0); self._cmd(self.pages - 1)    # page range
        self.i2c.writeto(self.addr, b"\x40" + self.buffer)


class LCD2004:
    """20x4 character LCD on an I2C backpack (PCF8574 -> HD44780, 4-bit mode).

    The OLED is 128x64 px and honest about what a real node would carry, but it
    is unreadable across a room or in a screenshot. This second display sits in
    the free space below the circuit and shows the same pages in characters
    four times the size - a demo aid, not a claim about the field hardware.

    Backpack bit map: P0=RS, P1=RW, P2=EN, P3=backlight, P4..P7=D4..D7.
    """

    ROW_ADDR = (0x00, 0x40, 0x14, 0x54)
    BACKLIGHT = 0x08
    EN = 0x04

    def __init__(self, i2c, addr, cols=20, rows=4):
        self.i2c = i2c
        self.addr = addr
        self.cols = cols
        self.rows = rows
        self.shown = [""] * rows          # only redraw lines that changed
        self._boot()

    def _raw(self, b):
        self.i2c.writeto(self.addr, bytes((b,)))

    def _pulse(self, b):
        self._raw(b | self.EN)
        self._raw(b & ~self.EN)

    def _send(self, value, rs):
        base = self.BACKLIGHT | (0x01 if rs else 0x00)
        self._pulse(base | (value & 0xF0))
        self._pulse(base | ((value << 4) & 0xF0))

    def _boot(self):
        time.sleep_ms(50)
        # Knock the controller into 4-bit mode: three 0x30s, then 0x20.
        for _ in range(3):
            self._pulse(self.BACKLIGHT | 0x30)
            time.sleep_ms(5)
        self._pulse(self.BACKLIGHT | 0x20)
        time.sleep_ms(5)
        for cmd in (0x28,      # 4-bit, 2-line mapping, 5x8 font
                    0x0C,      # display on, cursor off, no blink
                    0x06,      # entry mode: advance, no shift
                    0x01):     # clear
            self._send(cmd, False)
            time.sleep_ms(3)

    def line(self, row, text):
        """Write one padded row, skipping it entirely if it has not changed."""
        text = pad(text, self.cols)
        if self.shown[row] == text:
            return
        self.shown[row] = text
        self._send(0x80 | self.ROW_ADDR[row], False)
        for ch in text:
            self._send(ord(ch), True)


# The OLED is 128x64 with an 8x8 font: 16 characters wide, 8 rows tall.
# One function describes a page, and both the physical display and the serial
# mirror render from it - so the text in the monitor pane can never drift away
# from the text on the glass.
RULE = None
SCREEN_COLS = 16


def screen_rows(page, s, R, d, cloud):
    """The exact content of one OLED page as (y, segments) rows.

    A row is either RULE (a horizontal divider) or a list of (x, text)
    segments, x in pixels so the display can place them literally.
    """
    rows = [(0, [(0, "EDGE:OK"),
                 (64, "CLOUD:UP" if cloud.connected else "CLOUD:DN")]),
            (10, RULE)]

    if page == 0:
        rows.append((14, [(0, d.title[:16])]))
        rows.append((24, [(0, d.detail[:16])]))
        rows.append((33, RULE))
        for i, r in enumerate(d.reasons[:3]):
            rows.append((36 + i * 9, [(0, "-" + r[:15])]))

    elif page == 1:
        if s["stuck"]:
            soil = "Soil : STUCK"
        elif s["m"] is None:
            soil = "Soil : FAILED"
        else:
            soil = "Soil : {:.1f} %".format(s["m"])
        rows.append((14, [(0, soil)]))
        rows.append((24, [(0, _kv("Surf", s["m_shallow"], "%"))]))
        rows.append((34, [(0, _kv("Air", s["t"], "C"))]))
        rows.append((44, [(0, _kv("Soil", s["soil_t"], "C"))]))
        rows.append((54, [(0, _kv("Hum", s["h"], "%"))]))

    elif page == 2:
        rows.append((14, [(0, _kv("pH", s["ph"], ""))]))
        rows.append((24, [(0, _kv("EC", s["ec"], "dS"))]))
        rows.append((34, [(0, "N    : " + s["n_proxy"])]))
        rows.append((44, [(0, _kv("Lux", s["lux"], ""))]))
        rows.append((54, [(0, "Rain : " + ("YES" if s["rain"] else "NO"))]))

    elif page == 3:
        bands = (("Water", R.water), ("Disease", R.disease), ("Pest", R.pest),
                 ("Nutrient", R.nutrient), ("Flood", R.flood))
        for i, (name, v) in enumerate(bands):
            rows.append((14 + i * 10, [(0, "{:<9}{}".format(name, band(v)))]))

    else:
        rows.append((14, [(0, _kv("Tank", s["tank"], "%"))]))
        rows.append((24, [(0, "Flow : {:.1f} L".format(s["flow"]))]))
        rows.append((34, [(0, "Queued: {}".format(len(cloud.queue)))]))
        rows.append((44, RULE))
        rows.append((50, [(0, "Decision ACTIVE")]))

    return rows


LCD_COLS, LCD_ROWS = 20, 4


def _num(value, unit=""):
    return "n/a" if value is None else "{:.1f}{}".format(value, unit)


def lcd_lines(page, s, R, d, cloud):
    """The same five pages laid out for 20 columns and three content rows.

    Twenty columns fit two fields per line, so nothing from the OLED page is
    lost - the rows are paired rather than truncated.
    """
    tag = "C:UP" if cloud.connected else "C:DN"
    head = "{} {}/{}".format(PAGE_NAMES[page], page + 1, Display.PAGES)
    head = pad(head[:LCD_COLS - 5], LCD_COLS - 4) + tag

    if page == 0:
        body = [d.title, d.detail, d.reasons[0] if d.reasons else ""]

    elif page == 1:
        if s["stuck"]:
            root = "Root STUCK"
        elif s["m"] is None:
            root = "Root FAILED"
        else:
            root = "Root {:.1f}%".format(s["m"])
        body = ["{:<12}Srf {:.0f}%".format(root, s["m_shallow"]),
                "Air {} Soil {}".format(_num(s["t"], "C"), _num(s["soil_t"], "C")),
                "Humidity {}".format(_num(s["h"], "%"))]

    elif page == 2:
        body = ["pH {}   EC {} dS".format(_num(s["ph"]), _num(s["ec"])),
                "N:{:<6} Lux {:.0f}".format(s["n_proxy"], s["lux"]),
                "Rain: " + ("YES" if s["rain"] else "NO")]

    elif page == 3:
        body = ["Water {:<5} Dis {}".format(band(R.water), band(R.disease)),
                "Pest  {:<5} Ntr {}".format(band(R.pest), band(R.nutrient)),
                "Flood {}".format(band(R.flood))]

    else:
        body = ["Tank {}  Flow {:.1f}L".format(
            "n/a" if s["tank"] is None else "{:.0f}%".format(s["tank"]),
            s["flow"]),
                "Queued {}".format(len(cloud.queue)),
                "Decision ACTIVE"]

    return [head] + [b[:LCD_COLS] for b in body[:LCD_ROWS - 1]]


def _mirror_line(segments):
    """Flatten one row's pixel-positioned segments into 16 monospace columns."""
    line = [" "] * SCREEN_COLS
    for x, text in segments:
        col = x // 8
        for i, ch in enumerate(text[:SCREEN_COLS - col]):
            line[col + i] = ch
    return "".join(line).rstrip()


PAGE_NAMES = ("DECISION", "SOIL+AIR", "CHEMISTRY", "RISK BANDS", "SUPPLY")


def print_screen(page, rows):
    """Draw the same page into the serial monitor as a framed 16-column box.

    Wokwi's OLED is small and screenshots badly; this makes the field display
    readable in the log pane below the diagram, and leaves a text record of
    what the node actually showed at each moment.
    """
    # The caption sits outside the frame: the box is exactly as wide as the
    # glass, so what you read here is what a farmer reads in the field.
    print("   ." + "-" * SCREEN_COLS + ".   OLED {}/{}  {}".format(
        page + 1, Display.PAGES, PAGE_NAMES[page]))
    for _y, segs in rows:
        text = "-" * SCREEN_COLS if segs is RULE else _mirror_line(segs)
        print("   |" + pad(text, SCREEN_COLS) + "|")
    print("   '" + "-" * SCREEN_COLS + "'")


class Display:
    PAGES = 5

    def __init__(self):
        self.oled = None
        self.lcd = None
        try:
            i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
            found = i2c.scan()
            print("[i2c] devices found:", [hex(a) for a in found] or "none")
            if not found:
                print("[display] no I2C device - check SDA=21 / SCL=22 wiring")
                return
        except Exception as exc:
            print("[display] I2C bus unavailable ({}); running headless".format(exc))
            return

        # Two displays share one bus at different addresses. Each is optional:
        # a missing panel degrades the demo, it must never stop the node.
        oled_addr = 0x3C if 0x3C in found else (0x3D if 0x3D in found else None)
        if oled_addr is not None:
            try:
                self.oled = SSD1306(i2c, 128, 64, oled_addr)
                print("[display] SSD1306 128x64 ready at", hex(oled_addr))
            except Exception as exc:
                print("[display] SSD1306 init failed:", exc)

        lcd_addr = None
        for candidate in (0x27, 0x3F):       # common PCF8574 backpack addresses
            if candidate in found:
                lcd_addr = candidate
                break
        if lcd_addr is not None:
            try:
                self.lcd = LCD2004(i2c, lcd_addr)
                print("[display] LCD 20x4 ready at", hex(lcd_addr),
                      "- large mirror of the OLED, below the circuit")
            except Exception as exc:
                print("[display] LCD init failed:", exc)
        else:
            print("[display] no 20x4 LCD on the bus - OLED only")

    def splash(self):
        lines = ("SMART FARM", "SENTINEL", "edge booting...")
        if self.lcd:
            self.lcd.line(0, "SMART FARM SENTINEL")
            self.lcd.line(1, "SIH PS 26180  edge")
            self.lcd.line(2, "booting sensors...")
            self.lcd.line(3, "no cloud needed")
        if self.oled:
            self.oled.fill(0)
            for i, text in enumerate(lines):
                self.oled.text(text, 0, 16 + i * 12)
            self.oled.show()
        print("   ." + "-" * SCREEN_COLS + ".   OLED  boot")
        for text in lines:
            print("   |" + pad(text, SCREEN_COLS) + "|")
        print("   '" + "-" * SCREEN_COLS + "'")

    def draw(self, page, s, R, d, cloud):
        """Paint one page onto the glass, then mirror it to the LCD and log.

        Every panel is guarded on its own. A display is an output, never a
        dependency - a failing panel drops itself and the node keeps deciding.
        """
        rows = screen_rows(page, s, R, d, cloud)
        if self.oled:
            try:
                o = self.oled
                o.fill(0)
                for y, segs in rows:
                    if segs is RULE:
                        o.hline(0, y, 128, 1)
                        continue
                    for x, text in segs:
                        o.text(text, x, y)
                o.show()
            except Exception as exc:
                print("[display] OLED write failed:", exc)
                self.oled = None
        if self.lcd:
            try:
                for i, text in enumerate(lcd_lines(page, s, R, d, cloud)):
                    self.lcd.line(i, text)
            except Exception as exc:
                print("[display] LCD write failed:", exc)
                self.lcd = None
        print_screen(page, rows)


def _kv(label, value, unit):
    if value is None:
        return "{:<5}: n/a".format(label)
    return "{:<5}: {:.1f}{}".format(label, value, unit)


class Button:
    def __init__(self, pin):
        self.pin = Pin(pin, Pin.IN, Pin.PULL_UP)
        self._last = 0

    def pressed(self):
        if self.pin.value() == 0 and time.ticks_diff(time.ticks_ms(), self._last) > 300:
            self._last = time.ticks_ms()
            return True
        return False


SPEC = {s.key: s for s in SENSORS}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    print_inventory()

    print("[boot] initialising sensors...")
    hub = SensorHub()
    hist = History()
    vision = VisionInput(hub)

    print("[boot] initialising display...")
    display = Display()
    display.splash()

    btn_rain = Button(PIN_BTN_RAIN)
    btn_net = Button(PIN_BTN_NET)
    btn_fault = Button(PIN_BTN_FAULT)
    relay = Pin(PIN_VALVE_RELAY, Pin.OUT, value=0)
    led_valve = Pin(PIN_LED_VALVE, Pin.OUT)
    led_alert = Pin(PIN_LED_ALERT, Pin.OUT)
    led_edge = Pin(PIN_LED_EDGE, Pin.OUT)
    buzzer = Buzzer(PIN_BUZZER)

    # The cloud link is created but NOT connected here. Bringing up WiFi first
    # would leave the node blind for several seconds while the one thing it is
    # supposed to prove - that it decides locally - sits waiting on a network.
    # The control loop starts immediately; the link is raised after the first
    # decision has already been made and shown.
    cloud = CloudLink(vision.accept)
    cloud_started = False

    print()
    print("[boot] sensors and I/O ready - deciding now, before any network")
    print("Buttons: RAIN | NET (cut/restore cloud) | FAULT (stuck->failed)")
    print("Inject vision: publish {\"disease\":0.85,\"pests\":6} to", TOPIC_VISION)
    print()

    rain = False
    fault = FAULT_NONE
    held = None
    valve_open = False
    litres = 0.0
    session_litres = 0.0
    page = 0
    frame = None                 # last (state, risks, decision) drawn
    edge_on = False
    seq = 0
    prev_alert = False

    print("[loop] control loop running - first decision due immediately")
    hub.soil_temp.start_conversion()
    last_page = last_blink = time.ticks_ms()
    last_sample = time.ticks_add(time.ticks_ms(), -3000)   # sample on entry
    last_cloud_try = 0

    while True:
        cloud.poll()
        buzzer.service()
        now = time.ticks_ms()

        if btn_rain.pressed():
            rain = not rain
            print("[sensor] rain =", "YES" if rain else "NO")
        if btn_net.pressed():
            cloud.cut() if cloud.enabled else cloud.restore()
        if btn_fault.pressed():
            fault = (fault + 1) % 3
            held = None
            print("[fault] soil probe =", FAULT_NAMES[fault])

        # Edge heartbeat, deliberately independent of network state.
        if time.ticks_diff(now, last_blink) > 900:
            last_blink = now
            edge_on = not edge_on
            led_edge.value(edge_on)

        if time.ticks_diff(now, last_sample) > 2000:
            last_sample = now
            seq += 1

            m_shallow = hub.moisture(deep=False)
            m = hub.moisture(deep=True)

            # Root-zone probe drives the decision. The shallow one says what the
            # surface did after rain; only the deep one says what the plant can
            # actually drink.
            if fault == FAULT_FAILED:
                m = None
            elif fault == FAULT_STUCK:
                if held is None:
                    held = m
                m = held                     # dead probe repeats its last value

            t, h = hub.environment()
            soil_t = hub.soil_temp.read()
            hub.soil_temp.start_conversion()          # async: ready next cycle
            tank = hub.tank.level_pct(t)
            ph = hub.ph()
            ec = hub.ec()
            lux = hub.lux()
            vision.refresh()

            hist.push(m)

            s = {"m": m, "m_shallow": m_shallow, "t": t, "h": h, "soil_t": soil_t,
                 "tank": tank, "ph": ph, "ec": ec, "lux": lux, "rain": rain,
                 "trend": hist.trend_per_hour(), "n_proxy": npk_proxy(ec),
                 "stuck": hist.stuck(), "flow": session_litres}

            R = compute_risks(s, vision)
            d = decide(s, R, hist, vision)

            # Actuation. Advisory system, but the valve is the one controlled
            # action - and it is gated on a verified supply.
            if d.irrigate and tank is not None and tank >= TANK_MIN_PCT:
                if not valve_open:
                    session_litres = 0.0
                valve_open = True
                session_litres += 0.7        # modelled flow, ~0.35 L/s
                litres += 0.7
                if session_litres >= IRRIGATION_TARGET_L:
                    valve_open = False
                    print("[valve] cycle complete: {:.1f} L delivered "
                          "(target {:.0f} L)".format(session_litres,
                                                     IRRIGATION_TARGET_L))
            else:
                valve_open = False

            relay.value(valve_open)
            led_valve.value(valve_open)
            led_alert.value(d.alert)
            if d.alert and not prev_alert:
                buzzer.chirp()               # chirp on NEW alerts only
            prev_alert = d.alert
            s["flow"] = session_litres

            # Publish AFTER the decision. Networking is never upstream of advice.
            cloud.publish(TOPIC_TELEMETRY, {
                "seq": seq, "node": NODE_ID, "simulated": True,
                "soil_root": None if m is None else round(m, 1),
                "soil_surface": round(m_shallow, 1),
                "soil_state": "FAILED" if m is None else ("STUCK" if s["stuck"] else "OK"),
                "air_temp_c": t, "humidity_pct": h, "soil_temp_c": soil_t,
                "tank_pct": None if tank is None else round(tank, 0),
                "ph": round(ph, 2), "ec_ds_m": round(ec, 2),
                "n_indication": s["n_proxy"], "n_note": "EC-derived proxy, not ion-selective",
                "lux": round(lux, 0), "rain": rain,
                "trend_pct_per_h": None if s["trend"] is None else round(s["trend"], 2),
                "flow_l": round(session_litres, 1),
                "vision_source": vision.source,
                "quality": {k: SPEC[k].quality(v) for k, v in (
                    ("soil_root", m), ("air_temp", t), ("humidity", h),
                    ("soil_temp", soil_t), ("tank", tank), ("ph", ph),
                    ("ec", ec), ("light", lux))},
            })
            cloud.publish(TOPIC_DECISION, {
                "seq": seq, "node": NODE_ID, "advisory_only": True,
                "action": d.title, "detail": d.detail, "why": d.reasons,
                "valve_open": valve_open,
                "risk": {"water": round(R.water), "disease": round(R.disease),
                         "pest": round(R.pest), "nutrient": round(R.nutrient),
                         "heat": round(R.heat), "flood": round(R.flood)},
                "confidence": R.confidence,
            })
            if cloud.connected and cloud.queue:
                cloud.drain()

            # Serial block, deliberately short lines. Wokwi's monitor pane is
            # only a few rows tall, and a 200-character line wraps into an
            # unreadable smear - the point of this output is to be watchable
            # live, not to be dense.
            soil = ("FAILED" if m is None
                    else "STUCK {:.1f}%".format(m) if s["stuck"]
                    else "{:.1f}%".format(m))
            trend_txt = ("" if s["trend"] is None
                         else " ({:+.2f}/h)".format(s["trend"]))
            print("[{:04d}] {} - {}".format(seq, d.title, d.detail))
            print("   soil {}{}  surf {:.1f}%  air {}  RH {}  soilT {}".format(
                soil, trend_txt, m_shallow,
                "n/a" if t is None else "{:.1f}C".format(t),
                "n/a" if h is None else "{:.0f}%".format(h),
                "n/a" if soil_t is None else "{:.1f}C".format(soil_t)))
            print("   tank {}  pH {:.1f}  EC {:.1f}  N:{}  lux {:.0f}{}  rain:{}".format(
                "n/a" if tank is None else "{:.0f}%".format(tank),
                ph, ec, s["n_proxy"], lux,
                "" if R.image_usable else "(dark)", "Y" if rain else "N"))
            print("   risk W:{} D:{} P:{} N:{}  valve {}  cloud {}".format(
                band(R.water), band(R.disease), band(R.pest), band(R.nutrient),
                "OPEN {:.1f}L".format(session_litres) if valve_open else "shut",
                "up" if cloud.connected
                else "DOWN q={}".format(len(cloud.queue))))

            frame = (s, R, d)
            display.draw(page, s, R, d, cloud)

            # Cloud comes up only after the node has already decided and shown
            # a result. Retry quietly every 30 s if the link is wanted but down.
            if not cloud_started:
                cloud_started = True
                print("[boot] first decision made locally - "
                      "now raising the optional cloud link")
                if cloud.connect():
                    cloud.publish(TOPIC_INVENTORY, inventory_payload())
                last_cloud_try = time.ticks_ms()
            elif (cloud.enabled and not cloud.connected and
                  time.ticks_diff(time.ticks_ms(), last_cloud_try) > 30000):
                last_cloud_try = time.ticks_ms()
                if cloud.connect():
                    cloud.publish(TOPIC_INVENTORY, inventory_payload())
                    cloud.drain()

        # Rotate the page on its own clock and redraw immediately from the
        # last decision, so the mirrored block in the monitor always matches
        # what the OLED is showing right now.
        if time.ticks_diff(now, last_page) > 3200:
            last_page = now
            page = (page + 1) % Display.PAGES
            if frame is not None:
                display.draw(page, frame[0], frame[1], frame[2], cloud)

        time.sleep_ms(50)


try:
    main()
except Exception as exc:
    # A node frozen on its splash screen tells you nothing. Print the
    # whole traceback so the failing line is named in the monitor.
    print()
    print("=" * 66)
    print("[FATAL] sentinel loop stopped:", exc)
    try:
        import sys
        sys.print_exception(exc)
    except Exception:
        pass
    print("=" * 66)
    raise
