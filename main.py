import asyncio
import logging
from datetime import datetime, timedelta
import zoneinfo
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = "8720695015:AAFPqdMU_O9mj4AhFZ7mlMqjIx5OBfFnHl0"
CHAT_ID = "6955637394"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TRACKED_SIGNALS = {}
STATS = {
    "total": 0,
    "won": 0,
    "lost": 0,
    "pending": 0,
    "start_time": datetime.now()
}

def get_tr_now():
    try:
        return datetime.now(zoneinfo.ZoneInfo("Europe/Istanbul"))
    except Exception:
        return datetime.utcnow() + timedelta(hours=3)

def get_match_title(sig):
    home = sig.get("home_team") or sig.get("home") or sig.get("team_home") or ""
    away = sig.get("away_team") or sig.get("away") or sig.get("team_away") or ""
    if home and away:
        return f"{home} vs {away}"
    
    name = sig.get("match_name") or sig.get("match") or sig.get("teams") or sig.get("title")
    if name and str(name) != "None":
        return str(name)
    return "Bilinmiyor"

def get_prediction_value(sig):
    p = sig.get("prediction") or sig.get("pick") or sig.get("tip") or sig.get("bet") or sig.get("signal_type")
    if p and str(p) != "None":
        return str(p)
    return "ca"

async def fetch_signals():
    tr_now = get_tr_now()
    today_str = tr_now.strftime("%Y-%m-%d")
    yesterday_str = (tr_now - timedelta(days=1)).strftime("%Y-%m-%d")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://betsignalhub.com/dashboard",
        "Accept": "application/json"
    }

    all_fetched_signals = []
    seen_ids = set()

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for page in range(1, 6):
            urls = [
                f"https://betsignalhub.com/api/signals.php?date={today_str}&page={page}&limit=50",
                f"https://betsignalhub.com/api/signals.php?date={yesterday_str}&page={page}&limit=50",
                f"https://betsignalhub.com/api/signals.php?page={page}&limit=50"
            ]
            
            for url in urls:
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        signals_list = data.get("signals", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                        
                        if not signals_list:
                            continue

                        for sig in signals_list:
                            sig_id = str(sig.get("id") or sig.get("external_id") or "")
                            if sig_id and sig_id not in seen_ids:
                                seen_ids.add(sig_id)
                                all_fetched_signals.append(sig)
                except Exception as e:
                    logging.error(f"API Hatasi: {e}")

    return all_fetched_signals

async def track_signals_loop():
    is_first_run = True

    while True:
        try:
            signals = await fetch_signals()

            if is_first_run:
                for sig in signals:
                    sig_id = str(sig.get("id") or sig.get("external_id"))
                    TRACKED_SIGNALS[sig_id] = sig
                    
                    st = str(sig.get("status") or "").lower()
                    if st in ["kazandi", "won"]:
                        STATS["won"] += 1
                    elif st in ["kaybetti", "lost"]:
                        STATS["lost"] += 1
                    else:
                        STATS["pending"] += 1
                    STATS["total"] += 1

                is_first_run = False
            else:
                for sig in signals:
                    sig_id = str(sig.get("id") or sig.get("external_id"))
                    match_name = get_match_title(sig)
                    prediction = get_prediction_value(sig)
                    status = str(sig.get("status") or "pending").lower()
                    score = sig.get("score") or "0-0"

                    if sig_id not in TRACKED_SIGNALS:
                        TRACKED_SIGNALS[sig_id] = sig
                        STATS["total"] += 1
                        STATS["pending"] += 1

                        text = (
                            f"🚨 <b>YENİ SİNYAL!</b>\n\n"
                            f"⚽ <b>Maç:</b> {match_name}\n"
                            f"📌 <b>Tahmin:</b> {prediction}\n"
                            f"📊 <b>Durum:</b> Bekleniyor"
                        )
                        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

                    else:
                        old_status = str(TRACKED_SIGNALS[sig_id].get("status") or "").lower()
                        
                        # Durum kilitleme: Sadece bekleniyorken sonuçlanmışsa 1 defa bildirim at
                        if old_status not in ["kazandi", "kaybetti", "won", "lost"] and status in ["kazandi", "kaybetti", "won", "lost"]:
                            TRACKED_SIGNALS[sig_id]["status"] = status
                            
                            if STATS["pending"] > 0:
                                STATS["pending"] -= 1

                            if status in ["kazandi", "won"]:
                                STATS["won"] += 1
                                icon = "✅"
                                status_tr = "KAZANDI"
                            else:
                                STATS["lost"] += 1
                                icon = "❌"
                                status_tr = "KAYBETTİ"

                            text = (
                                f"🔔 <b>SİNYAL SONUÇLANDI!</b>\n\n"
                                f"⚽ <b>Maç:</b> {match_name}\n"
                                f"📌 <b>Tahmin:</b> {prediction}\n"
                                f"🎯 <b>Sonuç:</b> {icon} {status_tr}\n"
                                f"📊 <b>Skor:</b> {score}"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

        except Exception as e:
            logging.error(f"Loop hatasi: {e}")
            
        await asyncio.sleep(25)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    start_text = (
        "🤖 <b>VIP Bet Signal Botu Aktif!</b>\n\n"
        "Sistem 7/24 betsignalhub.com panelini tarıyor.\n"
        "Yeni sinyaller ve maç sonuçları anında buraya iletilecektir.\n\n"
        "<b>Komutlar:</b>\n"
        "• /durum - Sistem istatistikleri ve başarı oranı\n"
        "• /sinyaller - Aktif bekleyen sinyaller"
    )
    await message.answer(start_text, parse_mode="HTML")

@dp.message(Command("durum"))
async def cmd_durum(message: types.Message):
    total = STATS["total"]
    won = STATS["won"]
    lost = STATS["lost"]
    pending = STATS["pending"]
    
    completed = won + lost
    win_rate = round((won / completed) * 100, 1) if completed > 0 else 0.0
    uptime = str(datetime.now() - STATS["start_time"]).split('.')[0]

    status_text = (
        f"📊 <b>SİSTEM DÜZEYİ VE İSTATİSTİKLER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>Bot Durumu:</b> Aktif (Canlı)\n"
        f"⏱ <b>Çalışma Süresi:</b> {uptime}\n\n"
        f"🎯 <b>Toplam Sinyal:</b> {total}\n"
        f"⏳ <b>Bekleyen Maçlar:</b> {pending}\n"
        f"✅ <b>Kazanan Sinyal:</b> {won}\n"
        f"❌ <b>Kaybeden Sinyal:</b> {lost}\n"
        f"📈 <b>Başarı Oranı:</b> %{win_rate}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(status_text, parse_mode="HTML")

@dp.message(Command("sinyaller"))
async def cmd_sinyaller(message: types.Message):
    # Sadece bekleyen (pending) sinyalleri filtrele
    pending_signals = [
        sig for sig in TRACKED_SIGNALS.values() 
        if str(sig.get("status") or "pending").lower() in ["pending", "bekliyor"]
    ]
    
    if not pending_signals:
        await message.answer("⏳ <b>Şu anda bekleyen aktif bir sinyal bulunmuyor.</b>", parse_mode="HTML")
        return
    
    text = f"⏳ <b>BEKLEYEN SİNYALLER ({len(pending_signals)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for sig in pending_signals:
        m = get_match_title(sig)
        p = get_prediction_value(sig)
        text += f"⏳ <b>{m}</b>\n┗ Tahmin: {p} | Durum: BEKLENİYOR\n\n"
    
    await message.answer(text, parse_mode="HTML")

async def main():
    asyncio.create_task(track_signals_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
