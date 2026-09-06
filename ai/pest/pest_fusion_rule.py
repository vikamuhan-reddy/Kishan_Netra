"""
Pest fusion rule - the explicit decision about how the pest model's output
reaches the farmer, and how it relates to the disease model's output.

THE DECISION (made deliberately, not by an ad-hoc dashboard edit):

1. Disease and pest remain TWO INDEPENDENT VERDICTS. They are not averaged
   into a combined score. They are separate models answering different
   questions about the same image; a blended number would mean nothing and
   could not be explained to a farmer or a judge.

2. Pest verdicts obey the SAME corroboration principle already established in
   step6_rule_engine.fuse_disease: visual confidence alone can never reach
   HIGH. That is the rule which caps Tungro at MEDIUM because no sensor on
   this node observes leafhopper pressure.

     - Hispa CAN reach HIGH. Its corroborator is excess soil nitrogen, which
       this node measures. This is not a new agronomic claim: step6's own
       nutrient rule already states that N above N_HIGH carries "high risk of
       leaf folder/Blight" and advises holding urea. Hispa pressure under
       excess N is that same relationship, and the node has the sensor for it.

     - Dead Heart is capped at MEDIUM. It is caused by yellow stem borer, and
       nothing on this node observes stem borer pressure - no pheromone trap,
       no insect counter. By the exact precedent set for Tungro, HIGH is
       unreachable for it BY DESIGN rather than by accident.

3. A pest alert requires confidence >= ALERT_CONFIDENCE_THRESHOLD (0.80).
   Chosen from pest_threshold_analysis.py, not by feel: at T=0.80 the
   false-alert rate on healthy leaves drops from 8.37% to 3.04% while pest
   recall only falls from 96.92% to 90.31%. Below that threshold the node
   reports INCONCLUSIVE and re-images. This node is a FIXED sentinel watching
   one zone on a capture cycle, so an inconclusive frame is a deferred look at
   the same plants, not a missed detection.

4. The disagreement case is handled EXPLICITLY, not silently. The disease
   model has no pest class and the pest model has no disease class, so
   "disease says Healthy, pest says Hispa" is not a contradiction - it is the
   expected shape of a real pest-only infestation. The pest channel wins the
   pest question, the disease channel wins the disease question, and when both
   fire the farmer gets ONE advisory naming both, because they make one trip
   to the field.

All sensor values in this project are SIMULATED. This module contains no
measured field performance and asserts none.
"""
import json
import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parent.parent
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from step6_rule_engine import LIGHT_LOW, N_HIGH, _reading  # noqa: E402

PEST_CLASSES_PATH = Path(__file__).resolve().parent / "pest_classes.json"

# Chosen from the threshold sweep. See pest_threshold_analysis.json.
ALERT_CONFIDENCE_THRESHOLD = 0.80
NEGATIVE_CLASS = "No Pest Damage"

PEST_CORROBORATORS = {
    # Excess nitrogen promotes lush foliage and hispa feeding pressure. This
    # node measures soil N, and step6's nutrient rule already asserts the
    # N > N_HIGH -> leaf-pest risk relationship.
    "Hispa": {"corroborator": "excess_nitrogen", "max_risk": "HIGH"},
    # Yellow stem borer. No sensor on this node observes stem borer pressure,
    # so HIGH is unreachable BY DESIGN - same precedent as Tungro.
    "Dead Heart": {"corroborator": None, "max_risk": "MEDIUM"},
}


