"""PeatGuard decision layer: live data -> features -> risk -> category, priority, reasons, action.

Used by app.py. Everything here works without the big data/ folder: it reads the compact
files that scripts/build_dataset.py and scripts/train.py write to models/.
"""
import json
from datetime import date, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests

from config import build_zones, CELL, MIN_HOTSPOTS_FOR_FIRE, DANGER_WATER_TABLE_CM
from features import (weather_features, add_fire_features, add_anomalies, add_climate,
                      et0_hargreaves, hotspot_counts)

M = Path(__file__).parent / "models"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{bbox}/{days}"

# ---------------------------------------------------------------- loading


def load_artifacts():
    a = {
        "spread": lgb.Booster(model_file=str(M / "model_spread.txt")),
        "ignition": lgb.Booster(model_file=str(M / "model_ignition.txt")),
        "metrics": json.loads((M / "metrics.json").read_text()),
        "clim": pd.read_csv(M / "climatology.csv"),
        "climate": pd.read_csv(M / "climate.csv"),
        "info": json.loads((M / "data_info.json").read_text()),
        "zones": pd.DataFrame(build_zones()),
    }
    return a


def load_counts():
    zc = pd.read_csv(M / "zone_counts.csv.gz", parse_dates=["date"])
    return zc


def load_recent_weather():
    return pd.read_csv(M / "recent_weather.csv.gz")


# ---------------------------------------------------------------- live data


def fetch_live_weather(zones, start, forecast_days=8):
    """Open-Meteo daily weather from `start` to today, plus the forecast. Same columns
    and formulas as training (evaporation via Hargreaves from max/min temperature)."""
    past_days = min(92, max(1, (date.today() - start).days + 1))
    frames = []
    for b in range(0, len(zones), 20):
        batch = zones.iloc[b:b + 20]
        params = {
            "latitude": ",".join(map(str, batch["lat"])),
            "longitude": ",".join(map(str, batch["lon"])),
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,"
                     "wind_speed_10m_max,wind_direction_10m_dominant,relative_humidity_2m_min",
            "past_days": past_days, "forecast_days": forecast_days,
            "timezone": "Asia/Singapore",
        }
        r = requests.get(FORECAST_URL, params=params, timeout=60)
        r.raise_for_status()
        js = r.json()
        js = js if isinstance(js, list) else [js]
        for (_, z), j in zip(batch.iterrows(), js):
            d = pd.DataFrame(j["daily"]).rename(columns={
                "time": "date", "relative_humidity_2m_min": "rh_min"})
            dt = pd.to_datetime(d["date"])
            d["et0_fao_evapotranspiration"] = et0_hargreaves(
                d["temperature_2m_max"], d["temperature_2m_min"], z["lat"], dt.dt.dayofyear)
            d.insert(0, "zone_id", z["zone_id"])
            frames.append(d)
    return pd.concat(frames, ignore_index=True)


def fetch_live_hotspots(key, days=5):
    """Last few days of satellite hotspots (FIRMS near-real-time). Needs a FIRMS key."""
    from config import FIRE_BBOX
    r = requests.get(FIRMS_URL.format(key=key, bbox=FIRE_BBOX, days=days), timeout=60)
    r.raise_for_status()
    from io import StringIO
    h = pd.read_csv(StringIO(r.text))
    if h.empty or "latitude" not in h:
        return pd.DataFrame(columns=["latitude", "longitude", "date", "frp"])
    h["date"] = pd.to_datetime(h["acq_date"])
    if "confidence" in h:
        h = h[h["confidence"].astype(str).str.lower().str[0] != "l"]
    static = set(pd.read_csv(M / "static_sources.csv")["key"]) if (M / "static_sources.csv").exists() else set()
    key_ = h["latitude"].round(2).astype(str) + "," + h["longitude"].round(2).astype(str)
    return h[~key_.isin(static)]


# ---------------------------------------------------------------- features + scoring


