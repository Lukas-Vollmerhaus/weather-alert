import numpy as np

#CONSTANTS
#Temperature
IDEAL_TEMP = 20 #best temperature for climbing
IDEAL_TEMP_LOW = 10 #still ok
IDEAL_TEMP_HIGH = 30 #still ok
MAX_TEMP = 35 #too hot
MIN_TEMP = 0#too cold

TEMP_STEP_WEIGHT = 10
TEMP_TRI_WEIGHT = 1

#Cloud
IDEAL_CLOUD = 0
IDEAL_CLOUD_HIGH = 100
IDEAL_CLOUD_LOW = 0

CLOUD_TRI_WEIGHT = 0.4

#WINDSPEED
IDEAL_WS = 0
IDEAL_WS_HIGH = 30
IDEAL_WS_LOW = 0
MAX_WS = 60
MIN_WS = 0

WS_STEP_WEIGHT = 10
WS_TRI_WEIGHT = 0.6

#Precipitation
IDEAL_PRECIP = 0
IDEAL_PRECIP_HIGH = 5
IDEAL_PRECIP_LOW = 0
MAX_PRECIP = 20 #what are the units on this value? mm?
MIN_PRECIP = 0

PRECIP_STEP_WEIGHT = 10
PRECIP_TRI_WEIGHT = 1


def evaluate_weather_fitness(weekend_data):
    '''
    It's like golf. The lower the fitness score the better the weekend
    '''
    avg_cloud, min_cloud, max_cloud = getAvgMinMax(weekend_data, "CLOUD")
    avg_temp, min_temp, max_temp = getAvgMinMax(weekend_data, "TMP")
    avg_ws, min_ws, max_ws = getAvgMinMax(weekend_data, "WS")
    total_precip = weekend_data.iloc[-1]['APCP'] - weekend_data.iloc[1]['APCP'] #total precip for weekend


    fitness = TEMP_STEP_WEIGHT*stepFunction(max_temp, MAX_TEMP, MIN_TEMP) +\
                TEMP_STEP_WEIGHT*triangleFunction(max_temp, IDEAL_TEMP_LOW, IDEAL_TEMP_HIGH, IDEAL_TEMP) +\
                CLOUD_TRI_WEIGHT*triangleFunction(avg_cloud, IDEAL_CLOUD_LOW, IDEAL_CLOUD_HIGH, IDEAL_CLOUD) +\
                WS_STEP_WEIGHT*stepFunction(avg_ws, MIN_WS, MAX_WS) +\
                WS_TRI_WEIGHT*triangleFunction(avg_ws, IDEAL_WS_LOW, IDEAL_WS_HIGH, IDEAL_WS) +\
                PRECIP_STEP_WEIGHT*stepFunction(total_precip, MIN_PRECIP, MAX_PRECIP) +\
                PRECIP_TRI_WEIGHT*triangleFunction(total_precip, IDEAL_PRECIP_LOW, IDEAL_PRECIP_HIGH, IDEAL_PRECIP)
    
    return fitness

def getAvgMinMax(weekend_data, key):
    avg_val = np.mean(weekend_data[key])
    min_val = np.mean(weekend_data[key])
    max_val = np.mean(weekend_data[key])

    return avg_val, min_val, max_val


def stepFunction(value, MIN_THRESHOLD, MAX_THRESHOLD):
    '''
    Returns a 0 if threshold values are not exceeded, else returns 1
    '''
    if value < MAX_THRESHOLD and value > MAX_THRESHOLD:
        return 0
    else:
        return 1
    
def triangleFunction(value, MIN_THRESHOLD, MAX_THRESHOLD, IDEAL):
    '''
    Returns a value between 0 and 1 based on fitting the input value to a triangular distribution wher MIN=1, MAX=1 and IDEAL=0
    '''
    if value > IDEAL:
        return min((value-IDEAL)/(MAX_THRESHOLD-IDEAL),1)
    elif value < IDEAL:
        return min(1-(value-MIN_THRESHOLD)/(IDEAL-MIN_THRESHOLD),1)
    else:
        #Must equal IDEAL
        return 0

