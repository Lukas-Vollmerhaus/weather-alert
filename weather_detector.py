#! /usr/bin/env python3

import os,sys
import configparser
from alert_gdps_10day import Alert_GDPS_10day
from alert_gfs_10day import Alert_GFS_10day
from alert_rdps_3day import Alert_RDPS_3day
from slack_sdk import WebClient



class location:
    def __init__(self,name,lat,long):
        self.name = name
        self.lat = lat
        self.long = long

class result:
    def __init__(self, date, good_weather, partial,location):
        self.date = date
        self.good_weather = good_weather
        self.partial = partial
        self.location = location


LOCATION_LIST = [location("Bugaboos",50.738045,-116.768606),
                 location("Spillimacheen",50.90827,-116.44277),
                 location("Stone hill",48.792848,-115.297972)]

GDPS_RESULT_LIST = []
GFS_RESULT_LIST = []
RDPS_RESULT_LIST = []

def slack_alert(message):
    weather_alert_bot_token = "xoxb-7015922744519-7028590296021-2f2cwlMpDI2Y4xJwlK1b2XPS"
    channel_name = "weather-alert"
    client = WebClient(token=weather_alert_bot_token)
    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def slack_message(message):
    weather_alert_bot_token = "xoxb-7015922744519-7028590296021-2f2cwlMpDI2Y4xJwlK1b2XPS"
    channel_name = "weather-alert"
    bot_user = "weather alert"
    client = WebClient(token=weather_alert_bot_token)

    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def slack_error(message):
    weather_alert_bot_token = "xoxb-7015922744519-7028590296021-2f2cwlMpDI2Y4xJwlK1b2XPS"
    channel_name = "error-message"
    bot_user = "weather alert"
    client = WebClient(token=weather_alert_bot_token)

    result = client.chat_postMessage(channel=channel_name,text=message)

    return result

def alert():
    for result in GDPS_RESULT_LIST:
        if result.good_weather:
            message = "Weather window detected by GDPS at %s for 48hrs starting %s" % (result.location.name, result.date)
            slack_alert(message)

    for result in GFS_RESULT_LIST:
        
        if result.good_weather:
            message = "Weather window detected by GFS at %s for 48hrs starting %s" % (result.location.name, result.date)
            slack_alert(message)

    for result in RDPS_RESULT_LIST:
        print(result.date, result.good_weather, result.partial, result.location.name)
        if result.good_weather:
            message = "Weather window detected by RDPS at %s for 48hrs starting %s" % (result.location.name, result.date)
            slack_alert(message)

def main():
    for loc in LOCATION_LIST:
        first_weekend_good, first_weekend_date, second_weekend_good, second_weekend_date, second_weekend_partial = Alert_GDPS_10day(loc)
        GDPS_RESULT_LIST.append(result(first_weekend_date,first_weekend_good,False,loc))
        GDPS_RESULT_LIST.append(result(second_weekend_date,second_weekend_good,second_weekend_partial,loc))

        first_weekend_good, first_weekend_date, second_weekend_good, second_weekend_date, second_weekend_partial = Alert_GFS_10day(loc)
        GFS_RESULT_LIST.append(result(first_weekend_date,first_weekend_good,False,loc))
        GFS_RESULT_LIST.append(result(second_weekend_date,second_weekend_good,second_weekend_partial,loc))

        weekend_good,weekend_date,weekend_partial = Alert_RDPS_3day(loc)
        if weekend_date == False: #weekend data was not found
            continue
        else:
            RDPS_RESULT_LIST.append(result(weekend_date,weekend_good,weekend_partial,loc))

    if len(GDPS_RESULT_LIST) == 0:
        slack_error("No results returned for GDPS forecast")
    if len(GFS_RESULT_LIST) == 0:
        slack_error("No results returned for GFS forecast")   
    if len(RDPS_RESULT_LIST) == 0:
        slack_error("No results returned for RDPS forecast")        

    alert()

    return 0 

if(__name__ == '__main__'):
    main_exit = main()
    sys.exit(main_exit)
