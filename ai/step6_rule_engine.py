"""
Step 6 — Rule-Based Logic Engine (no training)
Nutrient, irrigation, disease fusion, and trend layer.
All sensor values are SIMULATED (mock). No real hardware.
"""
from collections import deque
from datetime import datetime

# ── Thresholds for Thanjavur paddy ──────────────────────────────────────────
PH_OPTIMAL    = (5.5, 7.0)
EC_HIGH       = 2.0          # dS/m; above this → salinity stress
N_LOW, N_HIGH = 30, 60      # mg/kg
P_LOW         = 12           # mg/kg
K_LOW         = 25           # mg/kg
SURFACE_MOIST_LOW  = 22.0   # % — below this → irrigate risk
ROOT_MOIST_LOW     = 16.0   # % — below this → irrigation urgent
TANK_LEVEL_CRITICAL = 20.0  # % — below this → block irrigation
LIGHT_LOW     = 400          # lux — poor image quality below this

DISEASE_CLASSES = ["Bacterial Blight", "Blast", "Brown Spot", "Tungro", "Healthy"]
HIGH_RISK_DISEASES = {
    "Bacterial Blight": {"humidity_thresh": 80, "temp_range": (25, 35)},
    "Blast":            {"humidity_thresh": 85, "temp_range": (24, 32)},
    # Brown spot tracks nutrient and water stress, not humidity — and this node
    # measures both, so it corroborates on soil rather than air.
    "Brown Spot":       {"corroborator": "soil_stress"},
    # Tungro is insect-vectored. No sensor on this node observes leafhopper
    # pressure, so there is no corroborator and HIGH is unreachable BY DESIGN.
    "Tungro":           {"corroborator": None, "max_risk": "MEDIUM"},
}

# ── History buffers for trend / rate-of-change ────────────────────────────
_HISTORY_LEN = 10
_history: dict[str, deque] = {
    "surface_moisture": deque(maxlen=_HISTORY_LEN),
    "root_moisture":    deque(maxlen=_HISTORY_LEN),
    "soil_n":           deque(maxlen=_HISTORY_LEN),
}

def _rate_of_change(buf: deque) -> float | None:
    """Moving average slope (units/reading). Needs ≥3 points."""
    if len(buf) < 3:
        return None
    diffs = [buf[i] - buf[i-1] for i in range(1, len(buf))]
    return sum(diffs) / len(diffs)

def _trend_warning(key: str, value: float, label: str, threshold: float) -> str | None:
    roc = _rate_of_change(_history[key])
    if roc is None or roc >= 0:
        return None
    if value <= threshold:        # already breached; not a forecast
        return None
    steps = max(0, int((value - threshold) / -roc))
    return f"EARLY WARNING ({label} trending down, ~{steps} readings to threshold)"

def _sensor_ok(status: dict, key: str) -> bool:
    return status.get(key, "UNKNOWN") in ("VALID", "STALE")

# ── Nutrient rules ──────────────────────────────────────────────────────────
def _reading(sensor, key, status_key=None):
    """A reading, or None. Never a substituted value.

    Section 4: 'Never replace a missing/failed sensor value with zero or a
    guess.' A missing value is a fault to be reported, not a number to reason
    with — 0 mg/kg nitrogen reads as a severe deficiency and generates a
    fertiliser prescription from an absent wire.
    """
    if sensor.get(key) is None:
        return None
    st = sensor.get("sensor_status", {}).get(status_key or key, "UNKNOWN")
    return sensor[key] if st in ("VALID", "STALE") else None

