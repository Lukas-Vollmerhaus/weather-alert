#!/home/lukas/miniconda3/envs/weather-alert/bin/python
import configparser
import re
import numpy as np

FITNESS_CONF = "/usr/local/src/weather-alert/weather_fitness.conf"

def _load_config(path=FITNESS_CONF):
    config = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
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

# Recent snow (winter): fit of the previous days' snowfall to a steady
# PRECIP_RECENT_IDEAL cm per day. A weight of 0 (key absent) disables the term.
PRECIP_RECENT_DAYS        = _cfg.getint("precipitation", "recent_days", fallback=7)
PRECIP_RECENT_IDEAL       = _cfg.getfloat("precipitation", "recent_ideal", fallback=2.0)
PRECIP_RECENT_WEIGHT      = _cfg.getfloat("precipitation", "recent_weight", fallback=0.0)
PRECIP_RECENT_OVER_WEIGHT = _cfg.getfloat("precipitation", "recent_over_weight", fallback=1.0)

# Rain on the day (winter): more than RAIN_MAX mm adds RAIN_STEP_WEIGHT.
# A weight of 0 (key absent) disables the term.
RAIN_MAX         = _cfg.getfloat("precipitation", "rain_max", fallback=0.0)
RAIN_STEP_WEIGHT = _cfg.getfloat("precipitation", "rain_step_weight", fallback=0.0)

# Significant snowfall: daily totals (cm) from the sig_snow_1..N keys of the
# [precipitation] section, ascending. Each threshold reached earns one snowflake
# on the summary graphic. Display only - not part of the fitness score.
# Empty when the config has no sig_snow_N keys, which hides the snowflakes.
SIG_SNOW_THRESHOLDS = sorted(
    _cfg.getfloat("precipitation", k)
    for k in _cfg.options("precipitation") if re.fullmatch(r"sig_snow_\d+", k)
)

# Avalanche: maps a danger rating value (e.g. "considerable") to its penalty.
# Empty when the config has no [avalanche] section, which disables the parameter.
AVALANCHE_PENALTIES = ({k: float(v) for k, v in _cfg.items("avalanche")}
                       if _cfg.has_section("avalanche") else {})


def snowflake_count(snow_cm):
    '''
    Number of snowflakes for a day's snowfall total: one per sig_snow_N
    threshold (cm) that the total reaches. 0 if the total is missing.
    '''
    if snow_cm is None or np.isnan(snow_cm):
        return 0
    return sum(1 for threshold in SIG_SNOW_THRESHOLDS if snow_cm >= threshold)


def recent_snow_days():
    '''Days of snowfall history the recent-snow term needs; 0 when it is disabled.'''
    return PRECIP_RECENT_DAYS if PRECIP_RECENT_WEIGHT > 0 else 0


def recent_snow_penalty(recent_snow):
    '''
    Consistency of the snowfall leading up to a day, as a penalty in [0, 1].

    Counting back from the scored day, the snow that fell in the last k days
    (k = 1 .. PRECIP_RECENT_DAYS) is compared with the ideal steady supply of
    PRECIP_RECENT_IDEAL cm per day, i.e. a straight line from 0 to
    PRECIP_RECENT_IDEAL * PRECIP_RECENT_DAYS cm. The penalty is the mean
    distance from that line, scaled so that no snow at all gives 1:
      - on the line (steady snowfall)            -> 0
      - no snow in the whole window              -> 1
      - a dry spell right before the day costs more than one a week earlier
      - snow above the line counts only PRECIP_RECENT_OVER_WEIGHT as much

    Parameters:
        recent_snow (sequence of float): daily snowfall (cm) for the days
            before the scored day, most recent first. Missing or NaN days
            count as no snow.

    Returns:
        float: penalty in [0, 1] (lower is better)
    '''
    n = PRECIP_RECENT_DAYS
    days = np.zeros(n)
    given = np.nan_to_num(np.asarray(list(recent_snow or [])[:n], dtype=float), nan=0.0)
    days[:len(given)] = given

    actual = np.cumsum(days)
    ideal = PRECIP_RECENT_IDEAL * np.arange(1, n + 1)
    diff = actual - ideal
    distance = np.where(diff > 0, diff * PRECIP_RECENT_OVER_WEIGHT, -diff)
    return float(min(distance.mean() / ideal.mean(), 1.0))


def avalanche_enabled():
    '''True when the fitness config has an [avalanche] section.'''
    return bool(AVALANCHE_PENALTIES)