def counts_to_tables(zc):
    """Long zone_counts -> dict of date x zone tables (as features.hotspot_counts returns)."""
    out = {}
    for k in ["inside", "near", "frp_in", "frp_near"]:
        out[k] = zc.pivot_table(index="date", columns="zone_id", values=k, aggfunc="sum").fillna(0)
    return out


def build_features(a, weather, zc):
    """Weather (all zones, daily) + hotspot counts -> one feature row per zone per day."""
    tables = counts_to_tables(zc)
    rows = []
    for _, z in a["zones"].iterrows():
        w = weather[weather["zone_id"] == z["zone_id"]].drop_duplicates("date", keep="last")
        if w.empty:
            continue
        w = weather_features(w)
        w = add_fire_features(w, z["zone_id"], tables, MIN_HOTSPOTS_FOR_FIRE)
        for k in ["zone_id", "region", "country", "lat", "lon", "impact"]:
            w[k] = z[k]
        rows.append(w)
    df = pd.concat(rows, ignore_index=True)
    df = add_anomalies(df, a["clim"])
    df = add_climate(df, a["climate"])
    return df


def score(a, df):
    df = df.copy()
    feats = a["metrics"]["features"]
    thr = a["metrics"]["thresholds"]
    act = (df["hot_zone_7"] > 0).to_numpy()
    df["model"] = np.where(act, "spread", "ignition")
    df["p"] = 0.0
    contrib = np.zeros((len(df), 0))
    contribs = {}
    for kind, mask in (("spread", act), ("ignition", ~act)):
        if mask.any():
            X = df.loc[mask, feats[kind]]
            df.loc[mask, "p"] = a[kind].predict(X)
            c = a[kind].predict(X, pred_contrib=True)[:, :-1]   # last column = bias
            contribs[kind] = (np.flatnonzero(mask), pd.DataFrame(c, columns=feats[kind]))
    df["thr"] = np.where(act, thr["spread"], thr["ignition"])
    df["level"] = np.select([df["p"] >= df["thr"], df["p"] >= df["thr"] / 2],
                            ["High", "Elevated"], "Low")
    df["_contrib"] = None
    for kind, (pos, c) in contribs.items():
        for i, row in zip(pos, c.to_dict("records")):
            df.at[df.index[i], "_contrib"] = row
    return df


# ---------------------------------------------------------------- explanations

GROUPS = {
    "Drought": ["rain_7", "rain_14", "rain_30", "rain_60", "rain_90", "dry_days", "deficit_mm",
                "deficit_change_7", "wt_est_cm", "rain_30_anom", "rain_90_anom",
                "deficit_mm_anom", "et0_7", "rh_min", "rh_min_7", "rh_min_7_anom",
                "tmax", "tmax_7", "tmax_7_anom", "wind_max"],
    "Climate (El Niño / IOD)": ["nino34_lag1", "nino34_3m", "dmi_lag1", "dmi_3m"],
    "Repeat-burn area": ["hot_zone_30", "hot_zone_90", "hot_zone_365", "days_since_fire",
                         "zone_month_fire_rate"],
    "Fire nearby": ["hot_near_7", "hot_near_1", "frp_near_7"],
    "Fire season": ["month_sin", "month_cos"],
    "Active fire": ["hot_zone_7", "frp_zone_7"],
}
FEATURE_GROUP = {f: g for g, fs in GROUPS.items() for f in fs}


