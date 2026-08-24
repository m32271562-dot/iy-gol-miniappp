import asyncio
import logging
from datetime import datetime, timedelta
import zoneinfo
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# YENİ TOKENİ BURAYA YAPIŞTIR
BOT_TOKEN = "8720695015:AAEznlCH2vfagkIXihP-2I8OoP7eixNYP2M"
CHAT_ID = "6955637394"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TRACKED_SIGNALS = {}
NOTIFIED_SIGNALS = set()

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

def get_league_name(sig):
    league = sig.get("league") or sig.get("league_name") or sig.get("tournament") or sig.get("category") or sig.get("country")
    if league and str(league) != "None":
        return str(league)
    return "Genel Lig"

def get_match_type_tag(sig):
    stype = str(sig.get("type") or sig.get("signal_type") or sig.get("market") or "").lower()
    minute = str(sig.get("minute") or sig.get("min") or "")
    
    if "iy" in stype or "ht" in stype or "half" in stype or "ilk yarı" in stype:
        return "[İ.Y]"
    elif minute and minute.isdigit() and int(minute) <= 45:
        return "[İ.Y]"
    return "[CM]"

def get_prediction_value(sig):
    p = sig.get("prediction") or sig.get("pick") or sig.get("tip") or sig.get("bet") or sig.get("signal_type")
    if p and str(p) != "None":
        return str(p)
    return "ca"

def generate_sig_id(sig):
    raw_id = sig.get("id") or sig.get("external_id")
    if raw_id and str(raw_id) != "None":
        return str(raw_id)
    m = get_match_title(sig)
    p = get_prediction_value(sig)
    return f"{m}_{p}".replace(" ", "_")

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
                            sig_id = generate_sig_id(sig)
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
            now_dt = get_tr_now().replace(tzinfo=None)

            if is_first_run:
                for sig in signals:
                    sig_id = generate_sig_id(sig)
                    sig["_added_at"] = now_dt
                    TRACKED_SIGNALS[sig_id] = sig
                    NOTIFIED_SIGNALS.add(sig_id)
                    
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
                    sig_id = generate_sig_id(sig)
                    match_name = get_match_title(sig)
                    league = get_league_name(sig)
                    type_tag = get_match_type_tag(sig)
                    prediction = get_prediction_value(sig)
                    status = str(sig.get("status") or "pending").lower()
                    score = sig.get("score") or "0-0"

                    if sig_id not in TRACKED_SIGNALS:
                        sig["_added_at"] = now_dt
                        TRACKED_SIGNALS[sig_id] = sig
                        STATS["total"] += 1
                        STATS["pending"] += 1

                        if sig_id not in NOTIFIED_SIGNALS:
                            NOTIFIED_SIGNALS.add(sig_id)
                            text = (
                                f"🚨 <b>YENİ SİNYAL! {type_tag}</b>\n\n"
                                f"🏆 <b>Lig:</b> {league}\n"
                                f"⚽ <b>Maç:</b> {match_name}\n"
                                f"📌 <b>Tahmin:</b> {prediction}\n"
                                f"📊 <b>Durum:</b> Bekleniyor"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

                    else:
                        old_status = str(TRACKED_SIGNALS[sig_id].get("status") or "").lower()
                        
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

                            result_key = f"{sig_id}_{status}"
                            if result_key not in NOTIFIED_SIGNALS:
                                NOTIFIED_SIGNALS.add(result_key)
                                text = (
                                    f"🔔 <b>SİNYAL SONUÇLANDI! {type_tag}</b>\n\n"
                                    f"🏆 <b>Lig:</b> {league}\n"
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
    tr_now = get_tr_now().replace(tzinfo=None)
    cutoff_time = tr_now - timedelta(hours=4)

    valid_pending_signals = []
    
    for sig in TRACKED_SIGNALS.values():
        status = str(sig.get("status") or "pending").lower()
        if status in ["pending", "bekliyor"]:
            added_at = sig.get("_added_at")
            if added_at is None or added_at >= cutoff_time:
                valid_pending_signals.append(sig)
    
    if not valid_pending_signals:
        await message.answer("⏳ <b>Şu anda bekleyen aktif bir sinyal bulunmuyor.</b>", parse_mode="HTML")
        return
    
    text = f"⏳ <b>BEKLEYEN SİNYALLER ({len(valid_pending_signals)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for sig in valid_pending_signals:
        m = get_match_title(sig)
        p = get_prediction_value(sig)
        l = get_league_name(sig)
        tag = get_match_type_tag(sig)
        text += f"⏳ {tag} <b>{m}</b>\n🏆 Lig: {l}\n┗ Tahmin: {p} | Durum: BEKLENİYOR\n\n"
    
    await message.answer(text, parse_mode="HTML")

async def main():
    asyncio.create_task(track_signals_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