def evaluate_nutrients(sensor: dict) -> list:
    """Nutrient logic: pH, EC, N, P, K + Zinc proxy."""
    alerts = []
    
    # Extract readings securely without defaults
    ph = _reading(sensor, "soil_ph")
    ec = _reading(sensor, "soil_ec", "soil_ec")
    n = _reading(sensor, "soil_n", "soil_npk")
    p = _reading(sensor, "soil_p", "soil_npk")
    k = _reading(sensor, "soil_k", "soil_npk")

    # pH
    if ph is None:
        alerts.append({"nutrient": "pH", "level": "UNKNOWN", "message": "Soil pH unavailable — MANUAL CHECK RECOMMENDED.", "confidence": "NONE"})
    elif ph < PH_OPTIMAL[0]:
        alerts.append({"nutrient": "pH", "level": "LOW",
                       "message": f"Soil pH {ph} is below optimal (5.5–7.0) — apply lime.",
                       "confidence": "HIGH"})
    elif ph > PH_OPTIMAL[1]:
        alerts.append({"nutrient": "pH", "level": "HIGH",
                       "message": f"Soil pH {ph} is above optimal — apply sulfur or organic matter.",
                       "confidence": "HIGH"})

    # EC
    if ec is None:
        alerts.append({"nutrient": "EC", "level": "UNKNOWN", "message": "Soil EC unavailable — MANUAL CHECK RECOMMENDED.", "confidence": "NONE"})
    elif ec > 2.0:
        alerts.append({"nutrient": "EC", "level": "HIGH", "message": f"EC {ec:.1f} dS/m indicates salt stress. Check drainage.", "confidence": "HIGH"})
    
    # Nitrogen
    if n is None:
        alerts.append({"nutrient": "N", "level": "UNKNOWN", "message": "Soil N unavailable — MANUAL CHECK RECOMMENDED. No fertiliser recommendation is made without a reading.", "confidence": "NONE"})
    elif n < N_LOW:
        alerts.append({"nutrient": "N", "level": "LOW", "message": f"N is {n} mg/kg. Apply urea top-dressing.", "confidence": "HIGH"})
    elif n > N_HIGH:
        alerts.append({"nutrient": "N", "level": "HIGH", "message": f"N is {n} mg/kg. High risk of leaf folder/Blight. Hold urea.", "confidence": "HIGH"})
        
    # Phosphorus
    if p is None:
        alerts.append({"nutrient": "P", "level": "UNKNOWN", "message": "Soil P unavailable — MANUAL CHECK RECOMMENDED. No fertiliser recommendation is made without a reading.", "confidence": "NONE"})
    elif p < 12:
        alerts.append({"nutrient": "P", "level": "LOW", "message": f"P is {p} mg/kg. Basal application likely insufficient.", "confidence": "HIGH"})
        
    # Potassium
    if k is None:
        alerts.append({"nutrient": "K", "level": "UNKNOWN", "message": "Soil K unavailable — MANUAL CHECK RECOMMENDED. No fertiliser recommendation is made without a reading.", "confidence": "NONE"})
    elif k < 25:
        alerts.append({"nutrient": "K", "level": "LOW", "message": f"K is {k} mg/kg. Essential for disease resistance. Apply MOP.", "confidence": "HIGH"})

    # Zinc — NEVER claim 'sensor detected zinc'; use agronomic prior
    zinc_risk = (n is not None and n > N_HIGH) or (ph is not None and ph > 7.2)
    if zinc_risk:
        alerts.append({"nutrient": "Zn", "level": "RISK",
                       "message": ("Possible zinc deficiency — high N or alkaline pH can lock out Zn in paddy. "
                                   "Soil test recommended. If confirmed, apply ZnSO₄ 25 kg/ha basal."),
                       "confidence": "LOW"})

    return alerts

# ── Irrigation rules ────────────────────────────────────────────────────────
def evaluate_irrigation(sensor: dict) -> dict:
    result = {"action": "NO_ACTION", "reason": [], "confidence": "HIGH", "blocked": False, "flow_alert": None}

    # Rain gate
    if sensor.get("rain", False):
        result["action"] = "HOLD"
        result["reason"].append("Active rainfall detected — irrigation not needed.")
        return result

    # Tank level safety check
    tank = _reading(sensor, "tank_level")
    if tank is None:
        result["action"] = "HOLD"
        result["confidence"] = "NONE"
        result["reason"].append("Tank level sensor FAILED — irrigation BLOCKED. MANUAL CHECK RECOMMENDED.")
        result["blocked"] = True
        return result

    if tank < TANK_LEVEL_CRITICAL:
        result["action"] = "HOLD"
        result["blocked"] = True
        result["reason"].append(f"Tank level {tank:.0f}% is critically low (<{TANK_LEVEL_CRITICAL}%) — irrigation BLOCKED.")
        return result

    # Moisture-based decision
    surf = _reading(sensor, "surface_moisture")
    root = _reading(sensor, "root_moisture")

    if surf is None or root is None:
        result["confidence"] = "LOW"
        result["reason"].append("Moisture sensor degraded — decision confidence reduced. MANUAL CHECK RECOMMENDED.")

    irrigate = False
    if surf is not None and surf < SURFACE_MOIST_LOW:
        irrigate = True
        result["reason"].append(f"Surface moisture {surf}% below threshold ({SURFACE_MOIST_LOW}%).")
        t = _trend_warning("surface_moisture", surf, "surface moisture", SURFACE_MOIST_LOW)
        if t: result["reason"].append(t)
    if root is not None and root < ROOT_MOIST_LOW:
        irrigate = True
        result["reason"].append(f"Root-zone moisture {root}% below threshold ({ROOT_MOIST_LOW}%).")
        t = _trend_warning("root_moisture", root, "root moisture", ROOT_MOIST_LOW)
        if t: result["reason"].append(t)

    result["action"] = "IRRIGATE" if irrigate else "NO_ACTION"

    # Flow verification check
    flow = _reading(sensor, "flow_lpm")
    if result["action"] == "IRRIGATE" and (flow is None or flow < 0.5):
        result["flow_alert"] = "Valve commanded but flow_lpm<0.5 or missing — possible blockage. VERIFY MANUALLY."

    return result

