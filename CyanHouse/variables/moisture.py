import pandas as pd
from utilities.base import WeatherVariable


class Moisture(WeatherVariable):
    """Hourly humidity and vapour pressure (DWD only)."""

    META = {
        "vapor_pressure_hpa": {
            "label":       "Vapour Pressure",
            "unit":        "hPa",
            "group":       "🌬 Pressure",
            "default":     False,
            "description": "Actual vapour pressure of water in the air (DWD only)",
        },
        "wetbulb_c": {
            "label":       "Wet-bulb Temp",
            "unit":        "°C",
            "group":       "🌡 Temperature & Humidity",
            "default":     False,
            "description": "Temperature a wet surface reaches by evaporative cooling (DWD only)",
        },
        "abs_humidity_g_m3": {
            "label":       "Abs. Humidity",
            "unit":        "g/m³",
            "group":       "🌡 Temperature & Humidity",
            "default":     False,
            "description": "Mass of water vapour per cubic metre of air (DWD only)",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "station_id" not in city:
            return pd.DataFrame()
        sid = self._dwd_station_str(city)
        url = f"{self.DWD_BASE_URL}/moisture/recent/stundenwerte_TF_{sid}_akt.zip"
        df = self._dwd_zip(url)
        return df[["VP_STD", "TF_STD", "ABSF_STD"]].rename(columns={
            "VP_STD":   "vapor_pressure_hpa",
            "TF_STD":   "wetbulb_c",
            "ABSF_STD": "abs_humidity_g_m3",
        })
