import pandas as pd
import requests
import json
from datetime import datetime

json_schdule = requests.get('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')

data = json_schdule.json()
season_opener_date = datetime(2023, 10, 24)
for date in data["leagueSchedule"]["gameDates"]:
    month = int(date['gameDate'].split('/')[0])
    day = int(date['gameDate'].split('/')[1])
    year = int(date['gameDate'].split('/')[2].split(' ')[0])
    if season_opener_date <= datetime(year, month, day):
        for i in date['games']:
            print(i['homeTeam']['teamName'])
# print(data["leagueSchedule"]["gameDates"])
print(season_opener_date)
