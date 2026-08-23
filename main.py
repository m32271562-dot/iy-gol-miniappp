import asyncio
import logging
from datetime import datetime, timedelta
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

async def fetch_signals():
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
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
                            sig_id = str(sig.get("external_id") or sig.get("id"))
                            if sig_id and sig_id not in seen_ids:
                                seen_ids.add(sig_id)
                                all_fetched_signals.append(sig)
                except Exception as e:
                    logging.error(f"API Hatasi ({url}): {e}")

    return all_fetched_signals

async def track_signals_loop():
    while True:
        try:
            signals = await fetch_signals()
            for sig in signals:
                sig_id = str(sig.get("external_id") or sig.get("id"))
                status = str(sig.get("status") or sig.get("state") or "Bekliyor")
                
                # API'den gelebilecek tüm alternatif parametre adları
                match_name = (
                    sig.get("match_name") or 
                    sig.get("match") or 
                    sig.get("teams") or 
                    sig.get("home_team") or 
                    sig.get("title") or 
                    "Bilinmiyor"
                )
                
                prediction = (
                    sig.get("prediction") or 
                    sig.get("pick") or 
                    sig.get("tip") or 
                    sig.get("bet") or 
                    sig.get("signal_type") or 
                    "Bilinmiyor"
                )
                
                score = sig.get("score") or sig.get("result_score") or sig.get("ft_score") or "N/A"

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
                    old_status = str(TRACKED_SIGNALS[sig_id].get("status"))
                    if old_status != status and status.lower() in ["kazandi", "kaybetti", "won", "lost"]:
                        TRACKED_SIGNALS[sig_id]["status"] = status
                        icon = "✅" if status.lower() in ["kazandi", "won"] else "❌"
                        text = (
                            f"🔔 <b>SİNYAL SONUÇLANDI!</b>\n\n"
                            f"⚽ {match_name}\n"
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
    await message.answer("🤖 Bot aktif ve canlı sinyalleri takip ediyor!")

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
        m = sig.get("match_name") or sig.get("match") or "Bilinmiyor"
        p = sig.get("prediction") or sig.get("pick") or "Bilinmiyor"
        s = sig.get("status") or "Bekliyor"
        text += f"• {m} - {p} ({s})\n"
    
    await message.answer(text, parse_mode="HTML")

async def main():
    asyncio.create_task(track_signals_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