# ── Disease fusion ──────────────────────────────────────────────────────────
def fuse_disease(predicted_class: str, confidence_score: float, sensor: dict) -> dict:
    """
    Fuse visual model output with environmental corroboration.
    Visual confidence alone cannot trigger HIGH without corroboration.
    """
    result = {
        "predicted": predicted_class,
        "visual_confidence": confidence_score,
        "final_risk": "LOW",
        "factors": [],
        "image_quality": "GOOD"
    }

    # Image-quality gate (light)
    lux = sensor.get("light_lux", 1000)
    if lux < LIGHT_LOW:
        result["image_quality"] = "POOR"
        result["factors"].append(f"Low light ({lux} lux) — image quality degraded. Visual confidence reduced.")
        confidence_score *= 0.7  # penalise visual confidence

    if predicted_class == "Healthy":
        result["final_risk"] = "NONE"
        result["factors"].append("Model predicts healthy crop.")
        return result

    # Environmental corroboration
    env_corroborated = False
    env_conditions = HIGH_RISK_DISEASES.get(predicted_class, {})
    corroborator = env_conditions.get("corroborator", "climate")

    if corroborator == "climate":
        hum = sensor.get("humidity", 0)
        temp = sensor.get("air_temperature", 0)
        hum_thresh = env_conditions.get("humidity_thresh", 999)
        t_range = env_conditions.get("temp_range", (0, 100))
        if hum >= hum_thresh and t_range[0] <= temp <= t_range[1]:
            env_corroborated = True
            result["factors"].append(f"Environmental corroboration: humidity {hum}% ≥ {hum_thresh}% and temp {temp}°C in {t_range} risk range.")
    elif corroborator == "soil_stress":
        n = _reading(sensor, "soil_n", "soil_npk")
        root = _reading(sensor, "root_moisture")
        if (n is not None and n < N_LOW) or (root is not None and root < ROOT_MOIST_LOW):
            env_corroborated = True
            result["factors"].append("Soil corroboration: low nitrogen or low root moisture detected.")
    
    max_risk = env_conditions.get("max_risk", "HIGH")
    if max_risk == "MEDIUM":
        result["factors"].append(f"{predicted_class} risk capped at MEDIUM — no environmental corroborator available on this node.")

    # Final risk level
    if confidence_score >= 0.75 and env_corroborated:
        result["final_risk"] = "HIGH"
    elif confidence_score >= 0.55 or env_corroborated:
        result["final_risk"] = "MEDIUM"
    else:
        result["final_risk"] = "LOW"
        result["factors"].append("Visual confidence below threshold and no environmental corroboration — monitoring recommended.")

    # Apply hard cap
    if result["final_risk"] == "HIGH" and max_risk != "HIGH":
        result["final_risk"] = max_risk

    result["adjusted_visual_confidence"] = confidence_score
    return result

# ── Main history update ─────────────────────────────────────────────────────
def update_history(sensor: dict):
    for key in _history:
        if key in sensor:
            _history[key].append(sensor[key])

# ── Full pipeline ────────────────────────────────────────────────────────────
def run_rule_engine(sensor: dict, predicted_class: str = "Healthy",
                    visual_confidence: float = 0.95) -> dict:
    update_history(sensor)
    return {
        "timestamp": sensor["timestamp"],
        "nutrients": evaluate_nutrients(sensor),
        "irrigation": evaluate_irrigation(sensor),
        "disease_fusion": fuse_disease(predicted_class, visual_confidence, sensor),
    }

if __name__ == "__main__":
    import json
    from sensor_contract import SensorDataGenerator
    
    # Demonstrate with a stress-test reading
    s = SensorDataGenerator.generate_mock_reading()
    s["surface_moisture"] = 18.0  # force below threshold
    s["soil_n"] = 25              # force low N
    s["humidity"] = 88.0          # force high humidity → Blast corroboration
    s["air_temperature"] = 27.0
    s["light_lux"] = 350          # poor light
    
    result = run_rule_engine(s, predicted_class="Blast", visual_confidence=0.81)
    print(json.dumps(result, indent=2))
