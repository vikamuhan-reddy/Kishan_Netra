"""Exercise the Wokwi MicroPython firmware's decision logic on CPython.

Run:  python test_firmware.py

The firmware cannot be unit-tested on the board, but its logic is pure Python.
This stubs the MicroPython-only modules, strips the trailing main() call, and
drives compute_risks/decide with synthetic field states. It has already caught
one real gap: a waterlogged field reporting "no action".

"""
import sys
import types
import time as _time
import pathlib

# ---- stub MicroPython modules -------------------------------------------
def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Stub:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _):
        return lambda *a, **k: 0


_mod("machine", Pin=_Stub, ADC=_Stub, SoftI2C=_Stub, PWM=_Stub,
     time_pulse_us=lambda *a: 100)
_mod("dht", DHT22=_Stub)
_mod("onewire", OneWire=_Stub)
_mod("ds18x20", DS18X20=_Stub)
_mod("network", STA_IF=0, WLAN=_Stub)
_mod("framebuf", FrameBuffer=_Stub, MONO_VLSB=0)
umqtt = types.ModuleType("umqtt")
umqtt.__path__ = []
sys.modules["umqtt"] = umqtt
_mod("umqtt.simple", MQTTClient=_Stub)

# MicroPython time extensions
_time.ticks_ms = lambda: int(_time.time() * 1000)
_time.ticks_us = lambda: int(_time.time() * 1000000)
_time.ticks_diff = lambda a, b: a - b
_time.ticks_add = lambda a, b: a + b
_time.sleep_ms = lambda ms: None
_time.sleep_us = lambda us: None

# ---- load the firmware without running main() ---------------------------
path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                    else pathlib.Path(__file__).parent / "main.py")
src = path.read_text(encoding="utf-8")
marker = "\ntry:\n    main()"
assert marker in src, "could not find the main() guard to strip"
src = src[:src.index(marker)]

fw = types.ModuleType("fw")
fw.__dict__["__name__"] = "fw"
exec(compile(src, str(path), "exec"), fw.__dict__)
print("firmware module loaded, main() not executed\n")


class FakeVision:
    def __init__(self, confidence=0.0, pests=0):
        self.confidence = confidence
        self.pests = pests


class FakeHist:
    def __init__(self, stuck=False):
        self._stuck = stuck

    def stuck(self):
        return self._stuck


def state(**kw):
    s = {"m": 34.0, "m_shallow": 34.0, "t": 30.0, "h": 60.0, "soil_t": 26.0,
         "tank": 70.0, "ph": 6.6, "ec": 1.1, "lux": 800.0, "rain": False,
         "trend": -0.1, "n_proxy": "NORMAL", "stuck": False, "flow": 0.0}
    s.update(kw)
    return s


def run(name, s, vision=None, hist=None, expect=None):
    vision = vision or FakeVision()
    hist = hist or FakeHist()
    R = fw.compute_risks(s, vision)
    d = fw.decide(s, R, hist, vision)
    ok = (d.title == expect) if expect else True
    flag = "PASS" if ok else "FAIL"
    print("[{}] {:<26} -> {:<16} ({})".format(flag, name, d.title, d.detail))
    if not ok:
        print("        expected:", expect)
    for r in d.reasons[:3]:
        print("           . " + r)
    return ok


results = []
results.append(run("healthy field", state(), expect="NO ACTION"))
results.append(run("dry root zone", state(m=16.0, trend=-1.2, t=39.0),
                   expect="IRRIGATE NOW"))
results.append(run("dry + empty tank", state(m=16.0, trend=-1.2, t=39.0, tank=8.0),
                   expect="TANK REFILL"))
results.append(run("waterlogged field", state(m=47.0, trend=0.5, rain=True),
                   expect="WATERLOGGING"))
results.append(run("dry but rain arrived", state(m=16.0, trend=-1.2, t=39.0, rain=True),
                   expect="DELAY IRRIGATION"))
results.append(run("over-irrigated, no rain", state(m=52.0, trend=0.2, rain=False),
                   expect="WATERLOGGING"))
results.append(run("light shower on dry soil", state(m=24.0, trend=-0.8, t=34.0, rain=True),
                   expect="NO ACTION"))
results.append(run("probe failed", state(m=None), expect="MANUAL CHECK"))
results.append(run("probe stuck", state(), hist=FakeHist(stuck=True),
                   expect="MANUAL CHECK"))
results.append(run("tank sensor lost", state(tank=None), expect="MANUAL CHECK"))
results.append(run("disease evidence", state(h=88.0, t=30.0),
                   vision=FakeVision(confidence=0.9), expect="INSPECT ZONE"))
results.append(run("dark frame, same vision", state(h=88.0, t=30.0, lux=20.0),
                   vision=FakeVision(confidence=0.9)))
results.append(run("saline moist soil", state(m=34.0, ec=4.2, t=38.0, h=40.0),
                   expect="SALINITY CHECK"))
results.append(run("ph lockout", state(ph=8.6, n_proxy="LOW", ec=0.5),
                   expect="SOIL TEST"))
results.append(run("heat wave", state(m=34.0, t=44.0, h=55.0), expect=None))

print("\nnpk_proxy mapping:", [(e, fw.npk_proxy(e)) for e in (0.4, 1.5, 3.5, None)])

print("\nsensor quality bands:")
for key, val in (("soil_root", 34.0), ("soil_root", 247.0), ("soil_root", None),
                 ("ph", 6.6), ("ph", 9.9), ("light", 20.0)):
    print("   {:<10} {!r:>7} -> {}".format(key, val, fw.SPEC[key].quality(val)))

print("\nSENSORS registry:", len(fw.SENSORS), "channels")
print("\nRESULT:", "all expectations met" if all(results) else "SOME FAILED")
