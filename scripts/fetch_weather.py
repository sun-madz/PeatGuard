"""Step 1a: download daily weather history for every zone from Open-Meteo (free, no key).

Run from the project root:  python scripts/fetch_weather.py
Saves one CSV per zone in data/weather/. Safe to re-run: finished zones are skipped.
"""
import sys, time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import build_zones, HIST_START, HIST_END

URL = "https://archive-api.open-meteo.com/v1/archive"
OUT = Path("data/weather")
OUT.mkdir(parents=True, exist_ok=True)

DAILY = [
    "precipitation_sum",
    "temperature_2m_max",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "et0_fao_evapotranspiration",
]
HOURLY = ["relative_humidity_2m"]  # aggregated to daily minimum below


def fetch(zone):
    params = {
        "latitude": zone["lat"], "longitude": zone["lon"],
        "start_date": HIST_START, "end_date": HIST_END,
        "daily": ",".join(DAILY), "hourly": ",".join(HOURLY),
        "timezone": "Asia/Singapore",
    }
    for attempt in range(6):
        r = requests.get(URL, params=params, timeout=120)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:  # rate limited: wait and retry
            wait = 60 * (attempt + 1)
            print(f"   rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
    raise RuntimeError("too many retries")


def to_daily(js):
    d = pd.DataFrame(js["daily"]).rename(columns={"time": "date"})
    h = pd.DataFrame(js["hourly"])
    h["date"] = h["time"].str[:10]
    rh = h.groupby("date")["relative_humidity_2m"].min().rename("rh_min").reset_index()
    return d.merge(rh, on="date", how="left")


def main():
    zones = build_zones()
    print(f"{len(zones)} zones, {HIST_START} to {HIST_END}")
    for i, z in enumerate(zones, 1):
        f = OUT / f"{z['zone_id']}.csv"
        if f.exists():
            continue
        print(f"[{i}/{len(zones)}] {z['zone_id']} ({z['region']})")
        df = to_daily(fetch(z))
        df.insert(0, "zone_id", z["zone_id"])
        df.to_csv(f, index=False)
        time.sleep(1.5)  # be polite to the free API
    print("Done.")


if __name__ == "__main__":
    main()
