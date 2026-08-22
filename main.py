import os
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RAPIDAPI_KEY = "1e7360ef8cmsh9fd0715929add0dp1f2784jsnb68c929b74d8"
RAPIDAPI_HOST = "sportapi7.p.rapidapi.com"

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/matches")
def get_matches():
    utc_now = datetime.now(timezone.utc)
    tsi_now = utc_now + timedelta(hours=3)
    
    url = f"https://{RAPIDAPI_HOST}/api/v1/sport/football/events/live"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }

    matches_list = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            events = data.get('events', []) if isinstance(data, dict) else []
            
            for event in events:
                start_timestamp = event.get('startTimestamp')
                home_team = event.get('homeTeam', {}).get('name', 'Ev Sahibi')
                away_team = event.get('awayTeam', {}).get('name', 'Deplasman')
                tournament = event.get('tournament', {}).get('name', 'Genel Lig')
                
                match_time = "Canlı"
                if start_timestamp:
                    match_utc = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
                    match_tsi = match_utc + timedelta(hours=3)
                    match_time = match_tsi.strftime("%H:%M")

                matches_list.append({
                    "league": tournament,
                    "home": home_team,
                    "away": away_team,
                    "time": match_time,
                    "prediction": "IY 0.5 ÜST"
                })
    except Exception as e:
        print(f"Hata: {e}")

    return {"status": "success", "data": matches_list}
