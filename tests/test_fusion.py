"""Tests for the fusion engine.

These lock the specific claims made in the demo and the deck. If a test here fails,
a slide is now wrong.
"""

from __future__ import annotations

import pytest

from iot.contracts import Hypothesis, SensorReading, SensorWindow, VisionDifferential
from iot.fusion.engine import FusionConfig, FusionEngine
from iot.simulator.field import generate_window

AMBIGUOUS = VisionDifferential({
    Hypothesis.NITROGEN_DEFICIENCY: 0.41,
    Hypothesis.WATER_STRESS: 0.37,
    Hypothesis.LEAF_CURL_VIRUS: 0.13,
    Hypothesis.BACTERIAL_BLIGHT: 0.06,
    Hypothesis.HEALTHY: 0.03,
})


@pytest.fixture
def engine() -> FusionEngine:
    return FusionEngine()


class TestHeadlineClaim:
    """The claim the whole pitch rests on."""

    def test_identical_image_yields_different_action_per_field(self, engine):
        dry = engine.diagnose(AMBIGUOUS, generate_window("drying_down"))
        wet = engine.diagnose(AMBIGUOUS, generate_window("well_watered"))

        assert dry.hypothesis is Hypothesis.WATER_STRESS
        assert wet.hypothesis is Hypothesis.NITROGEN_DEFICIENCY
        assert dry.recommended_action != wet.recommended_action

    def test_sensors_overturn_the_camera_when_they_should(self, engine):
        dry = engine.diagnose(AMBIGUOUS, generate_window("drying_down"))
        assert dry.vision_only_hypothesis is Hypothesis.NITROGEN_DEFICIENCY
        assert dry.changed_by_sensors is True

    def test_sensors_leave_the_camera_alone_when_they_agree(self, engine):
        wet = engine.diagnose(AMBIGUOUS, generate_window("well_watered"))
        assert wet.changed_by_sensors is False
        # Agreement should still sharpen a 41% call into something actionable.
        assert wet.confidence > wet.vision_only_confidence

    def test_every_recommendation_carries_traceable_evidence(self, engine):
        for scenario in ("drying_down", "well_watered", "humid_spell"):
            diagnosis = engine.diagnose(AMBIGUOUS, generate_window(scenario))
            assert diagnosis.evidence, f"{scenario} produced an unexplained recommendation"
            for item in diagnosis.evidence:
                assert item.signal and item.observation
                assert item.direction in ("supports", "contradicts")


class TestFailureModes:
    """Hostile-reviewer cases. A field device meets all of these."""

    def test_degraded_sensors_reduce_their_own_influence(self, engine):
        healthy = engine.diagnose(AMBIGUOUS, generate_window("drying_down"))
        faulty = engine.diagnose(AMBIGUOUS, generate_window("failing_sensor"))

        assert faulty.degraded is True
        assert any("incomplete" in note for note in faulty.notes)
        # A half-dead probe must not speak more confidently than a working one.
        assert faulty.confidence < healthy.confidence

    def test_total_sensor_loss_falls_back_to_vision_without_crashing(self, engine):
        blind = SensorWindow(
            readings=[SensorReading(float(h), None, None, None) for h in range(72, -1, -3)]
        )
        diagnosis = engine.diagnose(AMBIGUOUS, blind)

        assert diagnosis.degraded is True
        assert diagnosis.hypothesis is diagnosis.vision_only_hypothesis
        assert diagnosis.needs_human_review is True

    def test_empty_window_does_not_raise(self, engine):
        diagnosis = engine.diagnose(AMBIGUOUS, SensorWindow(readings=[]))
        assert diagnosis.hypothesis in Hypothesis

    def test_low_margin_declines_to_commit(self, engine):
        strict = FusionEngine(FusionConfig(min_decision_margin=0.99))
        diagnosis = strict.diagnose(AMBIGUOUS, generate_window("drying_down"))

        assert diagnosis.needs_human_review is True
        assert "manually" in diagnosis.recommended_action

    def test_too_few_readings_gives_no_trend_rather_than_a_fake_zero(self):
        window = SensorWindow(readings=[SensorReading(0.0, 30.0, 30.0, 50.0)])
        assert window.moisture_trend_pct_per_day is None


class TestStuckSensor:
    """The dangerous failure: a dead probe that keeps reporting.

    A stuck probe presents as perfectly stable moisture, which reads as "not
    water-driven" and resolves toward nitrogen deficiency. Undetected, this
    sends a farmer to buy fertilizer for a crop that may be dying of thirst.
    """

    def test_stuck_channel_is_detected(self):
        window = generate_window("dying_probe")
        assert "soil_moisture_pct" in window.frozen_channels

    def test_stuck_channel_is_excluded_rather_than_trusted(self):
        window = generate_window("dying_probe")
        # The value is in range and present, but it is not a measurement.
        assert window.current_moisture is None
        # A stuck probe fits a perfect zero slope; that must not read "stable".
        assert window.moisture_trend_pct_per_day is None

    def test_stuck_probe_does_not_yield_a_confident_nitrogen_call(self, engine):
        healthy = engine.diagnose(AMBIGUOUS, generate_window("well_watered"))
        broken = engine.diagnose(AMBIGUOUS, generate_window("dying_probe"))

        assert broken.degraded is True
        assert any("stuck sensor" in note for note in broken.notes)
        # Same nominal reading, but the broken probe must not speak as loudly.
        assert broken.confidence < healthy.confidence

    def test_stuck_sensor_note_names_the_channel(self, engine):
        diagnosis = engine.diagnose(AMBIGUOUS, generate_window("dying_probe"))
        note = next(n for n in diagnosis.notes if "stuck sensor" in n)
        # "low confidence" is not actionable; naming the dead probe is.
        assert "soil_moisture_pct" in note

    def test_live_probe_is_not_flagged_as_stuck(self):
        for scenario in ("drying_down", "well_watered", "humid_spell"):
            assert not generate_window(scenario).frozen_channels


class TestImplausibleValues:
    """A floating ADC pin is a fault, not a measurement."""

    @pytest.mark.parametrize(
        "moisture, temp, humidity",
        [
            (247.0, 30.0, 50.0),   # floating pin
            (-15.0, 30.0, 50.0),   # shorted low
            (30.0, 250.0, 50.0),   # open thermistor
            (30.0, 30.0, 180.0),   # impossible humidity
        ],
    )
    def test_out_of_range_counts_as_missing(self, moisture, temp, humidity):
        reading = SensorReading(0.0, moisture, temp, humidity)
        assert reading.is_complete is False

    def test_implausible_values_are_dropped_from_derived_features(self):
        readings = [SensorReading(float(h), 999.0, 30.0, 50.0)
                    for h in range(72, -1, -3)]
        window = SensorWindow(readings=readings)

        assert window.current_moisture is None
        assert window.dropout_ratio == 1.0

    def test_in_range_values_still_work(self):
        assert SensorReading(0.0, 30.0, 30.0, 50.0).is_complete is True


class TestContracts:
    def test_vision_scores_must_be_a_distribution(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            VisionDifferential({Hypothesis.HEALTHY: 0.5, Hypothesis.WATER_STRESS: 0.2})

    def test_simulator_is_deterministic(self):
        a = generate_window("drying_down", seed=7)
        b = generate_window("drying_down", seed=7)
        assert [r.soil_moisture_pct for r in a.readings] == [
            r.soil_moisture_pct for r in b.readings
        ]

    def test_drying_scenario_actually_dries(self):
        window = generate_window("drying_down")
        assert window.moisture_trend_pct_per_day < -3.0
