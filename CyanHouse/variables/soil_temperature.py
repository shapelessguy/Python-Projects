import pandas as pd
from utilities.base import WeatherVariable


class SoilTemperature(WeatherVariable):
    """Hourly soil temperature at multiple depths (DWD only)."""

    META = {
        "soil_temp_5cm_c": {
            "label":       "Soil Temp 5cm",
            "unit":        "°C",
            "group":       "🌱 Soil Temperature",
            "default":     False,
            "description": "Soil temperature at 5cm depth (DWD only)",
        },
        "soil_temp_10cm_c": {
            "label":       "Soil Temp 10cm",
            "unit":        "°C",
            "group":       "🌱 Soil Temperature",
            "default":     False,
            "description": "Soil temperature at 10cm depth (DWD only)",
        },
        "soil_temp_20cm_c": {
            "label":       "Soil Temp 20cm",
            "unit":        "°C",
            "group":       "🌱 Soil Temperature",
            "default":     False,
            "description": "Soil temperature at 20cm depth (DWD only)",
        },
        "soil_temp_50cm_c": {
            "label":       "Soil Temp 50cm",
            "unit":        "°C",
            "group":       "🌱 Soil Temperature",
            "default":     False,
            "description": "Soil temperature at 50cm depth (DWD only)",
        },
        "soil_temp_100cm_c": {
            "label":       "Soil Temp 100cm",
            "unit":        "°C",
            "group":       "🌱 Soil Temperature",
            "default":     False,
            "description": "Soil temperature at 100cm depth (DWD only)",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "station_id" not in city:
            return pd.DataFrame()
        sid = self._dwd_station_str(city)
        url = f"{self.DWD_BASE_URL}/soil_temperature/recent/stundenwerte_EB_{sid}_akt.zip"
        df = self._dwd_zip(url)
        return df[["V_TE005", "V_TE010", "V_TE020", "V_TE050", "V_TE100"]].rename(columns={
            "V_TE005": "soil_temp_5cm_c",
            "V_TE010": "soil_temp_10cm_c",
            "V_TE020": "soil_temp_20cm_c",
            "V_TE050": "soil_temp_50cm_c",
            "V_TE100": "soil_temp_100cm_c",
        })
