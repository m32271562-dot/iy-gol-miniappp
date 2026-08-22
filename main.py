import httpx
from datetime import datetime

async def get_signals():
    today_str = datetime.now().strftime("%Y-%m-%d")
    url = f"https://betsignalhub.com/api/signals.php?date={today_str}&limit=500"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://betsignalhub.com/dashboard"
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("signals", [])
        return []
