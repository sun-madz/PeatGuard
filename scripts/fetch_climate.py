"""Step 1c: download monthly ocean-climate indices from NOAA (free, no key).

  Nino 3.4 anomaly  - El Nino / La Nina strength (El Nino = drier Southeast Asia)
  DMI               - Indian Ocean Dipole (positive = drier Sumatra and Borneo)

Run from the project root:  python scripts/fetch_climate.py
Saves data/climate.csv and models/climate.csv (small; the app needs it).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import requests

NINO_SOURCES = [
    ("cpc", "https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.91-20.ascii"),
    ("psl", "https://psl.noaa.gov/data/correlation/nina34.anom.data"),
]
DMI_SOURCES = [
    ("psl", "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"),
    ("psl", "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data"),
]


def get(url):
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text


def parse_psl(text):
    """NOAA PSL format: 'start end' line, then 'YEAR v1 ... v12' rows; -99.99 = missing."""
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 13:
            if rows:
                break
            continue
        try:
            year = int(parts[0]); vals = [float(v) for v in parts[1:]]
        except ValueError:
            break
        for m, v in enumerate(vals, 1):
            rows.append((year, m, np.nan if v <= -99 else v))
    return pd.DataFrame(rows, columns=["year", "month", "value"])


def parse_cpc(text):
    """CPC ERSSTv5 table: YR MON then 4 pairs (value, anomaly); Nino 3.4 anomaly is last."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 10 and parts[0].isdigit():
            rows.append((int(parts[0]), int(parts[1]), float(parts[-1])))
    return pd.DataFrame(rows, columns=["year", "month", "value"])


def fetch(sources, name):
    for kind, url in sources:
        try:
            df = (parse_cpc if kind == "cpc" else parse_psl)(get(url)).dropna()
            if len(df) > 100:
                last = df.iloc[-1]
                print(f"{name}: {len(df)} months from {url} (latest {int(last.year)}-{int(last.month):02d})")
                return df.rename(columns={"value": name})
        except Exception as e:
            print(f"{name}: could not use {url} ({e})")
    print(f"{name}: no source worked; the model will treat it as missing")
    return pd.DataFrame(columns=["year", "month", name])


def main():
    nino = fetch(NINO_SOURCES, "nino34")
    dmi = fetch(DMI_SOURCES, "dmi")
    df = nino.merge(dmi, on=["year", "month"], how="outer").sort_values(["year", "month"])
    df = df[df["year"] >= 2010]
    for d in ("data", "models"):
        Path(d).mkdir(exist_ok=True)
        df.to_csv(f"{d}/climate.csv", index=False)
    print("Saved data/climate.csv and models/climate.csv")
    print(df[df["year"].isin([2015, 2019, 2023])].groupby("year")[["nino34", "dmi"]].max()
          .round(2).to_string())


if __name__ == "__main__":
    main()