def reason_text(f, r):
    v = r.get(f, np.nan)
    if pd.isna(v):
        return None
    wt = r.get("wt_est_cm", np.nan)
    texts = {
        "dry_days": f"{v:.0f} days in a row without real rain" if v >= 3 else None,
        "deficit_mm": f"estimated water table about {wt:.0f} cm below the surface "
                      f"(danger line {DANGER_WATER_TABLE_CM} cm)" if wt >= 20 else None,
        "wt_est_cm": f"estimated water table about {v:.0f} cm below the surface "
                     f"(danger line {DANGER_WATER_TABLE_CM} cm)" if v >= 20 else None,
        "deficit_change_7": f"peat dried by about {v:.0f} mm of water in the past week" if v > 0 else None,
        "rain_30_anom": f"{-v:.0f} mm less rain than normal over the past month" if v < 0 else None,
        "rain_90_anom": f"{-v:.0f} mm less rain than normal over the past 3 months" if v < 0 else None,
        "deficit_mm_anom": "peat drier than normal for this time of year" if v > 0 else None,
        "rain_7": f"only {v:.0f} mm of rain in the past week" if v < 20 else None,
        "rain_14": f"only {v:.0f} mm of rain in the past 2 weeks" if v < 40 else None,
        "rain_30": f"only {v:.0f} mm of rain in the past month" if v < 100 else None,
        "rain_60": f"only {v:.0f} mm of rain in the past 2 months" if v < 200 else None,
        "rain_90": f"only {v:.0f} mm of rain in the past 3 months" if v < 300 else None,
        "tmax_7_anom": f"{v:.1f} °C hotter than normal this week" if v > 0 else None,
        "rh_min_7_anom": f"air {-v:.0f}% drier than normal this week" if v < 0 else None,
        "rh_min": f"very dry afternoon air ({v:.0f}% humidity)" if v < 55 else None,
        "wind_max": f"strong winds ({v:.0f} km/h) that spread fire" if v > 25 else None,
        "nino34_3m": f"El Niño conditions (Niño 3.4 at {v:+.1f} °C)" if v > 0.5 else None,
        "nino34_lag1": f"El Niño conditions (Niño 3.4 at {v:+.1f} °C)" if v > 0.5 else None,
        "dmi_3m": f"positive Indian Ocean Dipole ({v:+.1f}), which dries Sumatra and Borneo" if v > 0.4 else None,
        "dmi_lag1": f"positive Indian Ocean Dipole ({v:+.1f}), which dries Sumatra and Borneo" if v > 0.4 else None,
        "hot_zone_7": f"{v:.0f} fire hotspots in this zone this week" if v > 0 else None,
        "frp_zone_7": "intense fires burning in this zone" if v > 50 else None,
        "hot_zone_30": f"{v:.0f} hotspots here in the past month" if v > 0 else None,
        "hot_zone_90": f"{v:.0f} hotspots here in the past 3 months" if v > 0 else None,
        "hot_zone_365": f"{v:.0f} hotspots here in the past year" if v > 0 else None,
        "days_since_fire": f"last burned {v:.0f} days ago (peat often re-ignites)" if v < 120 else None,
        "zone_month_fire_rate": f"this zone burned in this month in {v:.0%} of past years" if v > 0 else None,
        "hot_near_7": f"{v:.0f} hotspots within 80 km this week" if v > 0 else None,
        "hot_near_1": f"{v:.0f} hotspots within 80 km today" if v > 0 else None,
        "frp_near_7": "intense fires within 80 km" if v > 50 else None,
        "month_sin": "peak fire season for this area",
        "month_cos": "peak fire season for this area",
    }
    return texts.get(f)


def explain(r, top=3):
    """Return (category, [reason sentences]) from the model's per-feature contributions."""
    c = r["_contrib"] or {}
    pos = sorted(((v, f) for f, v in c.items() if v > 0), reverse=True)
    reasons, seen = [], set()
    for v, f in pos:
        t = reason_text(f, r)
        if t and t not in seen:
            reasons.append(t); seen.add(t)
        if len(reasons) == top:
            break
    group_score = {}
    for v, f in pos:
        g = FEATURE_GROUP.get(f, "Other")
        group_score[g] = group_score.get(g, 0) + v
    if r["hot_zone_7"] > 0:
        cat = "Active fire: spread risk"
    elif group_score:
        g = max(group_score, key=group_score.get)
        cat = {"Drought": "New fire risk: drought",
               "Climate (El Niño / IOD)": "New fire risk: El Niño / IOD dry spell",
               "Repeat-burn area": "New fire risk: repeat-burn area",
               "Fire nearby": "New fire risk: fire spreading from nearby",
               "Fire season": "New fire risk: fire season"}.get(g, "New fire risk")
    else:
        cat = "Low risk"
    return cat, reasons


