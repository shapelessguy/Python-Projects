import pandas as pd
from utilities.base import WeatherVariable


class Wind(WeatherVariable):
    """Hourly wind speed, direction and gusts via Open-Meteo."""

    META = {
        "wind_speed_ms": {
            "label":       "Wind Speed",
            "unit":        "m/s",
            "group":       "💨 Wind",
            "default":     False,
            "description": "Mean wind speed over the hour",
        },
        "wind_direction_deg": {
            "label":       "Wind Direction",
            "unit":        "°",
            "group":       "💨 Wind",
            "default":     False,
            "description": "Mean wind direction (0/360=N, 90=E, 180=S, 270=W)",
        },
        "wind_gusts_ms": {
            "label":       "Wind Gusts",
            "unit":        "m/s",
            "group":       "💨 Wind",
            "default":     False,
            "description": "Maximum wind gust in the hour",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "coords" not in city:
            raise ValueError(f"City has no coords for Open-Meteo: {city['city_name']}")
        df = self._om_fetch(city, ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"], start_date, end_date)
        return df.rename(columns={
            "wind_speed_10m":     "wind_speed_ms",
            "wind_direction_10m": "wind_direction_deg",
            "wind_gusts_10m":     "wind_gusts_ms",
        })
