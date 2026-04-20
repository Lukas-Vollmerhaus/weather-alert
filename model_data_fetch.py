#!/home/lukas/miniconda3/envs/weather-alert/bin/python
"""
Fetch hourly weather forecast data from the Open-Meteo API for a given location
and model. Returns a DataFrame with columns matching the rest of the codebase:
    DATETIME, TMP, CLOUD, WS, APCP

Supported models and their Open-Meteo identifiers:
    GDPS  -> gem_global    (Canadian Global, ~15 km, 10-day)
    RDPS  -> gem_regional  (Canadian Regional, ~10 km, 3.5-day)
    GFS   -> gfs_seamless  (American Global, ~25 km, 16-day)
    NAM   -> nam_conus     (North American Mesoscale, ~3 km, 60-hour)
"""

import configparser
import time
import syslog
import requests
import pandas as pd

LOCATIONS_CONF = "/usr/local/src/weather-alert/locations.conf"

# Open-Meteo endpoints
GEM_ENDPOINT = "https://api.open-meteo.com/v1/gem"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"

# Maps friendly model names to (endpoint, model_id, forecast_days)
MODEL_CONFIG = {
    "GDPS": (GEM_ENDPOINT,      "gem_global",      10),
    "RDPS": (GEM_ENDPOINT,      "gem_regional",     3),
    "GFS":  (FORECAST_ENDPOINT, "gfs_seamless",    10),
    "NAM":  (FORECAST_ENDPOINT, "ncep_nam_conus",   3),
}

HOURLY_VARS    = "temperature_2m,cloud_cover,wind_speed_10m,precipitation"
FETCH_TIMEOUT  = 120
FETCH_ATTEMPTS = 10


def fetch_forecast(location, model):
    """
    Fetch hourly forecast data from Open-Meteo for a single location and model.

    Parameters:
        location: object with .lat (float), .long (float), .name (str)
        model (str): one of "GDPS", "RDPS", "GFS", "NAM"

    Returns:
        pd.DataFrame with columns: DATETIME, TMP, CLOUD, WS, APCP
            APCP is accumulated precipitation (running cumulative sum of hourly values, mm)

    Raises:
        ValueError: if model name is not recognised
        requests.HTTPError: if the API returns an error status
    """
    if model not in MODEL_CONFIG:
        raise ValueError(f"Unknown model '{model}'. Choose from: {list(MODEL_CONFIG)}")

    endpoint, model_id, forecast_days = MODEL_CONFIG[model]

    params = {
        "latitude":       location.lat,
        "longitude":      location.long,
        "hourly":         HOURLY_VARS,
        "models":         model_id,
        "forecast_days":  forecast_days,
        "wind_speed_unit": "kmh",   # keep consistent with existing threshold constants (km/h)
        "timezone":       "America/Edmonton",
    }

    for attempt in range(FETCH_ATTEMPTS):
        try:
            response = requests.get(endpoint, params=params, timeout=FETCH_TIMEOUT)
            response.raise_for_status()
            break
        except requests.exceptions.Timeout:
            if attempt < FETCH_ATTEMPTS - 1:
                syslog.syslog(syslog.LOG_WARNING, f"Timeout on attempt {attempt + 1} for {model_id}, retrying...")
                time.sleep(10)
            else:
                raise
    data = response.json()

    hourly = data["hourly"]

    df = pd.DataFrame({
        "DATETIME": pd.to_datetime(hourly["time"]),
        "TMP":      hourly["temperature_2m"],
        "CLOUD":    hourly["cloud_cover"],
        "WS":       hourly["wind_speed_10m"],
        # Accumulate hourly precipitation into a running total, matching APCP convention
        "APCP":     pd.Series(hourly["precipitation"]).cumsum().values,
    })

    return df


def fetch_all_models(location):
    """
    Fetch forecast data for all four models for a single location.

    Parameters:
        location: object with .lat, .long, .name

    Returns:
        dict mapping model name -> pd.DataFrame (or None if the fetch failed)
    """
    results = {}
    for model in MODEL_CONFIG:
        try:
            results[model] = fetch_forecast(location, model)
            syslog.syslog(syslog.LOG_INFO, f"Fetched {model} for {location.name}")
        except Exception as e:
            syslog.syslog(syslog.LOG_ERR, f"Failed to fetch {model} for {location.name}: {e}")
            results[model] = None
    return results


def load_locations(path=LOCATIONS_CONF):
    config = configparser.ConfigParser()
    config.read(path)

    class location:
        def __init__(self, name, lat, long):
            self.name = name
            self.lat = lat
            self.long = long

    return [location(name, float(s["lat"]), float(s["long"])) for name, s in config.items() if name != "DEFAULT"]


if __name__ == "__main__":
    for loc in load_locations():
        print(f"\n=== {loc.name} ({loc.lat}, {loc.long}) ===")
        forecasts = fetch_all_models(loc)
        for model, df in forecasts.items():
            if df is not None:
                print(f"  {model}: {len(df)} hours, "
                      f"temp range {df['TMP'].min():.1f}–{df['TMP'].max():.1f} °C, "
                      f"total precip {df['APCP'].iloc[-1]:.1f} mm")
