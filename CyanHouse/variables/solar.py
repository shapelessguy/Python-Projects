import pandas as pd
from utilities.base import WeatherVariable


class Solar(WeatherVariable):
    """Hourly solar radiation.

    OM (all cities with coords): global shortwave + diffuse radiation.
    DWD (cities with station_id): adds atmospheric radiation + solar zenith.
    """

    META = {
        "global_radiation_j_cm2": {
            "label":       "Global Radiation",
            "unit":        "J/cm²",
            "group":       "☀ Solar Radiation",
            "default":     False,
            "description": "Total downward shortwave radiation at surface",
        },
        "diffuse_radiation_j_cm2": {
            "label":       "Diffuse Radiation",
            "unit":        "J/cm²",
            "group":       "☀ Solar Radiation",
            "default":     False,
            "description": "Diffuse fraction of shortwave radiation",
        },
        "atmo_radiation_j_cm2": {
            "label":       "Atmo. Radiation",
            "unit":        "J/cm²",
            "group":       "☀ Solar Radiation",
            "default":     False,
            "description": "Atmospheric (longwave) counter-radiation (DWD only)",
        },
        "solar_zenith_deg": {
            "label":       "Solar Zenith",
            "unit":        "°",
            "group":       "☀ Solar Radiation",
            "default":     False,
            "description": "Solar zenith angle at end of interval (DWD only)",
        },
    }

    def download(self, city: dict, start_date: str, end_date: str) -> pd.DataFrame:
        if "coords" not in city:
            raise ValueError(f"City has no coords for Open-Meteo: {city['city_name']}")

        # OM: global + diffuse for all cities
        df = self._om_fetch(
            city,
            ["shortwave_radiation", "diffuse_radiation"],
            start_date,
            end_date,
        )
        # Convert W/m² → J/cm²  (×3600 s/h ÷ 10000 cm²/m² = ×0.36)
        df["shortwave_radiation"] *= 0.36
        df["diffuse_radiation"]   *= 0.36
        result = df.rename(columns={
            "shortwave_radiation": "global_radiation_j_cm2",
            "diffuse_radiation":   "diffuse_radiation_j_cm2",
        })

        # DWD extras: atmo radiation + zenith
        if "station_id" in city:
            sid = self._dwd_station_str(city)
            url = f"{self.DWD_BASE_URL}/solar/stundenwerte_ST_{sid}_row.zip"
            try:
                dwd_df = self._dwd_zip_solar(url)
                extras = dwd_df[["ATMO_LBERG", "ZENIT"]].rename(columns={
                    "ATMO_LBERG": "atmo_radiation_j_cm2",
                    "ZENIT":      "solar_zenith_deg",
                })
                result = result.join(extras, how="left")
            except Exception as e:
                print(f"    [Solar] DWD extras unavailable for {city['city_name']}: {e}")

        return result
