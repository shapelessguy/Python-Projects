import pandas as pd
from utilities.base import WeatherVariable


class Cloudiness(WeatherVariable):
    """Hourly cloud cover and sunshine duration via Open-Meteo."""

    META = {
        "cloud_cover_oktas": {
            "label":       "Cloud Cover",
            "unit":        "oktas (0–8)",
            "group":       "☁ Cloudiness & Sun",
            "default":     False,
            "description": "Cloud cover in oktas (0=clear, 8=overcast). OM % ÷ 12.5",
        },
        "sunshine_min": {
            "label":       "Sunshine",
            "unit":        "min (0–60)",
            "group":       "☁ Cloudiness & Sun",
            "default":     False,
            "description": "Sunshine duration in the hour",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "coords" not in city:
            raise ValueError(f"City has no coords for Open-Meteo: {city['city_name']}")
        df = self._om_fetch(city, ["cloud_cover", "sunshine_duration"], start_date, end_date)
        df["cloud_cover_oktas"] = (df["cloud_cover"] / 12.5).round(1)
        df["sunshine_min"]      = df["sunshine_duration"] / 60
        return df[["cloud_cover_oktas", "sunshine_min"]]
