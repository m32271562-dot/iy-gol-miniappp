import asyncio
import logging
from datetime import datetime, timedelta
import zoneinfo  # Saat dilimi sabitleme için
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Telegram Bot Yapılandırması
BOT_TOKEN = "8720695015:AAFe7b-GCn1hi95NILLGH16Cqp7ZqlAlO5Y"
CHAT_ID = "6955637394"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Sistem Hafızası ve İstatistikler
TRACKED_SIGNALS = {}
STATS = {
    "total_received": 0,
    "won": 0,
    "lost": 0,
    "pending": 0,
    "start_time": datetime.now()
}

def get_tr_now():
    """Render sunucusunu Türkiye Saatine (UTC+3 / Istanbul) sabitler."""
    try:
        return datetime.now(zoneinfo.ZoneInfo("Europe/Istanbul"))
    except Exception:
        # ZoneInfo desteği yoksa UTC+3 manuel eklenir
        return datetime.utcnow() + timedelta(hours=3)

def parse_signal_data(sig):
    sig_id = str(sig.get("id") or sig.get("external_id") or "")
    
    home = sig.get("home_team") or sig.get("home") or sig.get("team_home") or ""
    away = sig.get("away_team") or sig.get("away") or sig.get("team_away") or ""
    if home and away:
        match_name = f"{home} vs {away}"
    else:
        match_name = sig.get("match_name") or sig.get("match") or sig.get("teams") or "Bilinmiyor"

    prediction = (
        sig.get("prediction") or 
        sig.get("pick") or 
        sig.get("tip") or 
        sig.get("bet") or 
        sig.get("signal_type") or 
        "ca"
    )

    odd = sig.get("odd") or sig.get("odds") or sig.get("rate") or "1.50"
    league = sig.get("league") or sig.get("league_name") or "VIP Lig"
    minute = sig.get("minute") or sig.get("time") or sig.get("match_time") or "Canlı"
    score = sig.get("score") or sig.get("result_score") or sig.get("ft_score") or "0-0"
    status = str(sig.get("status") or sig.get("state") or "pending").lower()

    return {
        "id": sig_id,
        "match_name": match_name,
        "prediction": prediction,
        "odd": odd,
        "league": league,
        "minute": minute,
        "score": score,
        "status": status,
        "raw": sig
    }

async def fetch_signals():
    # Türkiye saatine göre güncel tarih belirleniyor (Tam 24 Ağustos 2026 saati)
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
                            parsed = parse_signal_data(sig)
                            if parsed["id"] and parsed["id"] not in seen_ids:
                                seen_ids.add(parsed["id"])
                                all_fetched_signals.append(parsed)
                except Exception as e:
                    logging.error(f"API İstek Hatası: {e}")

    return all_fetched_signals

async def track_signals_loop():
    is_first_run = True

    while True:
        try:
            signals = await fetch_signals()

            if is_first_run:
                for sig in signals:
                    TRACKED_SIGNALS[sig["id"]] = sig
                    if sig["status"] in ["kazandi", "won"]:
                        STATS["won"] += 1
                    elif sig["status"] in ["kaybetti", "lost"]:
                        STATS["lost"] += 1
                    else:
                        STATS["pending"] += 1
                    STATS["total_received"] += 1
                
                is_first_run = False
                logging.info(f"Sistem Isındı: {len(TRACKED_SIGNALS)} eski sinyal hafızaya alındı, canlı takip başladı.")
            else:
                for sig in signals:
                    sig_id = sig["id"]
                    status = sig["status"]

                    if sig_id not in TRACKED_SIGNALS:
                        TRACKED_SIGNALS[sig_id] = sig
                        STATS["total_received"] += 1
                        STATS["pending"] += 1

                        text = (
                            f"🚨 <b>YENİ VIP SİNYAL DÜŞTÜ!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🏆 <b>Lig:</b> {sig['league']}\n"
                            f"⚽ <b>Maç:</b> {sig['match_name']}\n"
                            f"⏱ <b>Dakika:</b> {sig['minute']}\n"
                            f"📌 <b>Tahmin:</b> <code>{sig['prediction']}</code>\n"
                            f"📈 <b>Oran:</b> {sig['odd']}\n"
                            f"📊 <b>Mevcut Skor:</b> {sig['score']}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"🔔 <i>Sinyal takibe alındı, sonuçlandığında bildirilecek.</i>"
                        )
                        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

                    else:
                        old_status = TRACKED_SIGNALS[sig_id]["status"]
                        if old_status != status and status in ["kazandi", "kaybetti", "won", "lost"]:
                            TRACKED_SIGNALS[sig_id]["status"] = status
                            
                            if STATS["pending"] > 0:
                                STATS["pending"] -= 1

                            if status in ["kazandi", "won"]:
                                STATS["won"] += 1
                                icon = "✅"
                                title_status = "KAZANDI"
                            else:
                                STATS["lost"] += 1
                                icon = "❌"
                                title_status = "KAYBETTİ"

                            text = (
                                f"🔔 <b>SİNYAL SONUÇLANDI!</b> {icon}\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"⚽ <b>Maç:</b> {sig['match_name']}\n"
                                f"📌 <b>Tahmin:</b> <code>{sig['prediction']}</code>\n"
                                f"🎯 <b>Sonuç:</b> <b>{title_status}</b>\n"
                                f"📊 <b>Maç Sonu Skor:</b> {sig['score']}\n"
                                f"━━━━━━━━━━━━━━━━━━━━"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

        except Exception as e:
            logging.error(f"Ana Takip Döngüsü Hatası: {e}")
            
        await asyncio.sleep(25)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        f"🤖 <b>VIP Bet Signal Botu Aktif!</b>\n\n"
        f"Sistem 7/24 betsignalhub.com panelini tarıyor.\n"
        f"Yeni sinyaller ve maç sonuçları anında buraya iletilecektir.\n\n"
        f"<b>Komutlar:</b>\n"
        f"• /durum - Sistem istatistikleri ve başarı oranı\n"
        f"• /sinyaller - Son takip edilen sinyal listesi"
    )
    await message.answer(welcome_text, parse_mode="HTML")

@dp.message(Command("durum"))
async def cmd_durum(message: types.Message):
    total = STATS["total_received"]
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
    if not TRACKED_SIGNALS:
        await message.answer("⚠️ Henüz kayıtlı aktif sinyal bulunmuyor.")
        return
    
    text = "📋 <b>SON TAKİP EDİLEN 10 SİNYAL</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    recent_signals = list(TRACKED_SIGNALS.values())[-10:]
    
    for sig in reversed(recent_signals):
        st = sig['status']
        icon = "⏳" if st in ["pending", "bekliyor"] else ("✅" if st in ["kazandi", "won"] else "❌")
        text += f"{icon} <b>{sig['match_name']}</b>\n┗ Tahmin: <code>{sig['prediction']}</code> | Durum: {st.upper()}\n\n"
    
    await message.answer(text, parse_mode="HTML")

async def main():
    asyncio.create_task(track_signals_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
