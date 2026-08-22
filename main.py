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

# Takip edilen durumlar (Hafıza)
known_signals = set()       # Bildirimi atılmış sinyal ID'leri
known_status = {}          # Sinyal ID -> durum ("pending", "won", "lost")
subscribers = set()        # Bildirim alacak kullanıcı/kanal ID'leri

async def fetch_signals():
    today_str = datetime.now().strftime("%Y-%m-%d")
    url = f"https://betsignalhub.com/api/signals.php?date={today_str}&limit=500"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://betsignalhub.com/dashboard"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("signals", [])
        except Exception as e:
            logging.error(f"API Hatasi: {e}")
            return []
    return []

# Sitedeki yeni sinyalleri ve kazandı/kaybetti durumlarını kontrol eden döngü
async def track_signals_loop():
    while True:
        try:
            signals = await fetch_signals()
            
            for sig in signals:
                sig_id = sig.get("external_id") or sig.get("id")
                if not sig_id:
                    continue

                status = sig.get("status", "pending")
                home = sig.get("home_team", "Ev")
                away = sig.get("away_team", "Deplasman")
                sig_type = sig.get("type", "Canlı Analiz")
                
                # 1. YENİ SİNYAL DÜŞTÜĞÜNDE BİLDİRİM AT
                if sig_id not in known_signals and status == "pending":
                    known_signals.add(sig_id)
                    known_status[sig_id] = status
                    
                    msg = (
                        f"🚨 <b>YENİ SİNYAL DÜŞTÜ!</b>\n\n"
                        f"⚽ <b>{home} vs {away}</b>\n"
                        f"📌 <b>Tahmin:</b> {sig_type}\n"
                        f"⏳ <b>Durum:</b> Bekliyor"
                    )
                    
                    for chat_id in subscribers:
                        try:
                            await bot.send_message(chat_id, msg, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Mesaj gonderme hatasi ({chat_id}): {e}")

                # 2. SONUÇLANDIĞINDA (WON / LOST) BİLDİRİM AT
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
                    
                    for chat_id in subscribers:
                        try:
                            await bot.send_message(chat_id, msg, parse_mode="HTML")
                        except Exception as e:
                            logging.error(f"Mesaj gonderme hatasi ({chat_id}): {e}")

        except Exception as e:
            logging.error(f"Döngü hatası: {e}")

        # 15 saniyede bir siteyi kontrol et
        await asyncio.sleep(15)

# /start komutu
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    subscribers.add(message.chat.id)
    await message.answer(
        "✅ **Bot Aktif Edildi!**\n\n"
        "Yeni sinyaller düşdüğünde ve sinyaller sonuçlandığında (Kazandı/Kaybetti) otomatik bildirim alacaksınız.\n\n"
        "Komutlar:\n"
        "/durum - Günün başarı yüzdesi ve istatistikleri\n"
        "/sinyaller - Aktif bekleyen sinyaller"
    )

# /durum komutu (Günün başarı yüzdesini ve istatistiklerini hesaplar)
@dp.message(Command("durum"))
async def stats_cmd(message: types.Message):
    signals = await fetch_signals()
    if not signals:
        await message.answer("Güncel veriler alınamadı.")
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

# /sinyaller komutu
@dp.message(Command("sinyaller"))
async def signals_cmd(message: types.Message):
    signals = await fetch_signals()
    pending_signals = [s for s in signals if s.get("status") == "pending"]
    
    if not pending_signals:
        await message.answer("Şu an bekleyen aktif sinyal yok.")
        return

    msg = "<b>⏳ BEKLEYEN SİNYALLER</b>\n\n"
    for s in pending_signals[:10]:
        home = s.get("home_team", "Ev")
        away = s.get("away_team", "Deplasman")
        sig_type = s.get("type", "Sinyal")
        msg += f"⚽ <b>{home} vs {away}</b>\n📌 {sig_type}\n------------------------\n"

    await message.answer(msg, parse_mode="HTML")

async def main():
    # Arka planda siteyi dinleyen döngüyü başlat
    asyncio.create_task(track_signals_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
