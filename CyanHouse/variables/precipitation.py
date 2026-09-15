import pandas as pd
from utilities.base import WeatherVariable


class Precipitation(WeatherVariable):
    """Hourly precipitation via Open-Meteo."""

    META = {
        "precip_mm": {
            "label":       "Precipitation",
            "unit":        "mm",
            "group":       "🌧 Precipitation",
            "default":     True,
            "description": "Total precipitation in the hour",
        },
        "precip_indicator": {
            "label":       "Precip. occurred",
            "unit":        None,
            "group":       "🌧 Precipitation",
            "default":     False,
            "description": "Whether precipitation occurred (derived from precip_mm > 0)",
        },
        "precip_type": {
            "label":       "Precip. type",
            "unit":        None,
            "group":       "🌧 Precipitation",
            "default":     False,
            "description": "Form of precipitation — WMO weather code",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "coords" not in city:
            raise ValueError(f"City has no coords for Open-Meteo: {city['city_name']}")
        df = self._om_fetch(city, ["precipitation", "weather_code"], start_date, end_date)
        df = df.rename(columns={
            "precipitation": "precip_mm",
            "weather_code":  "precip_type",
        })
        df["precip_indicator"] = (df["precip_mm"] > 0).astype(int)
        return df[["precip_mm", "precip_indicator", "precip_type"]]
