import asyncio
import logging
from datetime import datetime
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = "8720695015:AAFe7b-GCn1hi95NILLGH16Cqp7ZqlAlO5Y"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Bot veritabanı (Bellek içi)
known_signals = set()
known_status = {}
subscribers = set()

async def fetch_signals():
    today_str = datetime.now().strftime("%Y-%m-%d")
    url = f"https://betsignalhub.com/api/signals.php?date={today_str}&limit=500"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://betsignalhub.com/dashboard",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("signals", [])
            else:
                logging.error(f"HTTP Hata Kodu: {response.status_code}")
        except Exception as e:
            logging.error(f"API Baglanti Hatasi: {e}")
    return []

async def track_signals_loop():
    while True:
        try:
            signals = await fetch_signals()
            
            for sig in signals:
                sig_id = str(sig.get("external_id") or sig.get("id"))
                if not sig_id:
                    continue

                status = sig.get("status", "pending")
                home = sig.get("home_team", "Ev")
                away = sig.get("away_team", "Deplasman")
                sig_type = sig.get("type", "Canlı Analiz")
                
                # İlk Kez Çalıştığında Mevcut Sinyalleri Kaydet (Spam Engelleme)
                if not known_signals and status == "pending":
                    known_signals.add(sig_id)
                    known_status[sig_id] = status
                    continue

                # Yeni Sinyal Yakalandığında
                if sig_id not in known_signals and status == "pending":
                    known_signals.add(sig_id)
                    known_status[sig_id] = status
                    
                    msg = (
                        f"🚨 <b>YENİ SİNYAL DÜŞTÜ!</b>\n\n"
                        f"⚽ <b>{home} vs {away}</b>\n"
                        f"📌 <b>Tahmin:</b> {sig_type}\n"
                        f"⏳ <b>Durum:</b> Bekliyor"
                    )
                    
                    for chat_id in list(subscribers):
                        try:
                            await bot.send_message(chat_id, msg, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Bildirim Gönderilemedi ({chat_id}): {e}")

                # Maç Sonuçlandığında (Kazandı / Kaybetti)
                elif sig_id in known_status and known_status[sig_id] == "pending" and status in ["won", "lost"]:
                    known_status[sig_id] = status
                    
                    icon = "✅ KAZANDI" if status == "won" else "❌ KAYBETTİ"
                    skor = sig.get("result_score", "")
                    skor_metni = f"\n📊 <b>Skor:</b> {skor}" if skor else ""

                    msg = (
                        f"🔔 <b>SİNYAL SONUÇLANDI!</b>\n\n"
                        f"⚽ <b>{home} vs {away}</b>\n"
                        f"📌 <b>Tahmin:</b> {sig_type}\n"
                        f"🎯 <b>Sonuç:</b> {icon}{skor_metni}"
                    )
                    
                    for chat_id in list(subscribers):
                        try:
                            await bot.send_message(chat_id, msg, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Bildirim Gönderilemedi ({chat_id}): {e}")

        except Exception as e:
            logging.error(f"Takip Döngüsü Hatası: {e}")

        await asyncio.sleep(15)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    subscribers.add(message.chat.id)
    await message.answer(
        "✅ <b>Bot Başarıyla Bağlandı!</b>\n\n"
        "Sistem arka planda canlı olarak çalışıyor. Yeni sinyaller veya sonuçlar geldikçe buraya düşecektir.\n\n"
        "📌 /durum - Günün başarı yüzdesi ve istatistikler\n"
        "📌 /sinyaller - Şu an bekleyen sinyaller",
        parse_mode="HTML"
    )

@dp.message(Command("durum"))
async def stats_cmd(message: types.Message):
    await message.answer("📊 Veriler hesaplanıyor...")
    signals = await fetch_signals()
    if not signals:
        await message.answer("⚠️ Güncel veri çekilemedi.")
        return

    won_count = sum(1 for s in signals if s.get("status") == "won")
    lost_count = sum(1 for s in signals if s.get("status") == "lost")
    pending_count = sum(1 for s in signals if s.get("status") == "pending")
    total_count = len(signals)
    resolved_count = won_count + lost_count

    win_rate = (won_count / resolved_count * 100) if resolved_count > 0 else 0.0

    msg = (
        f"📊 <b>GÜNÜN İSTATİSTİKLERİ</b>\n\n"
        f"✅ <b>Kazanan:</b> {won_count}\n"
        f"❌ <b>Kaybeden:</b> {lost_count}\n"
        f"⏳ <b>Bekleyen:</b> {pending_count}\n"
        f"📈 <b>Toplam Sinyal:</b> {total_count}\n"
        f"🔥 <b>Başarı Yüzdesi:</b> %{win_rate:.1f}"
    )
    await message.answer(msg, parse_mode="HTML")

@dp.message(Command("sinyaller"))
async def signals_cmd(message: types.Message):
    signals = await fetch_signals()
    pending_signals = [s for s in signals if s.get("status") == "pending"]
    
    if not pending_signals:
        await message.answer("Şu an bekleyen aktif sinyal bulunmuyor.")
        return

    msg = "<b>⏳ AKTİF BEKLEYEN SİNYALLER</b>\n\n"
    for s in pending_signals[:10]:
        home = s.get("home_team", "Ev")
        away = s.get("away_team", "Deplasman")
        sig_type = s.get("type", "Sinyal")
        msg += f"⚽ <b>{home} vs {away}</b>\n📌 Tip: {sig_type}\n------------------------\n"

    await message.answer(msg, parse_mode="HTML")

async def main():
    asyncio.create_task(track_signals_loop())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

async def fetch_signals():
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Farklı filtrelerle API istek adresleri (Tüm sinyalleri yakalamak için)
    urls = [
        f"https://betsignalhub.com/api/signals.php?date={today_str}&limit=1000",
        "https://betsignalhub.com/api/signals.php?status=all&limit=1000",
        "https://betsignalhub.com/api/signals.php"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://betsignalhub.com/dashboard",
        "Accept": "application/json"
    }

    all_fetched_signals = []
    seen_ids = set()

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for url in urls:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    signals_list = data.get("signals", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    
                    # Çekilen verileri çakışma olmadan birleştir
                    for sig in signals_list:
                        sig_id = str(sig.get("external_id") or sig.get("id"))
                        if sig_id and sig_id not in seen_ids:
                            seen_ids.add(sig_id)
                            all_fetched_signals.append(sig)
            except Exception as e:
                logging.error(f"API Baglanti Hatasi ({url}): {e}")

    return all_fetched_signals
