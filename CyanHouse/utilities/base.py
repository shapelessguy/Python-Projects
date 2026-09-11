import io
import zipfile
from abc import ABC, abstractmethod

import pandas as pd
import requests


class WeatherVariable(ABC):
    """Unified base for all weather variables.

    Each subclass implements download(city, start_date, end_date).
    The city dict has the shape:
        {"city_name": str, "country": str, "station_id": int}   # DWD
        {"city_name": str, "country": str, "coords": (lat, lon)} # Open-Meteo
    """

    DWD_BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"
    OM_BASE_URL  = "https://archive-api.open-meteo.com/v1/archive"

    @abstractmethod
    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        """Return a DataFrame indexed by 'datetime' with renamed columns."""
        ...

    # ── DWD helpers ───────────────────────────────────────────────────────

    def _dwd_station_str(self, city: dict) -> str:
        return str(city["station_id"]).zfill(5)

    def _dwd_zip(self, url: str) -> pd.DataFrame:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            data_file = next(n for n in zf.namelist() if n.startswith("produkt_"))
            with zf.open(data_file) as f:
                df = pd.read_csv(f, sep=";", encoding="latin-1")
        df.columns = df.columns.str.strip()
        df["datetime"] = pd.to_datetime(df["MESS_DATUM"].astype(str), format="%Y%m%d%H")
        df = df.set_index("datetime")
        df = df.replace(-999.0, float("nan"))
        df = df[~df.index.duplicated(keep="first")]
        return df

    def _dwd_zip_solar(self, url: str) -> pd.DataFrame:
        """Solar files use a 12-digit timestamp (YYYYMMDDHHMM)."""
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            data_file = next(n for n in zf.namelist() if n.startswith("produkt_"))
            with zf.open(data_file) as f:
                df = pd.read_csv(f, sep=";", encoding="latin-1")
        df.columns = df.columns.str.strip()
        df["datetime"] = (
            pd.to_datetime(df["MESS_DATUM"].astype(str).str.strip(), format="%Y%m%d%H:%M")
            .dt.round("h")
        )
        df = df.set_index("datetime")
        df = df.replace(-999.0, float("nan"))
        df = df.groupby(level=0).mean(numeric_only=True)
        return df

    # ── Open-Meteo helper ─────────────────────────────────────────────────

    def _om_fetch(
        self,
        city: dict,
        om_variables: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        lat, lon = city["coords"]
        params = {
            "latitude":        lat,
            "longitude":       lon,
            "start_date":      start_date,
            "end_date":        end_date,
            "hourly":          ",".join(om_variables),
            "timezone":        "auto",
            "wind_speed_unit": "ms",
        }
        response = requests.get(self.OM_BASE_URL, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data["hourly"])
        df["datetime"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"]).set_index("datetime")
        return df
