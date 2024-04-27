#! /usr/bin/env python3

import os,sys
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from selenium import webdriver
from selenium.webdriver.common.by import By
import numpy as np
import argparse
from slack_sdk import WebClient

CSV_PATH = "/home/lukas/Downloads/SpotWx Forecast.csv"

MAX_CLOUD_THRESHOLD = 50 #percent
MIN_TEMPERATURE_THRESHOLD = 0   #celcius
MAX_TEMPERATURE_THRESHOLD = 30       
MAX_PRECIP_THRESHOLD = 0   #mm rain // cm snow 
MAX_WIND_THRESHOLD = 10  #km/h 

brick_tamland = "xoxb-7015922744519-7028590296021-UE547noeSdKPQPYvam2qnVmt"

def slack_alert(message):
    weather_alert_bot_token = brick_tamland
    channel_name = "weather-alert"
    client = WebClient(token=weather_alert_bot_token)
    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def slack_update(message):
    weather_alert_bot_token = brick_tamland
    channel_name = "weather-update"
    client = WebClient(token=weather_alert_bot_token)
    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def slack_error(message):
    weather_alert_bot_token = brick_tamland
    channel_name = "error-message"
    client = WebClient(token=weather_alert_bot_token)
    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def get_csv(URL_STRING):
    try:
        driver = webdriver.Firefox()
        driver.get(URL_STRING)

        csv_button = driver.find_element(By.CLASS_NAME,"buttons-csv")
        csv_button.click()
        driver.quit()
    except Exception as e:
        print("Error clicking button: %s" % (e))
        return(1)
    
    try:
        data = pd.read_csv(CSV_PATH)
    except Exception as e:
        print("Error reading CSV file: %s" % (e))

    data['DATETIME'] = pd.to_datetime(data['DATETIME'],format="%Y/%m/%d %H:%M") #convert datetine column to datet time object
    #print(data.to_string())
    os.remove(CSV_PATH)
    return(data)

def find_weekend(data):
    index = 0
    weekend_data_list = []
    weekend_found = False

    for day in data['DATETIME']:
        if day.weekday() == 5 or day.weekday() == 6: #saturday
            if not weekend_found:
                weekend_found = True
            weekend_data_list.append(index)

        index = index + 1
        
    return(weekend_data_list,weekend_found,index)

def evaluate_thresholds(weekend_data):
    weekend_good = True
    avg_cloud = np.mean(weekend_data['CLOUD']) #avg cloud cover'
    weekend_good = weekend_good and (avg_cloud <= MAX_CLOUD_THRESHOLD)
    avg_temp = np.mean(weekend_data['TMP']) #avg temp
    weekend_good = weekend_good and (avg_temp < MAX_TEMPERATURE_THRESHOLD) and (avg_temp > MIN_TEMPERATURE_THRESHOLD)
    avg_ws = np.mean(weekend_data['WS']) #avg windspeed at ground
    weekend_good = weekend_good and (avg_ws <= MAX_WIND_THRESHOLD)
    total_precip = weekend_data.iloc[-1]['APCP'] - weekend_data.iloc[1]['APCP'] #total precip for weekend
    weekend_good = weekend_good and (total_precip <= MAX_PRECIP_THRESHOLD)
    slack_update("cloud %f temp %f ws %f precip %f" % (avg_cloud,avg_temp,avg_ws,total_precip))
    return(weekend_good)

def assess_weekends(data,weekend_data_list,index):
    weekend_partial = False

    if weekend_data_list[0] != 0: #weekend isn't today
        weekend_index = weekend_data_list[0]

        if index - weekend_index >= 48: #data contains entire weekend
            weekend_data = data.iloc[weekend_index:weekend_index+48]
            weekend_good = evaluate_thresholds(weekend_data)
            weekend_date = weekend_data['DATETIME'][weekend_index]

        else: #report on partial weekend
            weekend_data = data.iloc[weekend_index:-1] #get available data
            weekend_good = evaluate_thresholds(weekend_data)
            weekend_date = weekend_data['DATETIME'][weekend_index]
            weekend_partial = True

        
    else:
        weekend_good = False #don't report a weekend thats already happening
        print("first weekend happening now")
        
   
    return(weekend_good,weekend_date,weekend_partial)

def Alert_RDPS_3day(location):
    RDPS_3DAY = "https://spotwx.com/products/grib_index.php?model=rdps_10km&lat=XXXX&lon=YYYY&tz=America/Edmonton&display=table"
    slack_update(location.name + " RDPS")
    slack_update(RDPS_3DAY)
    RDPS_3DAY = RDPS_3DAY.replace("XXXX",str(location.lat))
    RDPS_3DAY = RDPS_3DAY.replace("YYYY",str(location.long))
    print(RDPS_3DAY)
    data = get_csv(RDPS_3DAY)
    weekend_data_list,weekend_found,index = find_weekend(data)

    if not weekend_found:
        slack_update("No weekend in current model")
        sys.exit(0,0,0)

    weekend,weekend_date, weekend_partial = assess_weekends(data,weekend_data_list,index)

    print("RDPS %s Weekend is good? %r, weekend is partial? %r" % (location.name,weekend,weekend_partial))

    return weekend, weekend_date, weekend_partial

if (__name__ == '__Alert_RDPS_3day__'):
    main_exit = Alert_RDPS_3day()
    sys.exit(main_exit)