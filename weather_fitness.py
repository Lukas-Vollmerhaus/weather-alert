#!/home/lukas/miniconda3/envs/weather-alert/bin/python
import configparser
import numpy as np

FITNESS_CONF = "/usr/local/src/weather-alert/weather_fitness.conf"

def _load_config(path=FITNESS_CONF):
    config = configparser.ConfigParser()
    config.read(path)
    return config

_cfg = _load_config()

# Basic
SEASON = _cfg.get("basic", "season")

# Temperature
IDEAL_TEMP       = _cfg.getfloat("temperature", "ideal")
IDEAL_TEMP_LOW   = _cfg.getfloat("temperature", "ideal_low")
IDEAL_TEMP_HIGH  = _cfg.getfloat("temperature", "ideal_high")
MAX_TEMP         = _cfg.getfloat("temperature", "max")
MIN_TEMP         = _cfg.getfloat("temperature", "min")
TEMP_STEP_WEIGHT = _cfg.getfloat("temperature", "step_weight")
TEMP_TRI_WEIGHT  = _cfg.getfloat("temperature", "tri_weight")

# Cloud
IDEAL_CLOUD      = _cfg.getfloat("cloud", "ideal")
IDEAL_CLOUD_LOW  = _cfg.getfloat("cloud", "ideal_low")
IDEAL_CLOUD_HIGH = _cfg.getfloat("cloud", "ideal_high")
CLOUD_TRI_WEIGHT = _cfg.getfloat("cloud", "tri_weight")

# Wind speed
IDEAL_WS         = _cfg.getfloat("windspeed", "ideal")
IDEAL_WS_LOW     = _cfg.getfloat("windspeed", "ideal_low")
IDEAL_WS_HIGH    = _cfg.getfloat("windspeed", "ideal_high")
MAX_WS           = _cfg.getfloat("windspeed", "max")
MIN_WS           = _cfg.getfloat("windspeed", "min")
WS_STEP_WEIGHT   = _cfg.getfloat("windspeed", "step_weight")
WS_TRI_WEIGHT    = _cfg.getfloat("windspeed", "tri_weight")

# Precipitation
IDEAL_PRECIP       = _cfg.getfloat("precipitation", "ideal")
IDEAL_PRECIP_LOW   = _cfg.getfloat("precipitation", "ideal_low")
IDEAL_PRECIP_HIGH  = _cfg.getfloat("precipitation", "ideal_high")
MAX_PRECIP         = _cfg.getfloat("precipitation", "max")
MIN_PRECIP         = _cfg.getfloat("precipitation", "min")
PRECIP_STEP_WEIGHT = _cfg.getfloat("precipitation", "step_weight")
PRECIP_TRI_WEIGHT  = _cfg.getfloat("precipitation", "tri_weight")


def evaluate_weather_fitness(weekend_data):
    '''
    Computes an overall fitness score for a weekend of weather data.
    It's like golf. The lower the fitness score the better the weekend.

    The score combines penalty terms for temperature, cloud cover, wind speed,
    and precipitation. Each variable contributes:
      - A step function penalty (heavy weight) if the value exceeds hard thresholds
      - A triangle function penalty (lighter weight) based on distance from ideal

    Precipitation is evaluated on daily totals derived from the cumulative APCP
    column: max single-day total drives the hard threshold, avg daily total
    drives the soft penalty.

    Parameters:
        weekend_data (pd.DataFrame): rows of forecast data covering the weekend,
            with columns: CLOUD, TMP, WS, APCP

    Returns:
        float: fitness score (lower is better)
    '''
    avg_cloud, min_cloud, max_cloud = getAvgMinMax(weekend_data, "CLOUD")
    avg_temp, min_temp, max_temp = getAvgMinMax(weekend_data, "TMP")
    avg_ws, min_ws, max_ws = getAvgMinMax(weekend_data, "WS")

    # Daily precipitation totals derived from cumulative APCP
    hourly_precip = weekend_data['APCP'].diff().fillna(0)
    daily_precip = hourly_precip.groupby(weekend_data['DATETIME'].dt.date).sum()
    avg_daily_precip = daily_precip.mean()
    max_daily_precip = daily_precip.max()

    fitness = (
        # Temperature: hard penalty if outside absolute limits, soft penalty based on distance from ideal
        TEMP_STEP_WEIGHT * stepFunction(max_temp, MAX_TEMP, MIN_TEMP) +
        TEMP_STEP_WEIGHT * triangleFunction(max_temp, IDEAL_TEMP_LOW, IDEAL_TEMP_HIGH, IDEAL_TEMP) +
        # Cloud cover: soft penalty only (no hard cutoff defined)
        CLOUD_TRI_WEIGHT * triangleFunction(avg_cloud, IDEAL_CLOUD_LOW, IDEAL_CLOUD_HIGH, IDEAL_CLOUD) +
        # Wind speed: hard penalty if above max, soft penalty based on distance from ideal (calm)
        WS_STEP_WEIGHT * stepFunction(avg_ws, MIN_WS, MAX_WS) +
        WS_TRI_WEIGHT * triangleFunction(avg_ws, IDEAL_WS_LOW, IDEAL_WS_HIGH, IDEAL_WS) +
        # Precipitation: evaluated on daily totals; max day drives hard threshold, avg drives soft
        PRECIP_STEP_WEIGHT * stepFunction(max_daily_precip, MIN_PRECIP, MAX_PRECIP) +
        PRECIP_TRI_WEIGHT * triangleFunction(avg_daily_precip, IDEAL_PRECIP_LOW, IDEAL_PRECIP_HIGH, IDEAL_PRECIP)
    )

    return fitness

def getAvgMinMax(weekend_data, key):
    '''
    Returns the average, min, and max of a column in the weekend forecast data.

    Parameters:
        weekend_data (pd.DataFrame): forecast data rows
        key (str): column name to aggregate

    Returns:
        tuple: (avg, min, max)
    '''
    avg_val = np.mean(weekend_data[key])
    min_val = np.min(weekend_data[key])
    max_val = np.max(weekend_data[key])

    return avg_val, min_val, max_val


def stepFunction(value, MIN_THRESHOLD, MAX_THRESHOLD):
    '''
    Hard threshold penalty: returns 0 if value is within [MIN_THRESHOLD, MAX_THRESHOLD],
    otherwise returns 1.

    Used to apply a large, binary penalty when a weather variable exceeds acceptable limits.
    '''
    if value < MAX_THRESHOLD and value > MIN_THRESHOLD:
        return 0
    else:
        return 1

def triangleFunction(value, MIN_THRESHOLD, MAX_THRESHOLD, IDEAL):
    '''
    Soft distance penalty: returns a value in [0, 1] based on how far the input is
    from the ideal value, using a triangular shape where IDEAL=0, MIN=1, MAX=1.

    Used to score gradual degradation in conditions away from the ideal.
    '''
    if value > IDEAL:
        return min((value-IDEAL)/(MAX_THRESHOLD-IDEAL),1)
    elif value < IDEAL:
        return min(1-(value-MIN_THRESHOLD)/(IDEAL-MIN_THRESHOLD),1)
    else:
        # Value equals IDEAL: perfect score for this variable
        return 0

