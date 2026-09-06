"""Field sensor simulator.

Emits the same `SensorWindow` contract the physical sensor driver will emit, so that
fusion, the advisory layer and the UI never learn whether they are talking to a
simulator or to a real probe. Swapping in hardware later is a driver change, not an
architecture change.

Every scenario is seeded, so demos replay identically. A demo that behaves differently
on stage than in rehearsal is a demo that fails on stage.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..contracts import SensorReading, SensorWindow


@dataclass(frozen=True)
class Scenario:
    """A named field condition with the parameters that generate it."""

    name: str
    description: str
    start_moisture_pct: float
    moisture_drift_per_day: float
    base_temp_c: float
    temp_amplitude_c: float
    base_humidity_pct: float
    hours_since_irrigation: float | None
    dropout_probability: float = 0.0
    #: Hours-ago at which the soil probe dies and holds its last value.
    #: Readings more recent than this repeat that value exactly.
    moisture_stuck_after: float | None = None


SCENARIOS: dict[str, Scenario] = {
    "drying_down": Scenario(
        name="drying_down",
        description="No irrigation for five days; soil drying steadily under high heat.",
        start_moisture_pct=34.0,
        moisture_drift_per_day=-4.5,
        base_temp_c=36.0,
        temp_amplitude_c=6.0,
        base_humidity_pct=42.0,
        hours_since_irrigation=120.0,
    ),
    "well_watered": Scenario(
        name="well_watered",
        description="Irrigated yesterday; moisture adequate and stable.",
        start_moisture_pct=33.0,
        moisture_drift_per_day=-0.6,
        base_temp_c=31.0,
        temp_amplitude_c=5.0,
        base_humidity_pct=55.0,
        hours_since_irrigation=20.0,
    ),
    "humid_spell": Scenario(
        name="humid_spell",
        description="Post-monsoon humidity holding above 80% with warm nights.",
        start_moisture_pct=41.0,
        moisture_drift_per_day=-0.3,
        base_temp_c=29.0,
        temp_amplitude_c=3.0,
        base_humidity_pct=86.0,
        hours_since_irrigation=48.0,
    ),
    "waterlogged": Scenario(
        name="waterlogged",
        description="Heavy rainfall; soil saturated and draining slowly.",
        start_moisture_pct=52.0,
        moisture_drift_per_day=-1.2,
        base_temp_c=28.0,
        temp_amplitude_c=3.0,
        base_humidity_pct=88.0,
        hours_since_irrigation=None,
    ),
    "dying_probe": Scenario(
        name="dying_probe",
        description=(
            "Soil is drying hard, but the probe died a day ago and is still "
            "reporting its last adequate-looking value."
        ),
        start_moisture_pct=33.0,
        moisture_drift_per_day=-4.5,
        base_temp_c=37.0,
        temp_amplitude_c=6.0,
        base_humidity_pct=40.0,
        hours_since_irrigation=110.0,
        moisture_stuck_after=24.0,
    ),
    "failing_sensor": Scenario(
        name="failing_sensor",
        description="Intermittent probe fault - half the readings drop out.",
        start_moisture_pct=22.0,
        moisture_drift_per_day=-3.0,
        base_temp_c=35.0,
        temp_amplitude_c=6.0,
        base_humidity_pct=45.0,
        hours_since_irrigation=90.0,
        dropout_probability=0.5,
    ),
}


def generate_window(
    scenario: str | Scenario,
    *,
    hours: int = 72,
    interval_hours: int = 3,
    seed: int = 42,
) -> SensorWindow:
    """Build a `SensorWindow` for the named scenario.

    Readings run from `hours` ago up to now. Diurnal temperature and humidity cycles
    are modelled explicitly because a mid-afternoon moisture dip is not the same
    signal as a multi-day drying trend, and fusion must not confuse them.
    """
    spec = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
    rng = random.Random(seed)

    readings: list[SensorReading] = []
    stuck_value: float | None = None

    for hours_ago in range(hours, -1, -interval_hours):
        days_elapsed = (hours - hours_ago) / 24.0

        moisture = spec.start_moisture_pct + spec.moisture_drift_per_day * days_elapsed
        moisture += rng.gauss(0, 0.4)
        moisture = max(0.0, min(100.0, moisture))

        # A dead probe keeps reporting. Latch the last live value and repeat it
        # verbatim - no noise, which is exactly what makes it detectable.
        if spec.moisture_stuck_after is not None and hours_ago <= spec.moisture_stuck_after:
            if stuck_value is None:
                stuck_value = round(moisture, 1)
            moisture = stuck_value

        # Peak heat mid-afternoon, trough before dawn.
        hour_of_day = (24 - (hours_ago % 24)) % 24
        diurnal = math.sin((hour_of_day - 9) / 24.0 * 2 * math.pi)
        temp = spec.base_temp_c + spec.temp_amplitude_c * diurnal + rng.gauss(0, 0.5)

        # Humidity runs inverse to temperature.
        humidity = spec.base_humidity_pct - 8.0 * diurnal + rng.gauss(0, 1.5)
        humidity = max(0.0, min(100.0, humidity))

        dropped = rng.random() < spec.dropout_probability
        readings.append(
            SensorReading(
                hours_ago=float(hours_ago),
                soil_moisture_pct=None if dropped else round(moisture, 1),
                air_temp_c=None if dropped else round(temp, 1),
                humidity_pct=None if dropped else round(humidity, 1),
            )
        )

    return SensorWindow(
        readings=readings, hours_since_irrigation=spec.hours_since_irrigation
    )
