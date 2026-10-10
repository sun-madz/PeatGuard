"""Step 1b: download satellite fire hotspots (NASA FIRMS, VIIRS S-NPP) for the region.

Needs a free FIRMS MAP_KEY: https://firms.modaps.eosdis.nasa.gov/api/map_key/
Run from the project root:
    Mac/Linux:  FIRMS_KEY=yourkey python scripts/fetch_fires.py
    Windows:    set FIRMS_KEY=yourkey   then   python scripts/fetch_fires.py
Downloads 10-day chunks into data/fires/raw/ (safe to re-run), then combines them
into data/fires/hotspots.csv.
"""
import io, os, sys, time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FIRE_BBOX, HIST_START

KEY = os.environ.get("FIRMS_KEY")
if not KEY:
    sys.exit("Set the FIRMS_KEY environment variable first (see the top of this file).")

BASE = "https://firms.modaps.eosdis.nasa.gov/api"
RAW = Path("data/fires/raw")
RAW.mkdir(parents=True, exist_ok=True)


def availability():
    """Latest date covered by the archive (SP) and near-real-time (NRT) sources."""
    r = requests.get(f"{BASE}/data_availability/csv/{KEY}/ALL", timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    return {row.data_id: (row.min_date, row.max_date) for row in df.itertuples()}


def get_chunk(source, start, days):
    url = f"{BASE}/area/csv/{KEY}/{source}/{FIRE_BBOX}/{days}/{start}"
    for attempt in range(6):
        r = requests.get(url, timeout=180)
        text = r.text
        if r.status_code == 200 and "Exceeding" not in text and "Invalid" not in text:
            return text
        print(f"   {r.status_code} {text[:120]!r}; waiting before retry")
        time.sleep(90 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def download(source, start, end):
    d = date.fromisoformat(start)
    end = date.fromisoformat(end)
    while d <= end:
        days = min(5, (end - d).days + 1)
        f = RAW / f"{source}_{d.isoformat()}.csv"
        if not f.exists():
            print(f"{source} {d} (+{days}d)")
            f.write_text(get_chunk(source, d.isoformat(), days))
            time.sleep(1)
        d += timedelta(days=days)


def combine():
    frames = []
    for f in sorted(RAW.glob("*.csv")):
        try:
            df = pd.read_csv(f)
        except pd.errors.EmptyDataError:
            continue
        if df.empty or "latitude" not in df.columns:
            continue
        df["source"] = f.name.split("_20")[0]
        frames.append(df)
    allf = pd.concat(frames, ignore_index=True)
    keep = [c for c in ["latitude", "longitude", "acq_date", "confidence",
                        "frp", "type", "source"] if c in allf.columns]
    allf = allf[keep].drop_duplicates()
    out = Path("data/fires/hotspots.csv")
    allf.to_csv(out, index=False)
    print(f"Saved {len(allf):,} hotspots to {out}")


def main():
    av = availability()
    sp_end = av["VIIRS_SNPP_SP"][1]
    nrt_start, nrt_end = av["VIIRS_SNPP_NRT"]
    print("Archive (SP) to", sp_end, "| near-real-time (NRT)", nrt_start, "to", nrt_end)
    download("VIIRS_SNPP_SP", HIST_START, sp_end)
    gap_start = (date.fromisoformat(sp_end) + timedelta(days=1)).isoformat()
    download("VIIRS_SNPP_NRT", max(gap_start, nrt_start), nrt_end)
    combine()


if __name__ == "__main__":
    main()
