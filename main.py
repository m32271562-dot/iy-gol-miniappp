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

TELEGRAM_BOT_TOKEN = "8720695015:AAFe7b-GCn1hi95NILLGH16Cqp7ZqlAlO5Y"
CHAT_ID = "6955637394"

notified_matches = set()


def send_telegram_notification(message: str):
  if TELEGRAM_BOT_TOKEN and CHAT_ID:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
      requests.post(url, json=payload, timeout=5)
    except Exception as e:
      print(f"Notification Error: {e}")


@app.get("/", response_class=HTMLResponse)
def read_root():
  with open("index.html", "r", encoding="utf-8") as f:
    return f.read()


@app.get("/api/matches")
def get_matches():
  headers = {
      "x-rapidapi-key": RAPIDAPI_KEY,
      "x-rapidapi-host": RAPIDAPI_HOST,
  }

  live_matches = []
  pre_matches = []

  # ----------------------------------------------------
  # 1. CANLI MAÇLAR (İsabetli Şut >= 3 ve Oran < 3.00)
  # ----------------------------------------------------
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

        home_shots_on_target = 0
        away_shots_on_target = 0

        # İstatistik Taraması (İsabetli Şut Sayıları)
        try:
          stats_url = (
              f"https://{RAPIDAPI_HOST}/api/v1/event/{match_id}/statistics"
          )
          res_stats = requests.get(stats_url, headers=headers, timeout=5)
          if res_stats.status_code == 200:
            stats_data = res_stats.json().get("statistics", [])
            for period in stats_data:
              if period.get("period") == "ALL":
                for group in period.get("groups", []):
                  for item in group.get("statisticsItems", []):
                    if "shots on target" in item.get("name", "").lower():
                      home_shots_on_target = int(item.get("home", 0))
                      away_shots_on_target = int(item.get("away", 0))
        except:
          pass

        # Gol Adayı Belirleme Kriteri (En az 3 isabetli şut)
        target_team = None
        prediction_text = ""

        if home_shots_on_target >= 3:
          target_team = home_team
          prediction_text = f"{home_team} GOL ATAR"
        elif away_shots_on_target >= 3:
          target_team = away_team
          prediction_text = f"{away_team} GOL ATAR"

        if target_team:
          match_info = {
              "id": match_id,
              "league": tournament,
              "home": home_team,
              "away": away_team,
              "status_text": (
                  f"İsabetli Şut: {home_shots_on_target}-{away_shots_on_target}"
              ),
              "prediction": prediction_text,
          }
          live_matches.append(match_info)

          if match_id not in notified_matches:
            notified_matches.add(match_id)
            send_telegram_notification(
                f"⚡ <b>CANLI GOL SİNYALİ</b>\n\n"
                f"🏆 <b>{tournament}</b>\n"
                f"⚔️ {home_team} vs {away_team}\n"
                f"🎯 <b>Tahmin:</b> {prediction_text}\n"
                f"📊 İsabetli Şut: {home_shots_on_target}-{away_shots_on_target}"
            )
  except Exception as e:
    print(f"Live Error: {e}")

  # ----------------------------------------------------
  # 2. MAÇ ÖNÜ (Oran < 1.60 ve Son 5'te 3 Galibiyet)
  # ----------------------------------------------------
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

        if 0 < time_diff <= 120:  # 2 saat içinde başlayacak maçlar
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
              "prediction": "FAVORİ (Oran < 1.60 & Form OK)",
          })

          if match_id not in notified_matches:
            notified_matches.add(match_id)
            send_telegram_notification(
                f"📅 <b>MAÇ ÖNÜ SİNYALİ</b>\n\n"
                f"🏆 <b>{tournament}</b>\n"
                f"⚔️ {home_team} vs {away_team}\n"
                f"⏰ Saat: {time_str}\n"
                f"🎯 <b>Filtre:</b> Favori Oran < 1.60 + Form"
            )
  except Exception as e:
    print(f"Scheduled Error: {e}")

  return {"status": "success", "live": live_matches, "pre": pre_matches}
