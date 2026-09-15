import pandas as pd
from utilities.base import WeatherVariable


class Pressure(WeatherVariable):
    """Hourly atmospheric pressure via Open-Meteo."""

    META = {
        "pressure_station_hpa": {
            "label":       "Pressure (station)",
            "unit":        "hPa",
            "group":       "🌬 Pressure",
            "default":     True,
            "description": "Atmospheric pressure at station level",
        },
        "pressure_sealevel_hpa": {
            "label":       "Pressure (sea level)",
            "unit":        "hPa",
            "group":       "🌬 Pressure",
            "default":     False,
            "description": "Atmospheric pressure reduced to mean sea level",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "coords" not in city:
            raise ValueError(f"City has no coords for Open-Meteo: {city['city_name']}")
        df = self._om_fetch(city, ["surface_pressure", "pressure_msl"], start_date, end_date)
        return df.rename(columns={
            "surface_pressure": "pressure_station_hpa",
            "pressure_msl":     "pressure_sealevel_hpa",
        })
