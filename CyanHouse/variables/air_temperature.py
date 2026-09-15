import pandas as pd
from utilities.base import WeatherVariable


class AirTemperature(WeatherVariable):
    """Hourly air temperature, humidity and dew point via Open-Meteo."""

    META = {
        "temperature_c": {
            "label":       "Air Temp",
            "unit":        "°C",
            "group":       "🌡 Temperature & Humidity",
            "default":     True,
            "description": "Air temperature at 2m above ground",
        },
        "humidity_pct": {
            "label":       "Humidity",
            "unit":        "%",
            "group":       "🌡 Temperature & Humidity",
            "default":     True,
            "description": "Relative humidity at 2m above ground",
        },
        "dewpoint_c": {
            "label":       "Dew Point",
            "unit":        "°C",
            "group":       "🌡 Temperature & Humidity",
            "default":     False,
            "description": "Dew point temperature at 2m above ground",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "coords" not in city:
            raise ValueError(f"City has no coords for Open-Meteo: {city['city_name']}")
        df = self._om_fetch(city, ["temperature_2m", "relative_humidity_2m", "dew_point_2m"], start_date, end_date)
        return df.rename(columns={
            "temperature_2m":       "temperature_c",
            "relative_humidity_2m": "humidity_pct",
            "dew_point_2m":         "dewpoint_c",
        })
