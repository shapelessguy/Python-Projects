import pandas as pd
from utilities.base import WeatherVariable


class Sun(WeatherVariable):
    """Hourly sunshine duration from DWD dedicated sensor (DWD only)."""

    META = {
        "sunshine_min": {
            "label":       "Sunshine (DWD sensor)",
            "unit":        "min (0–60)",
            "group":       "☁ Cloudiness & Sun",
            "default":     False,
            "description": "Sunshine duration in the hour from DWD dedicated sensor (DWD only)",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "station_id" not in city:
            return pd.DataFrame()
        sid = self._dwd_station_str(city)
        url = f"{self.DWD_BASE_URL}/sun/recent/stundenwerte_SD_{sid}_akt.zip"
        df = self._dwd_zip(url)
        return df[["SD_SO"]].rename(columns={"SD_SO": "sunshine_min"})
