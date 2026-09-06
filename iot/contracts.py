"""Data contracts shared by the simulator, the physical sensor layer and the fusion engine.

Frozen on day 1 so that tracks T1/T2/T3 can work in parallel. The simulator and the
real sensor driver must both emit `SensorWindow`; the vision model must emit
`VisionDifferential`. Nothing downstream may depend on which one produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class Hypothesis(str, Enum):
    """Candidate explanations for observed cotton leaf symptoms.

    These are deliberately *not* all diseases. Nitrogen deficiency and water stress
    present with overlapping visual symptoms (chlorosis, reddening, wilting) and are
    the ambiguity the sensor layer exists to resolve.
    """

    HEALTHY = "healthy"
    WATER_STRESS = "water_stress"
    NITROGEN_DEFICIENCY = "nitrogen_deficiency"
    LEAF_CURL_VIRUS = "leaf_curl_virus"
    BACTERIAL_BLIGHT = "bacterial_blight"


#: Interventions differ in cost and in the harm done by getting them wrong.
#: Fertilizing a water-stressed plant makes the stress worse *and* wastes the input.
INTERVENTION = {
    Hypothesis.HEALTHY: "no action",
    Hypothesis.WATER_STRESS: "irrigate",
    Hypothesis.NITROGEN_DEFICIENCY: "soil test, then nitrogen application",
    Hypothesis.LEAF_CURL_VIRUS: "whitefly vector control, rogue infected plants",
    Hypothesis.BACTERIAL_BLIGHT: "copper-based spray, avoid overhead irrigation",
}


#: Physically plausible ranges. A reading outside these is not a measurement,
#: it is a fault - a disconnected ADC pin floats, a shorted probe reads rail.
#: Such values are treated as missing rather than trusted.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "soil_moisture_pct": (0.0, 100.0),
    "air_temp_c": (-10.0, 60.0),
    "humidity_pct": (0.0, 100.0),
}

#: How many identical consecutive readings mean the channel is stuck.
#: A live capacitive probe in soil always shows some noise; bit-identical
#: values in a row mean the sensor died while still reporting.
FROZEN_RUN_LENGTH = 6


@dataclass(frozen=True)
class SensorReading:
    """One timestamped sample from the field node."""

    hours_ago: float
    soil_moisture_pct: float | None
    air_temp_c: float | None
    humidity_pct: float | None

    def is_valid(self, channel: str) -> bool:
        """True when this channel carries a physically plausible measurement."""
        value = getattr(self, channel)
        if value is None:
            return False
        low, high = PLAUSIBLE_RANGES[channel]
        return low <= value <= high

    @property
    def is_complete(self) -> bool:
        """All three channels present *and* physically plausible.

        Implausible values count as missing, not as data. Treating a floating
        ADC pin reading 247% moisture as a measurement is worse than having no
        measurement, because the pipeline downstream would act on it.
        """
        return all(self.is_valid(c) for c in PLAUSIBLE_RANGES)


@dataclass(frozen=True)
class SensorWindow:
    """A rolling window of readings plus the derived features fusion actually uses.

    A single snapshot cannot distinguish "dry because it was never watered" from
    "dry because it is mid-afternoon". The trend is what carries the information,
    which is why the window and not the reading is the contract.
    """

    readings: Sequence[SensorReading]
    hours_since_irrigation: float | None = None

    def _series(self, attr: str) -> list[float]:
        """Plausible values for one channel, oldest first. Faults are dropped."""
        return [getattr(r, attr) for r in self.readings if r.is_valid(attr)]

    @property
    def dropout_ratio(self) -> float:
        """Fraction of readings missing or implausible on any channel."""
        if not self.readings:
            return 1.0
        incomplete = sum(1 for r in self.readings if not r.is_complete)
        return incomplete / len(self.readings)

    @property
    def frozen_channels(self) -> frozenset[str]:
        """Channels whose recent readings are bit-identical, i.e. stuck.

        This is the most dangerous sensor failure this system faces, and the
        one that looks most like healthy data. A dead soil probe that keeps
        reporting its last value presents as *perfectly stable moisture* -
        which the fusion engine would read as "not water-driven" and resolve
        toward nitrogen deficiency, sending a farmer to buy fertilizer for a
        crop that may be dying of thirst.

        Nothing else in the pipeline can catch this: the value is in range,
        the reading is present, and the trend is a clean zero.
        """
        stuck = set()
        for channel in PLAUSIBLE_RANGES:
            series = self._series(channel)
            if len(series) >= FROZEN_RUN_LENGTH:
                tail = series[-FROZEN_RUN_LENGTH:]
                if all(v == tail[0] for v in tail):
                    stuck.add(channel)
        return frozenset(stuck)

    def _trusted(self, channel: str) -> list[float]:
        """Plausible values for a channel, or nothing if the channel is stuck."""
        if channel in self.frozen_channels:
            return []
        return self._series(channel)

    @property
    def current_moisture(self) -> float | None:
        series = self._trusted("soil_moisture_pct")
        return series[-1] if series else None

    @property
    def moisture_trend_pct_per_day(self) -> float | None:
        """Least-squares slope of soil moisture against time, in %/day.

        Negative means drying. Returns None when there is too little data to fit,
        rather than a misleading zero.
        """
        if "soil_moisture_pct" in self.frozen_channels:
            # A stuck probe fits a perfect zero slope. Reporting that as
            # "stable" would be worse than reporting nothing.
            return None

        pairs = [
            (r.hours_ago, r.soil_moisture_pct)
            for r in self.readings
            if r.is_valid("soil_moisture_pct")
        ]
        if len(pairs) < 3:
            return None

        # hours_ago decreases toward the present, so negate to get forward time.
        xs = [-h / 24.0 for h, _ in pairs]
        ys = [m for _, m in pairs]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom == 0:
            return None
        return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom

    @property
    def peak_temp_c(self) -> float | None:
        series = self._trusted("air_temp_c")
        return max(series) if series else None

    @property
    def mean_humidity_pct(self) -> float | None:
        series = self._trusted("humidity_pct")
        return sum(series) / len(series) if series else None


@dataclass(frozen=True)
class VisionDifferential:
    """What the vision model outputs: ranked hypotheses, not a single label.

    Emitting a differential rather than an argmax is the design choice that makes
    fusion possible. An argmax throws away exactly the information fusion needs.
    """

    scores: dict[Hypothesis, float]

    def __post_init__(self) -> None:
        total = sum(self.scores.values())
        if not self.scores or abs(total - 1.0) > 1e-3:
            raise ValueError(f"vision scores must sum to 1.0, got {total:.4f}")

    @property
    def ranked(self) -> list[tuple[Hypothesis, float]]:
        return sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)

    @property
    def top(self) -> tuple[Hypothesis, float]:
        return self.ranked[0]

    @property
    def margin(self) -> float:
        """Gap between the top two hypotheses. A small margin means vision is unsure."""
        ranked = self.ranked
        return ranked[0][1] - ranked[1][1] if len(ranked) > 1 else ranked[0][1]


@dataclass(frozen=True)
class Evidence:
    """One human-readable reason, tied to the hypothesis it moved and by how much.

    Every element of an explanation must be traceable to a measurement. If we cannot
    name the signal and the direction it pushed, we do not show the recommendation.
    """

    signal: str
    observation: str
    hypothesis: Hypothesis
    direction: str  # "supports" | "contradicts"
    weight: float


@dataclass(frozen=True)
class Diagnosis:
    """Fusion output. Advisory only - never an actuation command."""

    hypothesis: Hypothesis
    confidence: float
    vision_only_hypothesis: Hypothesis
    vision_only_confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    degraded: bool = False
    needs_human_review: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def changed_by_sensors(self) -> bool:
        """True when the sensor layer overturned what the camera alone concluded.

        This is the headline metric for the whole approach: how often does fusion
        actually change the answer? If it never does, the sensors are decoration.
        """
        return self.hypothesis is not self.vision_only_hypothesis

    @property
    def recommended_action(self) -> str:
        if self.needs_human_review:
            return "inspect manually - evidence is not conclusive"
        return INTERVENTION[self.hypothesis]
