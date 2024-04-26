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

def slack_alert(message):
    weather_alert_bot_token = "xoxb-7015922744519-7028590296021-2f2cwlMpDI2Y4xJwlK1b2XPS"
    channel_name = "weather-alert"
    client = WebClient(token=weather_alert_bot_token)
    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def slack_update(message):
    weather_alert_bot_token = "xoxb-7015922744519-7028590296021-2f2cwlMpDI2Y4xJwlK1b2XPS"
    channel_name = "weather-update"
    client = WebClient(token=weather_alert_bot_token)
    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def slack_error(message):
    weather_alert_bot_token = "xoxb-7015922744519-7028590296021-2f2cwlMpDI2Y4xJwlK1b2XPS"
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

def find_weekends(data):
    index = 0
    weekend_data_list = []
    weekend_found = False
    start_weekend_list = []

    for day in data['DATETIME']:
        if day.weekday() == 5 or day.weekday() == 6: #saturday
            if not weekend_found:
                start_weekend_list.append(index)
                weekend_found = True
            weekend_data_list.append(index)
            
        if weekend_found:
            if (index - start_weekend_list[-1]) >= 16: #16 data points per weekend for gdps 10day
                weekend_found = False
        index = index + 1
        
    return(weekend_data_list,start_weekend_list,index)

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

def assess_weekends(data,weekend_data_list,start_weekend_list,index):
    
    second_weekend_partial = False
    if start_weekend_list[0] != 0: #weekend isn't today
        first_weekend_index = start_weekend_list[0]
        weekend_data = data.iloc[first_weekend_index:first_weekend_index+16]
        print("First weekend")
        first_weekend_good = evaluate_thresholds(weekend_data)
        first_weekend_date = weekend_data['DATETIME'][first_weekend_index]
        
    else:
        first_weekend_good = False #don't report a weekend thats already happening
        print("first weekend happening now")
        
    second_weekend_index = start_weekend_list[1]

    if index - second_weekend_index < 16: #partial weekend
        second_weekend_partial = True
        weekend_data = data.iloc[second_weekend_index:]
        print("Second weekend")
        second_weekend_good = evaluate_thresholds(weekend_data)
        second_weekend_date = weekend_data['DATETIME'][second_weekend_index]
        
    else:
        weekend_data = data.iloc[second_weekend_index:]
        print("Second weekend")
        second_weekend_good = evaluate_thresholds(weekend_data)
        second_weekend_date = weekend_data['DATETIME'][second_weekend_index]

    return(first_weekend_good,first_weekend_date,second_weekend_good,second_weekend_date, second_weekend_partial)

def Alert_GDPS_10day(location):
    GDPS_10DAY = "https://spotwx.com/products/grib_index.php?model=gem_glb_15km&lat=XXXX&lon=YYYY&tz=America/Edmonton&display=table"
    slack_update(location.name + " GDPS")
    slack_update(GDPS_10DAY)
    GDPS_10DAY = GDPS_10DAY.replace("XXXX",str(location.lat))
    GDPS_10DAY = GDPS_10DAY.replace("YYYY",str(location.long))
    print(GDPS_10DAY)
    data = get_csv(GDPS_10DAY)
    weekend_data_list,start_weekend_list,index = find_weekends(data)
    first_weekend,first_weekend_date, second_weekend, second_weekend_date, second_weekend_partial = assess_weekends(data,weekend_data_list,start_weekend_list,index)

    print("First weekend is good? %r, Second weekend is good? %r, Second weekend is partial? %r" % (first_weekend,second_weekend,second_weekend_partial))

    return first_weekend, first_weekend_date, second_weekend, second_weekend_date, second_weekend_partial

if (__name__ == '__Alert_GDPS_10day__'):
    main_exit = Alert_GDPS_10day()
    sys.exit(main_exit)