def load_pest_classes():
    with PEST_CLASSES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def fuse_pest(predicted_class: str, confidence_score: float, sensor: dict) -> dict:
    """Fuse pest-model output with environmental corroboration.

    Mirrors step6_rule_engine.fuse_disease. Returns an independent pest
    verdict; it never touches the disease verdict.
    """
    result = {
        "predicted": predicted_class,
        "visual_confidence": confidence_score,
        "final_risk": "LOW",
        "factors": [],
        "image_quality": "GOOD",
        "alert": False,
    }

    # Image-quality gate (light) - same gate and same penalty as fuse_disease.
    lux = sensor.get("light_lux", 1000)
    if lux < LIGHT_LOW:
        result["image_quality"] = "POOR"
        result["factors"].append(
            f"Low light ({lux} lux) - image quality degraded. Visual confidence reduced.")
        confidence_score *= 0.7

    if predicted_class == NEGATIVE_CLASS:
        result["final_risk"] = "NONE"
        result["factors"].append("Model finds no pest damage.")
        result["adjusted_visual_confidence"] = confidence_score
        return result

    # Abstain band: below the alert threshold the node does not guess.
    if confidence_score < ALERT_CONFIDENCE_THRESHOLD:
        result["final_risk"] = "INCONCLUSIVE"
        result["factors"].append(
            f"Confidence {confidence_score:.2f} below alert threshold "
            f"{ALERT_CONFIDENCE_THRESHOLD:.2f} - re-image on next capture cycle.")
        result["adjusted_visual_confidence"] = confidence_score
        return result

    spec = PEST_CORROBORATORS.get(
        predicted_class, {"corroborator": None, "max_risk": "MEDIUM"})
    corroborated = False
    if spec["corroborator"] == "excess_nitrogen":
        n = _reading(sensor, "soil_n", "soil_npk")
        if n is not None and n > N_HIGH:
            corroborated = True
            result["factors"].append(
                f"Soil corroboration: nitrogen {n} mg/kg above {N_HIGH} mg/kg - "
                "lush foliage favours leaf-pest pressure.")

    max_risk = spec["max_risk"]
    if max_risk == "MEDIUM":
        result["factors"].append(
            f"{predicted_class} risk capped at MEDIUM - no environmental "
            "corroborator for this pest exists on this node.")

    if corroborated:
        result["final_risk"] = "HIGH"
    else:
        result["final_risk"] = "MEDIUM"
        if spec["corroborator"] is not None:
            result["factors"].append(
                "Visual detection without environmental corroboration - "
                "scouting recommended before treatment.")

    if result["final_risk"] == "HIGH" and max_risk != "HIGH":
        result["final_risk"] = max_risk

    result["alert"] = result["final_risk"] in ("MEDIUM", "HIGH")
    result["adjusted_visual_confidence"] = confidence_score
    return result


_ORDER = {"NONE": 0, "LOW": 1, "INCONCLUSIVE": 1, "MEDIUM": 2, "HIGH": 3}
_RANK_TO_NAME = {0: "NONE", 1: "LOW", 2: "MEDIUM", 3: "HIGH"}


def combine_verdicts(disease_result: dict, pest_result: dict) -> dict:
    """Produce ONE farmer-facing advisory from two independent verdicts.

    Both verdicts are preserved verbatim in the output. Nothing is averaged.
    This function only decides what the node SAYS, and in what order.
    """
    d_risk = disease_result.get("final_risk", "LOW")
    p_risk = pest_result.get("final_risk", "LOW")

    disease_fires = _ORDER.get(d_risk, 0) >= 2
    pest_fires = bool(pest_result.get("alert", False))

    combined = {
        "disease": disease_result,
        "pest": pest_result,
        "channels_fired": [],
        "headline_risk": "NONE",
        "advisory": "",
        "conflict_note": None,
    }

    if disease_fires:
        combined["channels_fired"].append("disease")
    if pest_fires:
        combined["channels_fired"].append("pest")

    top = max(_ORDER.get(d_risk, 0) if disease_fires else 0,
              _ORDER.get(p_risk, 0) if pest_fires else 0)
    combined["headline_risk"] = _RANK_TO_NAME[top]

    d_name = disease_result.get("predicted", "Healthy")
    p_name = pest_result.get("predicted", NEGATIVE_CLASS)

    if disease_fires and pest_fires:
        # One trip to the field, one message naming both.
        combined["advisory"] = (
            f"Both channels fired. Disease: {d_name} ({d_risk}). "
            f"Pest: {p_name} ({p_risk}). Inspect this zone for both.")
    elif disease_fires:
        combined["advisory"] = f"Disease: {d_name} ({d_risk}). No pest alert."
    elif pest_fires:
        combined["advisory"] = f"Pest: {p_name} ({p_risk}). No disease alert."
        if d_name == "Healthy":
            # Not a contradiction: the disease model has no pest class and was
            # never trained to recognise feeding damage.
            combined["conflict_note"] = (
                "Disease model reports Healthy while the pest model reports "
                f"{p_name}. This is expected for a pest-only infestation - the "
                "disease model has no pest class and cannot represent this "
                "damage. The pest channel is authoritative on pest questions.")
    elif p_risk == "INCONCLUSIVE":
        combined["advisory"] = (
            "No disease alert. Pest read inconclusive - re-imaging this zone "
            "on the next capture cycle.")
    else:
        combined["advisory"] = "No disease alert. No pest alert."

    return combined
