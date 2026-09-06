"""The headline demonstration: one leaf image, two field histories, two recommendations.

Run:  python -m demo.differential_demo

This is the thirty seconds of the pitch that a plain crop-disease classifier cannot
reproduce. The vision differential is held *identical* across both runs - the only
thing that changes is the sensor history - and the recommended intervention flips
from "irrigate" to "apply nitrogen". Those two actions cost different money and have
opposite effects if applied to the wrong cause.
"""

from __future__ import annotations

import sys

from iot.contracts import Hypothesis, VisionDifferential
from iot.fusion.engine import FusionEngine
from iot.simulator.field import SCENARIOS, generate_window

# What the vision model actually produces for an ambiguous chlorotic cotton leaf.
# Note the top two are 4 points apart: the camera genuinely cannot separate them.
AMBIGUOUS_LEAF = VisionDifferential({
    Hypothesis.NITROGEN_DEFICIENCY: 0.41,
    Hypothesis.WATER_STRESS: 0.37,
    Hypothesis.LEAF_CURL_VIRUS: 0.13,
    Hypothesis.BACTERIAL_BLIGHT: 0.06,
    Hypothesis.HEALTHY: 0.03,
})

RULE = "-" * 72


def show(scenario_key: str, engine: FusionEngine) -> None:
    scenario = SCENARIOS[scenario_key]
    window = generate_window(scenario_key)
    diagnosis = engine.diagnose(AMBIGUOUS_LEAF, window)

    print(RULE)
    print(f"FIELD HISTORY: {scenario.name}")
    print(f"  {scenario.description}")
    print()
    moisture = window.current_moisture
    trend = window.moisture_trend_pct_per_day
    temp = window.peak_temp_c
    humidity = window.mean_humidity_pct
    print("  sensors over the last 72 hours")
    print(f"    soil moisture now : {moisture:.0f}%" if moisture is not None else "    soil moisture now : unavailable")
    print(f"    moisture trend    : {trend:+.1f} %/day" if trend is not None else "    moisture trend    : unavailable")
    print(f"    peak temperature  : {temp:.0f} C" if temp is not None else "    peak temperature  : unavailable")
    print(f"    mean humidity     : {humidity:.0f}%" if humidity is not None else "    mean humidity     : unavailable")
    if window.dropout_ratio:
        print(f"    reading dropout   : {window.dropout_ratio:.0%}")
    print()

    print("  camera alone")
    print(f"    {diagnosis.vision_only_hypothesis.value} ({diagnosis.vision_only_confidence:.0%}) "
          f"- margin over next hypothesis {AMBIGUOUS_LEAF.margin:.0%}")
    print()

    print("  after fusion with field history")
    print(f"    {diagnosis.hypothesis.value} ({diagnosis.confidence:.0%})")
    print(f"    ACTION: {diagnosis.recommended_action}")
    if diagnosis.changed_by_sensors:
        print("    >>> sensors overturned the camera's conclusion")
    print()

    print("  why")
    for item in diagnosis.evidence[:4]:
        arrow = "+" if item.direction == "supports" else "-"
        print(f"    [{arrow}] {item.signal}: {item.observation}")
        print(f"        {item.direction} {item.hypothesis.value}")
    for note in diagnosis.notes:
        print(f"    [!] {note}")
    print()


def main() -> int:
    engine = FusionEngine()

    print()
    print("=" * 72)
    print("SAME LEAF IMAGE. DIFFERENT FIELD. DIFFERENT ANSWER.")
    print("=" * 72)
    print()
    print("The vision model output below is byte-identical in both cases:")
    for hypothesis, score in AMBIGUOUS_LEAF.ranked:
        print(f"    {hypothesis.value:<22} {score:.0%}")
    print()
    print("A classifier stops here and reports the top label. It would give the same")
    print("advice to both farmers below. One of them would waste money on fertilizer")
    print("while the crop died of thirst.")
    print()

    show("drying_down", engine)
    show("well_watered", engine)

    print(RULE)
    print("DEGRADED MODE: what happens when the probe starts failing")
    print(RULE)
    show("failing_sensor", engine)

    print(RULE)
    print("THE DANGEROUS ONE: a dead probe that keeps reporting")
    print(RULE)
    print("The soil is drying hard, but the probe died a day ago and still")
    print("reports its last adequate value. Every reading is present and in")
    print("range. The trend is a clean, convincing zero.")
    print()
    print("Taken at face value that reads as 'moisture is fine, so this is not")
    print("water' - and the farmer is told to buy fertilizer for a crop that is")
    print("dying of thirst. Detecting it is worth more than any accuracy point.")
    print()
    show("dying_probe", engine)

    return 0


if __name__ == "__main__":
    sys.exit(main())