def avalanche_penalty(day_ratings):
    '''
    Avalanche contribution to the fitness score for one location on one day:
    the average of the configured penalties for the three elevation-band
    ratings (alpine / treeline / below treeline).

    A rating with no entry in the [avalanche] config (e.g. "norating") uses
    the "unknown" penalty, as does a day the forecast does not cover.

    Parameters:
        day_ratings (dict or None): {"alp": str, "tln": str, "btl": str}, or
            None when the location is in a forecast region but has no rating
            for this day.

    Returns:
        float: penalty (lower is better)
    '''
    if not AVALANCHE_PENALTIES:
        return 0.0
    unknown = AVALANCHE_PENALTIES.get("unknown", 0.0)
    if not day_ratings:
        return unknown
    return float(np.mean([AVALANCHE_PENALTIES.get(str(r).lower(), unknown)
                          for r in day_ratings.values()]))


def evaluate_weather_fitness(weekend_data, avalanche=0.0, recent_snow=None):
    '''
    Computes an overall fitness score for a weekend of weather data.
    It's like golf. The lower the fitness score the better the weekend.

    The score combines penalty terms for temperature, cloud cover, wind speed,
    precipitation, and avalanche danger. Each weather variable contributes:
      - A step function penalty (heavy weight) if the value exceeds hard thresholds
      - A triangle function penalty (lighter weight) based on distance from ideal

    Precipitation is evaluated on daily totals. In summer these are mm of
    precipitation derived from the cumulative APCP column. In winter they are
    cm of snowfall from the SNOW column, and two more terms are added when the
    config enables them: how steadily it snowed over the previous days
    (recent_snow_penalty) and a step penalty for any rain on the day.

    Parameters:
        weekend_data (pd.DataFrame): rows of forecast data covering the weekend,
            with columns: CLOUD, TMP, WS, APCP (plus SNOW and RAIN in winter)
        avalanche (float): avalanche penalty for this location and day, from
            avalanche_penalty(); 0 when not applicable
        recent_snow (sequence of float): daily snowfall (cm) for the days
            before this one, most recent first; used by the recent-snow term

    Returns:
        tuple: (fitness_score, top_contributor) where fitness_score is a float
            (lower is better) and top_contributor is the name of the weather
            variable with the highest penalty contribution ("temperature",
            "cloud", "wind", "precipitation", or "avalanche")
    '''
    avg_cloud, min_cloud, max_cloud = getAvgMinMax(weekend_data, "CLOUD")
    avg_temp, min_temp, max_temp = getAvgMinMax(weekend_data, "TMP")
    avg_ws, min_ws, max_ws = getAvgMinMax(weekend_data, "WS")

    # Daily precipitation totals derived from cumulative APCP
    hourly_precip = weekend_data['APCP'].diff().fillna(0)
    daily_precip = hourly_precip.groupby(weekend_data['DATETIME'].dt.date).sum()
    avg_daily_precip = daily_precip.mean()
    max_daily_precip = daily_precip.max()

    recent_snow_term = 0.0
    rain_term = 0.0
    if SEASON == "winter":
        dates = weekend_data['DATETIME'].dt.date
        # Winter precipitation thresholds are cm of snow, not mm of water
        max_daily_precip = weekend_data['SNOW'].groupby(dates).sum().max()
        if PRECIP_RECENT_WEIGHT > 0:
            recent_snow_term = PRECIP_RECENT_WEIGHT * recent_snow_penalty(recent_snow)
        if RAIN_STEP_WEIGHT > 0:
            max_daily_rain = weekend_data['RAIN'].groupby(dates).sum().max()
            rain_term = RAIN_STEP_WEIGHT * (1 if max_daily_rain > RAIN_MAX else 0)

    contributions = {
        "temperature":   (TEMP_STEP_WEIGHT * stepFunction(max_temp, MIN_TEMP, MAX_TEMP) +
                          TEMP_TRI_WEIGHT * triangleFunction(max_temp, IDEAL_TEMP_LOW, IDEAL_TEMP_HIGH, IDEAL_TEMP)),
        "cloud":         (CLOUD_TRI_WEIGHT * triangleFunction(avg_cloud, IDEAL_CLOUD_LOW, IDEAL_CLOUD_HIGH, IDEAL_CLOUD)),
        "wind":          (WS_STEP_WEIGHT * stepFunction(avg_ws, MIN_WS, MAX_WS) +
                          WS_TRI_WEIGHT * triangleFunction(avg_ws, IDEAL_WS_LOW, IDEAL_WS_HIGH, IDEAL_WS)),
        "precipitation": (PRECIP_STEP_WEIGHT * stepFunction(max_daily_precip, MIN_PRECIP, MAX_PRECIP) +
                          PRECIP_TRI_WEIGHT * triangleFunction(max_daily_precip, IDEAL_PRECIP_LOW, IDEAL_PRECIP_HIGH, IDEAL_PRECIP) +
                          recent_snow_term + rain_term),
        "avalanche":     avalanche,
    }

    fitness = sum(contributions.values())
    top_contributor = max(contributions, key=contributions.get)
    return fitness, top_contributor, contributions

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
    if value <= MAX_THRESHOLD and value >= MIN_THRESHOLD:
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