def action(level, cat):
    if level == "High" and cat.startswith("Active"):
        return ("Send a fire crew today. Check the edges of the burn for spread into dry peat, "
                "and warn nearby communities about smoke.")
    if level == "High":
        return ("Patrol this zone today. Check canal blocks and water levels, enforce the "
                "open-burning ban, and position water pumps nearby.")
    if level == "Elevated":
        return "Schedule a patrol within 3 days and keep watching the daily risk."
    return "Routine monitoring."


def toward_malaysia(r):
    """Does today's wind carry this Indonesian zone's smoke toward Malaysia?"""
    if r["country"] != "ID" or pd.isna(r.get("wind_dir")):
        return False
    d = r["wind_dir"]   # direction the wind blows FROM (degrees)
    return 135 <= d <= 270   # southerly/south-westerly wind pushes smoke north to Malaysia


def decide(df):
    """Add category, reasons, action and priority for each zone row."""
    df = df.copy()
    cats, reasons, acts, haze = [], [], [], []
    for _, r in df.iterrows():
        cat, rs = explain(r)
        cats.append(cat); reasons.append(rs); acts.append(action(r["level"], cat))
        haze.append(toward_malaysia(r))
    df["category"], df["reasons"], df["action"], df["smoke_to_MY"] = cats, reasons, acts, haze
    # Priority = chance of fire x people exposed nearby x smoke blowing toward Malaysia.
    df["priority"] = df["p"] * df["impact"] * np.where(df["smoke_to_MY"], 1.5, 1.0)
    df["rank"] = df["priority"].rank(ascending=False, method="first").astype(int)
    return df.sort_values("rank")


def cell_polygon(lat, lon, half=CELL / 2):
    return [[lon - half, lat - half], [lon + half, lat - half],
            [lon + half, lat + half], [lon - half, lat + half]]


# ---------------------------------------------------------------- one-call pipeline


def run(a, firms_key=None, live=True):
    """Returns (scored_today, all_feature_rows, status dict)."""
    status = {"weather": "stored", "fires": "stored"}
    info = a["info"]
    weather = load_recent_weather()
    zc = load_counts()
    w_end = pd.to_datetime(info["weather_end"]).date()
    today = w_end
    if live:
        try:
            lw = fetch_live_weather(a["zones"], w_end + timedelta(days=1))
            lw = lw[pd.to_datetime(lw["date"]).dt.date > w_end]
            weather = pd.concat([weather, lw], ignore_index=True)
            today = date.today()
            status["weather"] = "live"
        except Exception as e:
            status["weather_error"] = str(e)[:200]
        if firms_key:
            try:
                h = fetch_live_hotspots(firms_key)
                pts = h[["latitude", "longitude", "date"] + (["frp"] if "frp" in h else [])].copy()
                pts["date"] = pts["date"].dt.strftime("%Y-%m-%d")
                status["points"] = pts.to_dict("records")   # raw live hotspots for the map
                f_end = pd.to_datetime(info["fire_end"])
                h = h[h["date"] > f_end]
                if len(h):
                    c = hotspot_counts(h, a["zones"].to_dict("records"), CELL / 2)
                    long = []
                    for k, tab in c.items():
                        t = tab.stack().rename(k)
                        long.append(t[t > 0])
                    new = pd.concat(long, axis=1).fillna(0).rename_axis(["date", "zone_id"]).reset_index()
                    zc = pd.concat([zc, new], ignore_index=True)
                status["fires"] = "live"
            except Exception as e:
                status["fires_error"] = str(e)[:200]
    feats = build_features(a, weather, zc)
    feats["date"] = pd.to_datetime(feats["date"])
    pred_day = pd.Timestamp(min(today, feats["date"].max().date()))
    now = feats[feats["date"] == pred_day]
    scored = decide(score(a, now))
    status["as_of"] = str(pred_day.date())
    return scored, feats, status
