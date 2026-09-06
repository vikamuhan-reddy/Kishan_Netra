"""Sensor-vision fusion: resolving an ambiguous visual differential using field history.

The premise
-----------
Cotton leaf chlorosis and reddening look broadly similar whether the cause is water
stress, nitrogen deficiency, or a viral infection. This is not a weakness of the
vision model that a bigger model would fix - a single RGB frame does not contain the
information needed to separate them. A three-day soil-moisture trend does.

So the vision model emits a ranked differential, and this module adjusts it with
agronomic likelihoods derived from the sensor window. Each adjustment records the
signal that caused it, so every recommendation can be explained back to a measurement.

Everything here runs on CPU in well under a millisecond. The expensive part of the
pipeline is the vision model; this is deliberately cheap and deliberately transparent,
because a farmer-facing recommendation that cannot be explained should not be shown.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Diagnosis, Evidence, Hypothesis, SensorWindow, VisionDifferential


@dataclass(frozen=True)
class FusionConfig:
    """Agronomic thresholds, tunable per crop and region.

    Defaults are for cotton on medium-textured soil. These are starting points from
    general agronomy, not calibrated field constants - they must be validated against
    local conditions before any field claim is made.
    """

    moisture_stress_pct: float = 20.0
    moisture_adequate_pct: float = 28.0
    moisture_waterlogged_pct: float = 45.0

    #: %/day. More negative than this counts as actively drying.
    drying_trend_pct_per_day: float = -3.0

    heat_stress_c: float = 38.0
    blight_humidity_pct: float = 80.0
    whitefly_favourable_temp_c: float = 30.0

    #: Below this post-fusion margin we decline to commit to a single diagnosis.
    min_decision_margin: float = 0.15

    #: Above this fraction of incomplete readings we distrust the sensor layer.
    max_dropout_ratio: float = 0.30

    #: How far a degraded sensor window is allowed to move the vision prior.
    #: 0.0 means "ignore sensors entirely", 1.0 means "full influence".
    degraded_influence: float = 0.25


class FusionEngine:
    """Combines a vision differential with a sensor window into an explained diagnosis."""

    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()

    def diagnose(
        self, vision: VisionDifferential, window: SensorWindow
    ) -> Diagnosis:
        cfg = self.config
        vision_hypothesis, vision_confidence = vision.top

        notes: list[str] = []

        stuck = window.frozen_channels
        degraded = window.dropout_ratio > cfg.max_dropout_ratio or bool(stuck)

        if window.dropout_ratio > cfg.max_dropout_ratio:
            notes.append(
                f"sensor window {window.dropout_ratio:.0%} incomplete - "
                f"sensor influence reduced to {cfg.degraded_influence:.0%}"
            )
        if stuck:
            # Named explicitly so a farmer or technician knows which probe to
            # go and replace. "Low confidence" is not actionable; "the soil
            # probe is dead" is.
            notes.append(
                "stuck sensor detected (" + ", ".join(sorted(stuck)) + ") - "
                "readings unchanging, channel excluded and probe needs service"
            )

        evidence: list[Evidence] = []
        multipliers: dict[Hypothesis, float] = {}
        for hypothesis in vision.scores:
            factor, reasons = self._sensor_likelihood(hypothesis, window)
            multipliers[hypothesis] = factor
            evidence.extend(reasons)

        # Under degradation, pull every multiplier toward 1.0 so that a failing
        # sensor cannot manufacture a confident diagnosis on its own.
        if degraded:
            influence = cfg.degraded_influence
            multipliers = {
                h: 1.0 + (m - 1.0) * influence for h, m in multipliers.items()
            }

        posterior = {h: vision.scores[h] * multipliers[h] for h in vision.scores}
        total = sum(posterior.values())
        if total <= 0:
            # Sensors contradicted everything. Fall back to vision rather than
            # dividing by zero or inventing a result.
            posterior = dict(vision.scores)
            total = 1.0
            notes.append("sensor evidence contradicted all hypotheses; using vision only")
        posterior = {h: p / total for h, p in posterior.items()}

        ranked = sorted(posterior.items(), key=lambda kv: kv[1], reverse=True)
        top_hypothesis, top_confidence = ranked[0]
        margin = top_confidence - ranked[1][1] if len(ranked) > 1 else top_confidence

        needs_review = margin < cfg.min_decision_margin
        if needs_review:
            notes.append(
                f"top-two margin {margin:.2f} below {cfg.min_decision_margin:.2f} - "
                "not committing to a single cause"
            )

        # Only surface evidence for hypotheses that ended up mattering, ranked by
        # how much they moved the answer. A farmer does not need five paragraphs.
        relevant = {top_hypothesis, vision_hypothesis}
        shown = sorted(
            (e for e in evidence if e.hypothesis in relevant),
            key=lambda e: abs(e.weight),
            reverse=True,
        )

        return Diagnosis(
            hypothesis=top_hypothesis,
            confidence=top_confidence,
            vision_only_hypothesis=vision_hypothesis,
            vision_only_confidence=vision_confidence,
            evidence=shown,
            degraded=degraded,
            needs_human_review=needs_review,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Per-hypothesis agronomic likelihoods
    # ------------------------------------------------------------------

    def _sensor_likelihood(
        self, hypothesis: Hypothesis, window: SensorWindow
    ) -> tuple[float, list[Evidence]]:
        handler = {
            Hypothesis.WATER_STRESS: self._water_stress,
            Hypothesis.NITROGEN_DEFICIENCY: self._nitrogen_deficiency,
            Hypothesis.LEAF_CURL_VIRUS: self._leaf_curl_virus,
            Hypothesis.BACTERIAL_BLIGHT: self._bacterial_blight,
            Hypothesis.HEALTHY: self._healthy,
        }[hypothesis]
        return handler(window)

    def _water_stress(self, w: SensorWindow) -> tuple[float, list[Evidence]]:
        """Water stress is the one hypothesis the sensors can nearly confirm outright."""
        cfg = self.config
        factor = 1.0
        reasons: list[Evidence] = []
        h = Hypothesis.WATER_STRESS

        moisture = w.current_moisture
        if moisture is not None:
            if moisture < cfg.moisture_stress_pct:
                factor *= 2.5
                reasons.append(Evidence(
                    "soil moisture", f"{moisture:.0f}% (below {cfg.moisture_stress_pct:.0f}% stress threshold)",
                    h, "supports", 2.5,
                ))
            elif moisture > cfg.moisture_adequate_pct:
                factor *= 0.3
                reasons.append(Evidence(
                    "soil moisture", f"{moisture:.0f}% (adequate)",
                    h, "contradicts", 0.3,
                ))

        trend = w.moisture_trend_pct_per_day
        if trend is not None and trend < cfg.drying_trend_pct_per_day:
            factor *= 1.8
            reasons.append(Evidence(
                "moisture trend", f"falling {abs(trend):.1f}%/day",
                h, "supports", 1.8,
            ))

        temp = w.peak_temp_c
        if temp is not None and temp > cfg.heat_stress_c:
            factor *= 1.4
            reasons.append(Evidence(
                "peak temperature", f"{temp:.0f}C (above {cfg.heat_stress_c:.0f}C heat-stress threshold)",
                h, "supports", 1.4,
            ))

        if w.hours_since_irrigation is not None and w.hours_since_irrigation > 96:
            factor *= 1.5
            reasons.append(Evidence(
                "irrigation history", f"{w.hours_since_irrigation:.0f}h since last irrigation",
                h, "supports", 1.5,
            ))

        return factor, reasons

    def _nitrogen_deficiency(self, w: SensorWindow) -> tuple[float, list[Evidence]]:
        """Nitrogen deficiency is diagnosed largely by *excluding* water stress.

        We cannot measure soil nitrogen with these sensors, and we do not pretend to.
        What we can say is that chlorosis under adequate, stable moisture is not
        explained by water - which is precisely the distinction that changes whether
        the farmer buys fertilizer or turns on a pump.
        """
        cfg = self.config
        factor = 1.0
        reasons: list[Evidence] = []
        h = Hypothesis.NITROGEN_DEFICIENCY

        moisture = w.current_moisture
        if moisture is not None:
            if moisture > cfg.moisture_adequate_pct:
                factor *= 2.0
                reasons.append(Evidence(
                    "soil moisture", f"{moisture:.0f}% adequate, so symptoms are not water-driven",
                    h, "supports", 2.0,
                ))
            elif moisture < cfg.moisture_stress_pct:
                factor *= 0.5
                reasons.append(Evidence(
                    "soil moisture", f"{moisture:.0f}% - water stress is the simpler explanation",
                    h, "contradicts", 0.5,
                ))

        trend = w.moisture_trend_pct_per_day
        if trend is not None and abs(trend) < 1.5:
            factor *= 1.4
            reasons.append(Evidence(
                "moisture trend", f"stable ({trend:+.1f}%/day), consistent with a slow nutrient issue",
                h, "supports", 1.4,
            ))

        return factor, reasons

    def _leaf_curl_virus(self, w: SensorWindow) -> tuple[float, list[Evidence]]:
        """Cotton leaf curl is whitefly-vectored; conditions favour the vector, not the virus."""
        cfg = self.config
        factor = 1.0
        reasons: list[Evidence] = []
        h = Hypothesis.LEAF_CURL_VIRUS

        temp = w.peak_temp_c
        humidity = w.mean_humidity_pct
        if temp is not None and humidity is not None:
            if temp > cfg.whitefly_favourable_temp_c and humidity < cfg.blight_humidity_pct:
                factor *= 1.6
                reasons.append(Evidence(
                    "vector conditions", f"{temp:.0f}C with {humidity:.0f}% humidity favours whitefly activity",
                    h, "supports", 1.6,
                ))

        moisture = w.current_moisture
        if moisture is not None and moisture > cfg.moisture_adequate_pct:
            factor *= 1.2
            reasons.append(Evidence(
                "soil moisture", f"{moisture:.0f}% adequate, so symptoms are not water-driven",
                h, "supports", 1.2,
            ))

        return factor, reasons

    def _bacterial_blight(self, w: SensorWindow) -> tuple[float, list[Evidence]]:
        """Bacterial blight needs sustained leaf wetness; humidity is the proxy."""
        cfg = self.config
        factor = 1.0
        reasons: list[Evidence] = []
        h = Hypothesis.BACTERIAL_BLIGHT

        humidity = w.mean_humidity_pct
        if humidity is not None:
            if humidity > cfg.blight_humidity_pct:
                factor *= 2.0
                reasons.append(Evidence(
                    "humidity", f"{humidity:.0f}% sustained, favourable for bacterial spread",
                    h, "supports", 2.0,
                ))
            elif humidity < 50:
                factor *= 0.5
                reasons.append(Evidence(
                    "humidity", f"{humidity:.0f}% - too dry for bacterial spread",
                    h, "contradicts", 0.5,
                ))

        moisture = w.current_moisture
        if moisture is not None and moisture > cfg.moisture_waterlogged_pct:
            factor *= 1.5
            reasons.append(Evidence(
                "soil moisture", f"{moisture:.0f}% waterlogged, prolongs leaf wetness",
                h, "supports", 1.5,
            ))

        return factor, reasons

    def _healthy(self, w: SensorWindow) -> tuple[float, list[Evidence]]:
        """Benign conditions raise the prior that the camera saw noise, not disease."""
        cfg = self.config
        factor = 1.0
        reasons: list[Evidence] = []
        h = Hypothesis.HEALTHY

        moisture = w.current_moisture
        temp = w.peak_temp_c
        benign_moisture = (
            moisture is not None
            and cfg.moisture_adequate_pct <= moisture <= cfg.moisture_waterlogged_pct
        )
        benign_temp = temp is not None and temp < cfg.heat_stress_c
        if benign_moisture and benign_temp:
            factor *= 1.3
            reasons.append(Evidence(
                "field conditions", f"moisture {moisture:.0f}% and peak {temp:.0f}C both in normal range",
                h, "supports", 1.3,
            ))

        return factor, reasons
