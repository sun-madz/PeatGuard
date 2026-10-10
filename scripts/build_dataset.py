"""Step 2: turn downloaded weather + hotspots into one training table.

Run from the project root:  python scripts/build_dataset.py
Output:
  data/dataset.csv.gz      one row per zone per day: features + label
  models/zone_state.csv    each zone's latest dryness, used to start the live forecast
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (build_zones, CELL, HORIZON_DAYS, MIN_HOTSPOTS_FOR_FIRE,
                    STATIC_MIN_DAYS, STATIC_MIN_YEARS, TEST_START)
from features import (weather_features, hotspot_counts, add_fire_features, FEATURES,
                      climatology, add_anomalies, add_climate)

WEATHER = Path("data/weather")
HOT = Path("data/fires/hotspots.csv")
Path("models").mkdir(exist_ok=True)


def load_hotspots():
    h = pd.read_csv(HOT)
    n0 = len(h)
    h["date"] = pd.to_datetime(h["acq_date"])
    # Drop low-confidence detections.
    if "confidence" in h:
        h = h[h["confidence"].astype(str).str.lower().str[0] != "l"]
    # Drop known non-fire heat sources (factories, gas flares, offshore) where labelled.
    if "type" in h:
        h = h[h["type"].isna() | (h["type"] == 0)]
    # Drop persistent static heat sources: the same ~1 km spot burning on many days
    # across many years is a factory or flare, not a fire.
    key = h["latitude"].round(2).astype(str) + "," + h["longitude"].round(2).astype(str)
    days = h.groupby(key)["date"].nunique()
    years = h["date"].dt.year.groupby(key).nunique()
    static = set(days[(days >= STATIC_MIN_DAYS) & (years >= STATIC_MIN_YEARS)].index)
    n1 = len(h)
    h = h[~key.isin(static)]
    print(f"Hotspots: {n0:,} downloaded, {n1:,} after confidence/type filters, "
          f"{len(h):,} after removing {len(static):,} static heat sources")
    return h


def main():
    zones = build_zones()
    half = CELL / 2
    hot = load_hotspots()
    counts = hotspot_counts(hot, zones, half)
    inside = counts["inside"]
    fire_end = hot["date"].max()
    print("Fire data runs to", fire_end.date())

    rows, states = [], []
    for z in zones:
        f = WEATHER / f"{z['zone_id']}.csv"
        if not f.exists():
            print("  missing weather for", z["zone_id"], "- skipped")
            continue
        w = weather_features(pd.read_csv(f))
        w = add_fire_features(w, z["zone_id"], counts, MIN_HOTSPOTS_FOR_FIRE)

        # Label: at least MIN_HOTSPOTS_FOR_FIRE hotspots inside the zone in the NEXT 7 days (not including today).
        zin = inside.get(z["zone_id"], pd.Series(dtype=float))
        full = pd.date_range(w["date"].min(), w["date"].max() + pd.Timedelta(days=HORIZON_DAYS))
        zin = zin.reindex(full, fill_value=0)
        future = zin[::-1].rolling(HORIZON_DAYS, min_periods=1).sum()[::-1].shift(-1)
        w["fire_next7"] = (future.reindex(w["date"]).to_numpy() >= MIN_HOTSPOTS_FOR_FIRE).astype(int)
        # Only keep days whose full 7-day future is covered by fire data.
        w = w[w["date"] + pd.Timedelta(days=HORIZON_DAYS) <= fire_end]

        for k in ["zone_id", "region", "country", "lat", "lon", "impact"]:
            w[k] = z[k]
        rows.append(w)
        last = w.iloc[-1] if len(w) else None
        if last is not None:
            states.append({"zone_id": z["zone_id"], "date": last["date"].date(),
                           "deficit_mm": round(float(last["deficit_mm"]), 2)})

    df = pd.concat(rows, ignore_index=True)
    # Each zone's normal weather per month, from training years only (no peeking at test years).
    clim = climatology(df[df["date"] < TEST_START])
    clim.to_csv("models/climatology.csv", index=False)
    df = add_anomalies(df, clim)
    climate_file = Path("data/climate.csv")
    if climate_file.exists():
        df = add_climate(df, pd.read_csv(climate_file))
    else:
        print("WARNING: data/climate.csv missing - run scripts/fetch_climate.py first")
        for c in ["nino34_lag1", "nino34_3m", "dmi_lag1", "dmi_3m"]:
            df[c] = np.nan
    keep = ["zone_id", "region", "country", "lat", "lon", "impact", "date",
            "wind_dir", "hot_zone_1"] + FEATURES + ["fire_next7"]
    df = df[keep].dropna(subset=["deficit_change_7"])
    df.to_csv("data/dataset.csv.gz", index=False)
    pd.DataFrame(states).to_csv("models/zone_state.csv", index=False)

    print(f"\nDataset: {len(df):,} rows, {df['zone_id'].nunique()} zones, "
          f"{df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Fire-in-next-7-days rate: {df['fire_next7'].mean():.1%}")
    print("\nFire rate by region:")
    print(df.groupby("region")["fire_next7"].mean().map("{:.1%}".format).to_string())
    print("\nFire rate by year (2015 and 2019 should stand out):")
    print(df.groupby(df["date"].dt.year)["fire_next7"].mean().map("{:.1%}".format).to_string())


if __name__ == "__main__":
    main()
