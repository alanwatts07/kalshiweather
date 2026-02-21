"""GFS bias correction — per-station per-month MOS adjustments."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from lib.config import BIAS_MAX_AGE_DAYS, BIAS_MIN_SAMPLES

BIAS_DIR = Path.home() / ".openclaw" / "kalshi-weather"
BIAS_FILE = BIAS_DIR / "bias_corrections.json"


@dataclass
class MonthlyBias:
    mean_bias: float   # mean(forecast - actual) in F; positive = GFS runs warm
    std_error: float   # stdev of errors
    samples: int       # data points for this month


@dataclass
class BiasCorrections:
    version: int
    trained_at: str
    training_start: str
    training_end: str
    corrections: dict[str, dict[str, MonthlyBias]]  # city_code -> month_str -> MonthlyBias

    @classmethod
    def load(cls) -> Optional[BiasCorrections]:
        if not BIAS_FILE.exists():
            return None
        try:
            data = json.loads(BIAS_FILE.read_text())
            corrections: dict[str, dict[str, MonthlyBias]] = {}
            for city, months in data.get("corrections", {}).items():
                corrections[city] = {}
                for month, vals in months.items():
                    corrections[city][month] = MonthlyBias(**vals)
            return cls(
                version=data.get("version", 1),
                trained_at=data.get("trained_at", ""),
                training_start=data.get("training_start", ""),
                training_end=data.get("training_end", ""),
                corrections=corrections,
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save(self) -> None:
        BIAS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.version,
            "trained_at": self.trained_at,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "corrections": {
                city: {month: asdict(bias) for month, bias in months.items()}
                for city, months in self.corrections.items()
            },
        }
        BIAS_FILE.write_text(json.dumps(data, indent=2))

    def get_bias(self, city_code: str, month: int) -> Optional[MonthlyBias]:
        city_data = self.corrections.get(city_code)
        if not city_data:
            return None
        return city_data.get(str(month))

    def is_stale(self) -> bool:
        if not self.trained_at:
            return True
        try:
            trained = datetime.fromisoformat(self.trained_at)
            age_days = (datetime.now() - trained).days
            return age_days > BIAS_MAX_AGE_DAYS
        except ValueError:
            return True


def apply_bias_correction(members: list[float], bias: MonthlyBias) -> list[float]:
    """Shift all ensemble members by -mean_bias (remove systematic warm/cold bias)."""
    if bias.samples < BIAS_MIN_SAMPLES:
        return members
    return [m - bias.mean_bias for m in members]
