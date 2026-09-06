"""
Test cases for the pest fusion rule.

Every branch of the decision documented in pest_fusion_rule.py has a test
here, including the ones that exist to PREVENT something: the MEDIUM cap on
Dead Heart, the abstain band, and the disease/pest disagreement case.

Run: python test_pest_fusion.py     (exit code 0 = all pass)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from pest_fusion_rule import (  # noqa: E402
    ALERT_CONFIDENCE_THRESHOLD, combine_verdicts, fuse_pest, load_pest_classes)
from step6_rule_engine import fuse_disease  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


# Simulated sensor baselines. All values are SIMULATED, never measured.
# Shape follows sensor_contract.SensorDataGenerator: flat soil_n, with the
# NPK probe's health reported under sensor_status["soil_npk"].
_STATUS = {"soil_ph": "VALID", "soil_ec": "VALID", "soil_npk": "VALID",
           "surface_moisture": "VALID", "root_moisture": "VALID",
           "tank_level": "VALID"}
GOOD_LIGHT = {"light_lux": 1200, "humidity": 60, "air_temperature": 28,
              "soil_n": 45, "soil_p": 20, "soil_k": 40, "root_moisture": 25,
              "sensor_status": dict(_STATUS)}
EXCESS_N = dict(GOOD_LIGHT, soil_n=75)          # above N_HIGH (60)
LOW_LIGHT = dict(GOOD_LIGHT, light_lux=200)     # below LIGHT_LOW (400)
# Excess nitrogen present in the payload, but the NPK probe reports FAULT.
EXCESS_N_PROBE_FAULT = dict(EXCESS_N,
                            sensor_status=dict(_STATUS, soil_npk="FAULT"))
# Nitrogen key absent entirely (sensor_contract drop=['soil_n']).
EXCESS_N_MISSING = {k: v for k, v in EXCESS_N.items() if k != "soil_n"}


def main():
    classes = load_pest_classes()
    check("pest_classes.json loads and holds the expected 3 classes",
          len(classes) == 3, str(classes))

    # --- Rule 2: corroboration governs HIGH -------------------------------
    r = fuse_pest("Hispa", 0.95, EXCESS_N)
    check("Hispa + excess nitrogen reaches HIGH",
          r["final_risk"] == "HIGH", r["final_risk"])

    r = fuse_pest("Hispa", 0.95, GOOD_LIGHT)
    check("Hispa without corroboration is capped at MEDIUM",
          r["final_risk"] == "MEDIUM", r["final_risk"])

    # Honesty rule: a failed or absent sensor must never be reasoned with as
    # if it were a reading. Both cases must fall back to MEDIUM, not escalate.
    r = fuse_pest("Hispa", 0.95, EXCESS_N_PROBE_FAULT)
    check("Faulted NPK probe cannot corroborate, even with N in the payload",
          r["final_risk"] == "MEDIUM", r["final_risk"])
    r = fuse_pest("Hispa", 0.95, EXCESS_N_MISSING)
    check("Absent nitrogen reading cannot corroborate",
          r["final_risk"] == "MEDIUM", r["final_risk"])

    # The cap that exists to prevent an unsupported claim.
    r = fuse_pest("Dead Heart", 0.99, EXCESS_N)
    check("Dead Heart can NEVER reach HIGH (no stem-borer sensor on this node)",
          r["final_risk"] == "MEDIUM", r["final_risk"])
    check("Dead Heart verdict states why it is capped",
          any("capped at MEDIUM" in f for f in r["factors"]))

    # --- Rule 3: the abstain band ------------------------------------------
    r = fuse_pest("Hispa", ALERT_CONFIDENCE_THRESHOLD - 0.01, GOOD_LIGHT)
    check("Confidence just below threshold yields INCONCLUSIVE, not a guess",
          r["final_risk"] == "INCONCLUSIVE" and r["alert"] is False, r["final_risk"])

    r = fuse_pest("Hispa", ALERT_CONFIDENCE_THRESHOLD, GOOD_LIGHT)
    check("Confidence exactly at threshold does alert",
          r["alert"] is True, r["final_risk"])

    r = fuse_pest("No Pest Damage", 0.97, GOOD_LIGHT)
    check("Negative class yields NONE and never alerts",
          r["final_risk"] == "NONE" and r["alert"] is False, r["final_risk"])

    # Low light penalises confidence by 0.7, which can drop a call into abstain.
    r = fuse_pest("Hispa", 0.95, LOW_LIGHT)
    check("Low light degrades image quality and pushes 0.95 into the abstain band",
          r["image_quality"] == "POOR" and r["final_risk"] == "INCONCLUSIVE",
          f"{r['image_quality']}/{r['final_risk']} conf={r['adjusted_visual_confidence']:.3f}")

    # --- Rule 1 + 4: combination and disagreement --------------------------
    healthy_disease = fuse_disease("Healthy", 0.96, GOOD_LIGHT)
    hispa_pest = fuse_pest("Hispa", 0.95, EXCESS_N)
    c = combine_verdicts(healthy_disease, hispa_pest)
    check("Disease=Healthy + Pest=Hispa fires the pest channel only",
          c["channels_fired"] == ["pest"], str(c["channels_fired"]))
    check("The disease/pest disagreement is explained, not left silent",
          c["conflict_note"] is not None and "no pest class" in c["conflict_note"])
    check("Headline risk follows the pest channel when only pest fires",
          c["headline_risk"] == "HIGH", c["headline_risk"])

    blast = fuse_disease("Blast", 0.92, dict(EXCESS_N, humidity=90, air_temperature=28))
    c = combine_verdicts(blast, hispa_pest)
    check("Both channels firing produces ONE advisory naming both",
          set(c["channels_fired"]) == {"disease", "pest"}
          and "Blast" in c["advisory"] and "Hispa" in c["advisory"],
          c["advisory"])

    clean = combine_verdicts(healthy_disease, fuse_pest("No Pest Damage", 0.97, GOOD_LIGHT))
    check("All-clear fires no channel and claims nothing",
          clean["channels_fired"] == [] and clean["headline_risk"] == "NONE",
          clean["advisory"])

    inconc = combine_verdicts(healthy_disease, fuse_pest("Hispa", 0.5, GOOD_LIGHT))
    check("Inconclusive pest read asks for a re-image rather than alerting",
          inconc["channels_fired"] == [] and "re-imaging" in inconc["advisory"],
          inconc["advisory"])

    # --- Rule 1: nothing is averaged ---------------------------------------
    check("Both raw verdicts survive combination verbatim",
          c["disease"] is blast and c["pest"] is hispa_pest)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
