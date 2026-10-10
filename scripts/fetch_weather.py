"""Step 1a: download daily weather history for every zone from NASA POWER (free, no key).

Run from the project root:  python scripts/fetch_weather.py
One request per zone covers the whole period. Runs 3 zones at a time.
Saves one CSV per zone in data/weather/. Safe to re-run: finished zones are skipped.

Columns produced (same names the rest of the code expects):
  precipitation_sum (mm), temperature_2m_max (C), temperature_2m_min (C),
  wind_speed_10m_max (km/h), wind_direction_10m_dominant (deg),
  rh_min (%, humidity at the hottest part of the day, from dew point),
  et0_fao_evapotranspiration (mm, Hargreaves method; see features.et0_hargreaves)
"""
import sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import build_zones, HIST_START, HIST_END
from features import et0_hargreaves, rh_from_dewpoint

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["PRECTOTCORR", "T2M_MAX", "T2M_MIN", "T2MDEW", "WS10M_MAX", "WD10M"]
OUT = Path("data/weather")
OUT.mkdir(parents=True, exist_ok=True)


def fetch(zone):
    params = {
        "parameters": ",".join(PARAMS),
        "community": "AG",
        "latitude": zone["lat"], "longitude": zone["lon"],
        "start": HIST_START.replace("-", ""), "end": HIST_END.replace("-", ""),
        "format": "JSON",
    }
    for attempt in range(8):
        try:
            r = requests.get(URL, params=params, timeout=300)
        except requests.exceptions.RequestException as e:
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(30 * (attempt + 1))
            continue
        raise RuntimeError(f"{zone['zone_id']}: {r.status_code}: {r.text[:300]}")
    raise RuntimeError(f"{zone['zone_id']}: too many retries")


def to_frame(js, zone):
    p = js["properties"]["parameter"]
    df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan).sort_index()
    out = pd.DataFrame({
        "zone_id": zone["zone_id"],
        "date": df.index.strftime("%Y-%m-%d"),
        "precipitation_sum": df["PRECTOTCORR"].to_numpy(),
        "temperature_2m_max": df["T2M_MAX"].to_numpy(),
        "temperature_2m_min": df["T2M_MIN"].to_numpy(),
        "wind_speed_10m_max": (df["WS10M_MAX"] * 3.6).to_numpy(),  # m/s -> km/h
        "wind_direction_10m_dominant": df["WD10M"].to_numpy(),
        "rh_min": rh_from_dewpoint(df["T2MDEW"].to_numpy(), df["T2M_MAX"].to_numpy()),
    })
    out["et0_fao_evapotranspiration"] = et0_hargreaves(
        out["temperature_2m_max"].to_numpy(), out["temperature_2m_min"].to_numpy(),
        zone["lat"], df.index.dayofyear.to_numpy())
    return out


def job(zone):
    to_frame(fetch(zone), zone).to_csv(OUT / f"{zone['zone_id']}.csv", index=False)
    return zone["zone_id"]


def main():
    zones = [z for z in build_zones() if not (OUT / f"{z['zone_id']}.csv").exists()]
    print(f"{len(zones)} zones to download from NASA POWER, {HIST_START} to {HIST_END}")
    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(job, z): z for z in zones}
        for f in as_completed(futures):
            try:
                zid = f.result()
                done += 1
                print(f"[{done}/{len(zones)}] {zid} saved", flush=True)
            except Exception as e:
                print("  FAILED:", e, "(re-run the script to retry)", flush=True)
    print("Done.")


if __name__ == "__main__":
    main()
