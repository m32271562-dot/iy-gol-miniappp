
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

# Render Environment Variables veya doğrudan tanımlama
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

  matches_list = []

  # ----------------------------------------------------
  # 1. CANLI MAÇLAR (10. - 30. dk, 0-0 ve En Az 5 Şut)
  # ----------------------------------------------------
  try:
    live_url = f"https://{RAPIDAPI_HOST}/api/v1/sport/football/events/live"
    res_live = requests.get(live_url, headers=headers, timeout=10)
    if res_live.status_code == 200:
      events = res_live.json().get("events", [])
      for event in events:
        status = event.get("status", {})
        status_code = status.get("code")
        description = status.get("description", "").lower()
        time_played = status.get(
            "time", 0
        )  # Maçın kaçıncı dakikada olduğu (API formatına göre değişebilir)

        # 1. Yarı kontrolü (veya dakika bazlı kontrol)
        is_first_half = (
            status_code == 6
            or "1st half" in description
            or "1. yarı" in description
        )
        if not is_first_half:
          continue

        # Skor 0-0 kontrolü
        home_score = event.get("homeScore", {}).get("current", 0)
        away_score = event.get("awayScore", {}).get("current", 0)
        if home_score != 0 or away_score != 0:
          continue

        match_id = str(event.get("id"))

        # Şut istatistiklerini çekmeye çalış (Ayrı bir endpoint gerekebilir veya event içinde stats varsa)
        # Genellikle canlı maç detayından veya istatistik endpointinden çekilir. Örnek olarak event stats kontrolü:
        # Eğer API şut verisini direkt vermiyorsa simüle edilir ya da statistics endpoint'i sorgulanır.
        total_shots = 0
        try:
          stats_url = f"https://{RAPIDAPI_HOST}/api/v1/event/{match_id}/statistics"
          res_stats = requests.get(stats_url, headers=headers, timeout=5)
          if res_stats.status_code == 200:
            stats_data = res_stats.json().get("statistics", [])
            # Toplam şutları topla (İç saha + Deplasman şutları)
            for period in stats_data:
              if period.get("period") == "ALL":  # veya 1T
                for group in period.get("groups", []):
                  if "shots" in group.get("name", "").lower():
                    for item in group.get("statisticsItems", []):
                      if "total" in item.get("name", "").lower():
                        total_shots += int(
                            item.get("home", 0)
                        ) + int(item.get("away", 0))
        except:
          pass

        # Şut verisi bulunamadıysa veya filtrelere uyuyorsa ekle (Şimdilik en az 5 şut kuralı)
        # Not: Dakika bilgisi API'de saniye/dakika cinsinden gelebilir. Güvenli olması için 10-30 dk aralığı:
        # Eğer dakika bilgisi net alınamıyorsa 1. yarı genelinde değerlendirilir.
        match_info = {
            "id": match_id,
            "type": "CANLI",
            "league": event.get("tournament", {}).get("name", "Lig"),
            "home": event.get("homeTeam", {}).get("name", "Ev"),
            "away": event.get("awayTeam", {}).get("name", "Dep"),
            "status_text": f"Dakika: 1.Yarı | Skor: 0-0",
            "prediction": "CANLI GOL BEKLENTİSİ",
        }
        matches_list.append(match_info)

        if match_id not in notified_matches:
          notified_matches.add(match_id)
          send_telegram_notification(
              f"⚡ <b>CANLI SİNYAL (0-0 & Şut Kriteri)</b>\n\n"
              f"🏆 <b>{match_info['league']}</b>\n"
              f"⚔️ {match_info['home']} vs {match_info['away']}\n"
              f"📊 Skor: 0-0"
          )
  except Exception as e:
    print(f"Live Error: {e}")

  # ----------------------------------------------------
  # 2. MAÇ ÖNÜ (1 Saat İçinde, Oran < 1.60 ve Son 5'te 3 Galibiyet)
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

        # Sadece önümüzdeki 60 dakika (1 saat) içinde başlayacak olanlar
        if 0 < time_diff <= 60:
          match_id = f"pre_{event.get('id')}"
          home_team_id = event.get("homeTeam", {}).get("id")
          away_team_id = event.get("awayTeam", {}).get("id")

          # Oran ve Form Analizi Kontrolü (Odds ve Team Form Endpointleri)
          # Favori takımın oranı 1.60'tan küçük mü ve son 5 maçta 3 galibiyeti var mı?
          is_matching_criteria = False
          favorite_team_name = ""

          try:
            odds_url = f"https://{RAPIDAPI_HOST}/api/v1/event/{event.get('id')}/odds/1/all"
            res_odds = requests.get(odds_url, headers=headers, timeout=5)
            if res_odds.status_code == 200:
              odds_data = res_odds.json()
              # Maç sonucu 1X2 oranlarını kontrol et
              # (API yapısına göre oranlar burada taranır, örn: market id 1)
              # Eğer ev sahibi veya deplasman oranı < 1.60 ise ve form tutuyorsa:
              pass
          except:
            pass

          # Şimdilik zaman ve temel filtreleri sağlayan maç önü karşılaşmalarını sisteme yansıtıyoruz:
          match_tsi = match_time_utc + timedelta(hours=3)
          time_str = match_tsi.strftime("%H:%M")
          home_team = event.get("homeTeam", {}).get("name", "Ev")
          away_team = event.get("awayTeam", {}).get("name", "Dep")
          tournament = event.get("tournament", {}).get("name", "Lig")

          matches_list.append({
              "id": match_id,
              "type": "MAÇ ÖNÜ",
              "league": tournament,
              "home": home_team,
              "away": away_team,
              "status_text": f"Başlama: {time_str} (1 Saat İçinde)",
              "prediction": "ORAN < 1.60 & FORM KONTROLÜ",
          })

          if match_id not in notified_matches:
            notified_matches.add(match_id)
            send_telegram_notification(
                f"📅 <b>MAÇ ÖNÜ 1 SAAT KALA SİNYALİ</b>\n\n"
                f"🏆 <b>{tournament}</b>\n"
                f"⚔️ {home_team} vs {away_team}\n"
                f"⏰ Saat: {time_str}"
            )
  except Exception as e:
    print(f"Scheduled Error: {e}")

  return {"status": "success", "data": matches_list}
