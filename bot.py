import time
import requests
from datetime import datetime

SUPABASE_URL = "https://tounfjouealqppeoqvij.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRvdW5mam91ZWFscXBwZW9xdmlqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA3NDg2NjMsImV4cCI6MjEwNjMyNDY2M30.J65td7zwVaAuvkTzONdJty0Hwsspi8JAB2GsNuI35DU"

HEADERS_SUPABASE = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

VOLUME_USD = 100.0
FEE_THRESHOLD = 0.40

def fetch_cex_price():
    try:
        target_url = "https://api.bybit.com/v5/market/tickers?category=spot&symbol=MNTUSDT"
        proxy_url = f"https://corsproxy.io/?{target_url}"
        response = requests.get(proxy_url, headers=HEADERS_WEB, timeout=7)
        if response.status_code != 200:
            return None
        data = response.json()
        return float(data['result']['list'][0]['lastPrice'])
    except Exception:
        return None

def fetch_dex_price():
    try:
        url = "https://api.dexscreener.com/latest/dex/tokens/0x78c1b0c915c4faa5fffa6cabf0219da63d7f4cb8"
        response = requests.get(url, headers=HEADERS_WEB, timeout=7)
        if response.status_code != 200:
            return None
        data = response.json()
        pairs = data.get('pairs', [])
        for pair in pairs:
            if pair.get('chainId') == 'mantle' and 'agni' in pair.get('dexId', '').lower():
                return float(pair.get('priceUsd'))
        for pair in pairs:
            if pair.get('chainId') == 'mantle':
                return float(pair.get('priceUsd'))
        return None
    except Exception:
        return None

def insert_to_supabase(data_row):
    try:
        url = f"{SUPABASE_URL}/rest/v1/spread_events"
        requests.post(url, json=data_row, headers=HEADERS_SUPABASE, timeout=5)
    except Exception:
        pass

def determine_status(net_spread):
    if net_spread >= 1.20:
        return "HIGH_PRIORITY"
    elif net_spread >= 0.75:
        return "ACTIONABLE"
    elif net_spread >= 0.40:
        return "LOW_MARGIN"
    return "IGNORE"

def main():
    print("Запуск воркера через прокси-шлюз...", flush=True)
    active_event = None

    while True:
        start_time = time.time()
        current_time_str = datetime.now().strftime("%H:%M:%S")
        
        cex_price = fetch_cex_price()
        dex_price = fetch_dex_price()
        
        if cex_price and dex_price:
            raw_spread = ((cex_price - dex_price) / dex_price) * 100
            if cex_price > dex_price:
                direction = "DEX->CEX"
                gross_spread = abs(raw_spread)
            else:
                direction = "CEX->DEX"
                gross_spread = abs(raw_spread)

            net_spread = max(0.0, gross_spread - 0.40)
            status = determine_status(net_spread)
            
            print(f"\r[{current_time_str}] CEX: {cex_price} | DEX: {dex_price} | Чистый спред: {net_spread:.2f}% [{status}]     ", end="", flush=True)

            if net_spread >= FEE_THRESHOLD:
                mnt_profit = (VOLUME_USD * (net_spread / 100.0)) / cex_price
                if active_event is None:
                    active_event = {
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "direction": direction,
                        "net_spread": round(net_spread, 4),
                        "duration_sec": 3,
                        "volume_usd": VOLUME_USD,
                        "mnt_profit": round(mnt_profit, 6),
                        "status": status
                    }
                else:
                    active_event["duration_sec"] += 3
                    if net_spread > active_event["net_spread"]:
                        active_event["net_spread"] = round(net_spread, 4)
                        active_event["mnt_profit"] = round(mnt_profit, 6)
                        active_event["status"] = status
                        active_event["direction"] = direction
            else:
                if active_event is not None:
                    print(f"\n[{current_time_str}] [!] Сохранение в Supabase: Длительность {active_event['duration_sec']}с, Чистый спред: {active_event['net_spread']}% [{active_event['status']}]", flush=True)
                    insert_to_supabase(active_event)
                    active_event = None
        else:
            print(f"\r[{current_time_str}] [LOG] Ошибка получения цен через прокси...                       ", end="", flush=True)

        elapsed = time.time() - start_time
        sleep_time = max(0, 3.0 - elapsed)
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
