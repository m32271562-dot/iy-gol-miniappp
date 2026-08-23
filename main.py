import asyncio
import logging
from datetime import datetime, timedelta
import zoneinfo
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Telegram Bot Yapılandırması
BOT_TOKEN = "8720695015:AAFe7b-GCn1hi95NILLGH16Cqp7ZqlAlO5Y"
CHAT_ID = "6955637394"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TRACKED_SIGNALS = {}

def get_tr_now():
    try:
        return datetime.now(zoneinfo.ZoneInfo("Europe/Istanbul"))
    except Exception:
        return datetime.utcnow() + timedelta(hours=3)

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
                            sig_id = str(sig.get("id"))
                            if sig_id and sig_id not in seen_ids:
                                seen_ids.add(sig_id)
                                all_fetched_signals.append(sig)
                except Exception as e:
                    logging.error(f"API Hatasi ({url}): {e}")

    return all_fetched_signals

async def track_signals_loop():
    is_first_run = True  # Eski maç spamını engelleyen kilit

    while True:
        try:
            signals = await fetch_signals()

            if is_first_run:
                # İlk çalıştırmada mevcut tüm sinyalleri hafızaya al, Telegram'a mesaj ATMA!
                for sig in signals:
                    sig_id = str(sig.get("id"))
                    TRACKED_SIGNALS[sig_id] = sig
                is_first_run = False
                logging.info(f"Sistem hazır: {len(TRACKED_SIGNALS)} eski maç hafızaya alındı.")
            else:
                # Canlı Takip Modu
                for sig in signals:
                    sig_id = str(sig.get("id"))
                    
                    home = sig.get("home_team", "")
                    away = sig.get("away_team", "")
                    match_name = f"{home} vs {away}" if home and away else (sig.get("match_name") or "Bilinmiyor")
                    
                    prediction = sig.get("prediction") or sig.get("pick") or sig.get("tip") or "ca"
                    status = sig.get("status", "pending")
                    score = sig.get("score", "0-0")

                    if sig_id not in TRACKED_SIGNALS:
                        TRACKED_SIGNALS[sig_id] = sig
                        text = (
                            f"🚨 <b>YENİ SİNYAL!</b>\n\n"
                            f"⚽ <b>Maç:</b> {match_name}\n"
                            f"📌 <b>Tahmin:</b> {prediction}\n"
                            f"📊 <b>Durum:</b> {status}"
                        )
                        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
                    else:
                        old_status = TRACKED_SIGNALS[sig_id].get("status")
                        if old_status != status and str(status).lower() in ["kazandi", "kaybetti", "won", "lost"]:
                            TRACKED_SIGNALS[sig_id]["status"] = status
                            icon = "✅" if str(status).lower() in ["kazandi", "won"] else "❌"
                            text = (
                                f"🔔 <b>SİNYAL SONUÇLANDI!</b>\n\n"
                                f"⚽ <b>Maç:</b> {match_name}\n"
                                f"📌 <b>Tahmin:</b> {prediction}\n"
                                f"🎯 <b>Sonuç:</b> {icon} {status}\n"
                                f"📊 <b>Skor:</b> {score}"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Loop hatasi: {e}")
            
        await asyncio.sleep(30)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    start_text = (
        "✅ <b>Bot Başarıyla Bağlandı!</b>\n\n"
        "Sistem arka planda canlı olarak çalışıyor. Yeni sinyaller veya sonuçlar geldikçe buraya düşecektir.\n\n"
        "📌 /durum - Günün başarı yüzdesi ve istatistikler\n"
        "📌 /sinyaller - Şu an bekleyen sinyaller"
    )
    await message.answer(start_text, parse_mode="HTML")

@dp.message(Command("durum"))
async def cmd_durum(message: types.Message):
    total = len(TRACKED_SIGNALS)
    await message.answer(f"📊 <b>Sistem Durumu</b>\n\nTakip Edilen Toplam Sinyal: {total}", parse_mode="HTML")

@dp.message(Command("sinyaller"))
async def cmd_sinyaller(message: types.Message):
    if not TRACKED_SIGNALS:
        await message.answer("Henüz kaydedilmiş aktif sinyal bulunmuyor.")
        return
    
    text = "📋 <b>Son Sinyaller:</b>\n\n"
    for sig in list(TRACKED_SIGNALS.values())[-10:]:
        home = sig.get("home_team", "")
        away = sig.get("away_team", "")
        m = f"{home} vs {away}" if home and away else (sig.get("match_name") or "Bilinmiyor")
        p = sig.get("prediction") or sig.get("pick") or sig.get("tip") or "ca"
        s = sig.get("status") or "pending"
        text += f"• {m} - {p} ({s})\n"
    
    await message.answer(text, parse_mode="HTML")

async def main():
    asyncio.create_task(track_signals_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
