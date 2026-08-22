from datetime import datetime, timedelta, timezone
import os
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


def get_team_stats(team_id: int, headers: dict):
  """Takımın kazanma yüzdesi ve son 5 maçtaki galibiyet sayısını hesaplar."""
  if not team_id:
    return {"win_rate": 0, "last_5_wins": 0}

  try:
    url = f"https://{RAPIDAPI_HOST}/api/v1/team/{team_id}/performance"
    res = requests.get(url, headers=headers, timeout=4)
    if res.status_code == 200:
      data = res.json()
      wins = data.get("wins", 0)
      total = data.get("totalMatches", 5)
      win_rate = (wins / total * 100) if total > 0 else 0

      # Son 5 maç galibiyeti
      last_5_wins = data.get("last5Wins", wins if total <= 5 else 0)
      return {"win_rate": win_rate, "last_5_wins": last_5_wins}
  except Exception as e:
    print(f"Team Stats Error ({team_id}): {e}")

  return {"win_rate": 0, "last_5_wins": 0}


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
  # 1. CANLI MAÇLAR
  # Kriter: En az 5 Şut + En az 3 İsabetli Şut + Kazanma Yüzdesi >= %40
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
        home_id = event.get("homeTeam", {}).get("id")
        away_id = event.get("awayTeam", {}).get("id")
        tournament = event.get("tournament", {}).get("name", "Lig")

        home_total_shots = 0
        home_shots_on_target = 0
        away_total_shots = 0
        away_shots_on_target = 0

        # Şut istatistiklerini çek
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
                    name_lower = item.get("name", "").lower()
                    if "shots on target" in name_lower:
                      home_shots_on_target = int(item.get("home", 0))
                      away_shots_on_target = int(item.get("away", 0))
                    elif "total shots" in name_lower or "shots" == name_lower:
                      home_total_shots = int(item.get("home", 0))
                      away_total_shots = int(item.get("away", 0))
        except:
          pass

        # Ev Sahibi Kontrolü (Toplam Şut >= 5, İsabetli >= 3)
        home_stats = (
            get_team_stats(home_id, headers) if home_id else {"win_rate": 50}
        )
        away_stats = (
            get_team_stats(away_id, headers) if away_id else {"win_rate": 50}
        )

        prediction_text = ""
        target_team = ""
        shots_info = ""

        if (
            home_total_shots >= 5
            and home_shots_on_target >= 3
            and home_stats["win_rate"] >= 40
        ):
          target_team = home_team
          prediction_text = f"{home_team} GOL ATAR"
          shots_info = f"Şut: {home_total_shots} (İsabet: {home_shots_on_target}) | Win Rate: %{int(home_stats['win_rate'])}"
        elif (
            away_total_shots >= 5
            and away_shots_on_target >= 3
            and away_stats["win_rate"] >= 40
        ):
          target_team = away_team
          prediction_text = f"{away_team} GOL ATAR"
          shots_info = f"Şut: {away_total_shots} (İsabet: {away_shots_on_target}) | Win Rate: %{int(away_stats['win_rate'])}"

        if prediction_text:
          live_matches.append({
              "id": match_id,
              "league": tournament,
              "home": home_team,
              "away": away_team,
              "status_text": shots_info,
              "prediction": prediction_text,
          })

          if match_id not in notified_matches:
            notified_matches.add(match_id)
            send_telegram_notification(
                f"⚡ <b>CANLI GOL SİNYALİ</b>\n\n"
                f"🏆 <b>{tournament}</b>\n"
                f"⚔️ {home_team} vs {away_team}\n"
                f"🎯 <b>Tahmin:</b> {prediction_text}\n"
                f"📊 <b>Baskı:</b> {shots_info}"
            )
  except Exception as e:
    print(f"Live Error: {e}")

  # ----------------------------------------------------
  # 2. MAÇ ÖNÜ
  # Kriter: Kazanma Yüzdesi >= %70 VE Son 5 Maçın En Az 3'ü Galibiyet
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
          home_id = event.get("homeTeam", {}).get("id")
          away_id = event.get("awayTeam", {}).get("id")
          home_team = event.get("homeTeam", {}).get("name", "Ev")
          away_team = event.get("awayTeam", {}).get("name", "Dep")
          tournament = event.get("tournament", {}).get("name", "Lig")

          favorite_team = None
          win_rate = 0
          last_5_wins = 0

          # İki takımı da tara
          for tid, tname in [(home_id, home_team), (away_id, away_team)]:
            if not tid:
              continue
            stats = get_team_stats(tid, headers)
            # %70+ kazanma VE son 5 maçın en az 3'ü galibiyet
            if stats["win_rate"] >= 70 and stats["last_5_wins"] >= 3:
              favorite_team = tname
              win_rate = int(stats["win_rate"])
              last_5_wins = stats["last_5_wins"]
              break

          if favorite_team:
            match_id = f"pre_{event.get('id')}"
            match_tsi = match_time_utc + timedelta(hours=3)
            time_str = match_tsi.strftime("%H:%M")

            pre_matches.append({
                "id": match_id,
                "league": tournament,
                "home": home_team,
                "away": away_team,
                "status_text": f"Saat: {time_str}",
                "prediction": (
                    f"{favorite_team} (%{win_rate} Win | Son 5'te {last_5_wins}W)"
                ),
            })

            if match_id not in notified_matches:
              notified_matches.add(match_id)
              send_telegram_notification(
                  f"📅 <b>MAÇ ÖNÜ FIRSAT SİNYALİ</b>\n\n"
                  f"🏆 <b>{tournament}</b>\n"
                  f"⚔️ {home_team} vs {away_team}\n"
                  f"⏰ Saat: {time_str}\n"
                  f"🔥 <b>Favori:</b> {favorite_team}\n"
                  f"📈 <b>Kazanma Oranı:</b> %{win_rate}\n"
                  f"✅ <b>Son 5 Maç Galibiyeti:</b> {last_5_wins}/5"
              )
  except Exception as e:
    print(f"Scheduled Error: {e}")

  return {"status": "success", "live": live_matches, "pre": pre_matches}
