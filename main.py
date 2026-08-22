import asyncio
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests

RAPIDAPI_KEY = "1e7360ef8cmsh9fd0715929add0dp1f2784jsnb68c929b74d8"
RAPIDAPI_HOST = "sportapi7.p.rapidapi.com"

TELEGRAM_BOT_TOKEN = "8720695015:AAFe7b-GCn1hi95NILLGH16Cqp7ZqlAlO5Y"
CHAT_ID = "6955637394"

notified_matches = set()

def send_telegram_notification(message: str):
    if TELEGRAM_BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Notification Error: {e}")

def fetch_and_process():
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    
    live_matches = []
    pre_matches = []

    # 1. CANLI MAÇLAR (1. Yarı ve 0-0 Devam Eden Maçlar)
    try:
        live_url = f"https://{RAPIDAPI_HOST}/api/v1/sport/football/events/live"
        res_live = requests.get(live_url, headers=headers, timeout=10)
        if res_live.status_code == 200:
            events = res_live.json().get("events", [])
            for event in events:
                match_id = str(event.get("id"))
                home_team = event.get("homeTeam", {}).get("name", "Ev")
                away_team = event.get("awayTeam", {}).get("name", "Dep")
                tournament = event.get("tournament", {}).get("name", "Lig")
                
                status_code = event.get("status", {}).get("code")
                description = event.get("status", {}).get("description", "").lower()
                
                home_score = event.get("homeScore", {}).get("current", 0)
                away_score = event.get("awayScore", {}).get("current", 0)

                # İlk Yarı ve Skor 0-0 ise Sinyal Üret
                is_first_half = (status_code == 6 or "1st half" in description or "1. yarı" in description)
                if is_first_half and home_score == 0 and away_score == 0:
                    live_matches.append({
                        "id": match_id,
                        "league": tournament,
                        "home": home_team,
                        "away": away_team,
                        "status_text": "1. Yarı (0-0)",
                        "prediction": "İY 0.5 ÜST"
                    })

                    if match_id not in notified_matches:
                        notified_matches.add(match_id)
                        send_telegram_notification(
                            f"⚡ <b>CANLI SİNYAL (IY 0.5 ÜST)</b>\n\n"
                            f"🏆 <b>{tournament}</b>\n"
                            f"⚔️ {home_team} vs {away_team}\n"
                            f"📊 Skor: 0-0 (1. Yarı)"
                        )
    except Exception as e:
        print(f"Live Error: {e}")

    # 2. MAÇ ÖNÜ (Yaklaşan 2 Saat İçindeki Maçlar)
    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        scheduled_url = f"https://{RAPIDAPI_HOST}/api/v1/sport/football/scheduled-events/{today_str}"
        res_sched = requests.get(scheduled_url, headers=headers, timeout=10)
        
        if res_sched.status_code == 200:
            sched_events = res_sched.json().get("events", [])
            now_utc = datetime.now(timezone.utc)
            
            for event in sched_events:
                start_ts = event.get("startTimestamp")
                if not start_ts:
                    continue
                
                match_time_utc = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                time_diff = (match_time_utc - now_utc).total_seconds() / 60
                
                if 0 < time_diff <= 120:
                    match_id = f"pre_{event.get('id')}"
                    match_tsi = match_time_utc + timedelta(hours=3)
                    time_str = match_tsi.strftime("%H:%M")
                    home_team = event.get("homeTeam", {}).get("name", "Ev")
                    away_team = event.get("awayTeam", {}).get("name", "Dep")
                    tournament = event.get("tournament", {}).get("name", "Lig")

                    pre_matches.append({
                        "id": match_id,
                        "league": tournament,
                        "home": home_team,
                        "away": away_team,
                        "status_text": f"Saat: {time_str}",
                        "prediction": "MAÇ ÖNÜ SİNYALİ"
                    })

                    if match_id not in notified_matches:
                        notified_matches.add(match_id)
                        send_telegram_notification(
                            f"📅 <b>MAÇ ÖNÜ SİNYALİ</b>\n\n"
                            f"🏆 <b>{tournament}</b>\n"
                            f"⚔️ {home_team} vs {away_team}\n"
                            f"⏰ Başlama Saati: {time_str}"
                        )
    except Exception as e:
        print(f"Scheduled Error: {e}")

    return {"live": live_matches, "pre": pre_matches}

# Arka planda her 60 saniyede bir otomatik tarama yapan döngü
async def background_scanner():
    while True:
        try:
            fetch_and_process()
        except Exception as e:
            print(f"Background Scan Error: {e}")
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background_scanner())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/matches")
def get_matches():
    data = fetch_and_process()
    return {"status": "success", "live": data["live"], "pre": data["pre"]}
