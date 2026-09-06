import json
from datetime import datetime, timezone
import random

VALIDITY = ("VALID", "STALE", "FAILED", "UNKNOWN")

class SensorDataGenerator:
    """Provides realistic mock sensor data matching the contract above."""
    
    _instance = None
    
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.state = {
            "air_temperature": 30.0,
            "humidity": 75.0,
            "soil_ph": 6.5,
            "soil_ec": 1.2,
            "soil_n": 40.0,
            "soil_p": 15.0,
            "soil_k": 30.0,
            "surface_moisture": 32.0,
            "root_moisture": 24.0,
            "tank_level": 80.0,
            "flow_lpm": 0.0,
            "light_lux": 1000.0
        }
        self.drift = {
            "surface_moisture": -0.45,
            "root_moisture": -0.25,
            "tank_level": -2.0
        }
        self.noise = {
            "surface_moisture": 0.1,
            "root_moisture": 0.05,
            "tank_level": 0.5
        }
        self.floor = {k: 0.0 for k in self.state}
        self.ceil = {k: 1500.0 for k in self.state}
        self.ceil.update({"surface_moisture": 100, "root_moisture": 100, "tank_level": 100})
        self.raining = False
        
    def step(self):
        self.raining = self.rng.random() < 0.1
        for k, v in self.state.items():
            d = self.drift.get(k, 0.0)
            n = self.noise.get(k, 0.5)
            v += d + self.rng.gauss(0, n)
            self.state[k] = max(self.floor.get(k, 0), min(self.ceil.get(k, 1000), v))
        if self.raining:
            self.state["surface_moisture"] += 6.0
            self.state["tank_level"] += 5.0
            
    @classmethod
    def generate_mock_reading(cls, faults=None, drop=None) -> dict:
        if cls._instance is None:
            cls._instance = cls()
        cls._instance.step()
        
        faults = faults or {}
        reading = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "rain": cls._instance.raining,
            "sensor_status": {
                "soil_ph": "VALID",
                "soil_ec": "VALID",
                "soil_npk": "VALID",
                "surface_moisture": "VALID",
                "root_moisture": "VALID",
                "tank_level": "VALID"
            }
        }
        for k, v in cls._instance.state.items():
            reading[k] = round(v, 1) if isinstance(v, float) else v
            
        reading["sensor_status"].update(faults)
        for key in (drop or []):
            reading.pop(key, None)
            
        return reading

if __name__ == "__main__":
    reading = SensorDataGenerator.generate_mock_reading()
    print(json.dumps(reading, indent=2))
