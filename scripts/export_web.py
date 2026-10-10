"""Export PeatGuard predictions as small JSON files for the web app (web/data/).

Run from the project root:
    python scripts/export_web.py

Writes:
  web/data/today.json    today's risk for all 71 zones (live weather + satellite fires)
  web/data/metrics.json  the proof numbers and method facts from training
  web/data/air.json      air quality now and for the next 3 days (Open-Meteo / CAMS)
  web/data/replay.json   2023-2026 replay (only when data/dataset.csv.gz exists, i.e. in
                         the Codespace; the daily GitHub Action keeps the existing file)

Set FIRMS_KEY in the environment to include live satellite hotspots.
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import peatguard as pg  # noqa: E402

OUT = ROOT / "web" / "data"
OUT.mkdir(parents=True, exist_ok=True)
MYT = timezone(timedelta(hours=8))
PAST_DAYS = 60

# Approximate town/district centres used to give each ~55 km zone a human name.
TOWNS = {
    "Selangor": [("Kuala Langat", 2.81, 101.50), ("Kuala Selangor", 3.34, 101.25), ("Sabak Bernam", 3.68, 100.98),
                 ("Tanjung Karang", 3.42, 101.18), ("Klang", 3.04, 101.45), ("Sepang", 2.69, 101.75),
                 ("Hulu Selangor", 3.57, 101.66), ("Rawang", 3.32, 101.58)],
    "Johor": [("Batu Pahat", 1.85, 102.93), ("Pontian", 1.49, 103.39), ("Kluang", 2.03, 103.32),
              ("Muar", 2.05, 102.57), ("Benut", 1.63, 103.27)],
    "Pahang": [("Pekan", 3.49, 103.39), ("Kuantan", 3.82, 103.33), ("Nenasi", 3.13, 103.44),
               ("Maran", 3.59, 102.77), ("Chini", 3.43, 102.91)],
    "Sarawak": [("Mukah", 2.90, 112.09), ("Dalat", 2.73, 111.93), ("Sibu", 2.30, 111.82), ("Sarikei", 2.13, 111.52),
                ("Daro", 2.53, 111.43), ("Matu", 2.68, 111.53), ("Kanowit", 2.10, 112.15), ("Betong", 1.41, 111.53),
                ("Selangau", 2.53, 112.23), ("Sri Aman", 1.24, 111.46)],
    "Riau": [("Pekanbaru", 0.51, 101.45), ("Siak", 0.79, 102.05), ("Dumai", 1.67, 101.45), ("Bengkalis", 1.47, 102.11),
             ("Pangkalan Kerinci", 0.40, 101.86), ("Teluk Meranti", 0.20, 102.70), ("Bangkinang", 0.34, 101.03),
             ("Selatpanjang", 1.01, 102.71), ("Sungai Pakning", 1.33, 102.16), ("Duri", 1.29, 101.36),
             ("Rupat", 1.86, 101.60)],
    "South Sumatra-Jambi": [("Palembang", -2.99, 104.76), ("Kayu Agung", -3.39, 104.83), ("Sungsang", -2.37, 104.92),
                            ("Pangkalan Balai", -2.83, 104.38), ("Sekayu", -2.88, 103.85), ("Pedamaran", -3.47, 104.89),
                            ("Tulung Selapan", -3.20, 105.33), ("Air Sugihan", -2.65, 105.35), ("Muntok", -2.06, 105.16),
                            ("Muara Sabak", -1.13, 103.83), ("Jambi", -1.61, 103.61), ("Pangkalpinang", -2.13, 106.12),
                            ("Toboali", -3.00, 106.46)],
    "Central Kalimantan": [("Palangka Raya", -2.21, 113.92), ("Kuala Kapuas", -3.00, 114.39),
                           ("Pulang Pisau", -2.75, 114.26), ("Kasongan", -1.89, 113.40), ("Sampit", -2.54, 112.95),
                           ("Mantangai", -2.57, 114.48), ("Banjarmasin", -3.32, 114.59), ("Bahaur", -3.38, 114.10),
                           ("Tumbang Nusa", -2.35, 114.07), ("Buntok", -1.71, 114.84), ("Timpah", -1.95, 114.47)],
}

# Places people check air quality for (Malaysia first, then the main smoke-source cities).
AIR_PLACES = [
    ("Kuala Lumpur", "Kuala Lumpur", 3.139, 101.687), ("Shah Alam", "Selangor", 3.073, 101.518),
    ("Klang", "Selangor", 3.044, 101.445), ("Kuala Selangor", "Selangor", 3.340, 101.250),
    ("Seremban", "Negeri Sembilan", 2.725, 101.938), ("Melaka", "Melaka", 2.189, 102.250),
    ("Johor Bahru", "Johor", 1.493, 103.741), ("Muar", "Johor", 2.045, 102.568),
    ("Kuantan", "Pahang", 3.808, 103.326), ("Ipoh", "Perak", 4.597, 101.090),
    ("George Town", "Penang", 5.414, 100.329), ("Kuching", "Sarawak", 1.553, 110.359),
    ("Sibu", "Sarawak", 2.300, 111.820), ("Pekanbaru", "Riau, Indonesia", 0.507, 101.448),
    ("Palembang", "South Sumatra, Indonesia", -2.990, 104.756),
    ("Palangka Raya", "Central Kalimantan, Indonesia", -2.210, 113.920),
]

FRIENDLY = {
    "hot_zone_7": ("Fires in this zone this week", "n", "hotspots"),
    "hot_zone_30": ("Fires in this zone this month", "n", "hotspots"),
    "hot_zone_90": ("Fires in the past 3 months", "n", "hotspots"),
    "hot_zone_365": ("Fires in the past year", "n", "hotspots"),
    "days_since_fire": ("Days since this zone last burned", "n", "days"),
    "zone_month_fire_rate": ("Past years it burned in this month", "pct", ""),
    "hot_near_7": ("Fires within 80 km this week", "n", "hotspots"),
    "hot_near_1": ("Fires within 80 km today", "n", "hotspots"),
    "frp_zone_7": ("Fire intensity in this zone", "n", "MW"),
    "frp_near_7": ("Fire intensity nearby", "n", "MW"),
    "nino34_3m": ("El Niño index, last 3 months", "f", "°C"),
    "nino34_lag1": ("El Niño index, last month", "f", "°C"),
    "dmi_3m": ("Indian Ocean Dipole, 3 months", "f", ""),
    "dmi_lag1": ("Indian Ocean Dipole, last month", "f", ""),
    "deficit_mm": ("Water lost from the peat", "n", "mm"),
    "wt_est_cm": ("Estimated water table depth", "n", "cm"),
    "dry_days": ("Days in a row without rain", "n", "days"),
    "rain_7": ("Rain, past week", "n", "mm"), "rain_14": ("Rain, past 2 weeks", "n", "mm"),
    "rain_30": ("Rain, past month", "n", "mm"), "rain_60": ("Rain, past 2 months", "n", "mm"),
    "rain_90": ("Rain, past 3 months", "n", "mm"),
    "rain_30_anom": ("Rain vs normal, past month", "s", "mm"),
    "rain_90_anom": ("Rain vs normal, past 3 months", "s", "mm"),
    "deficit_mm_anom": ("Peat dryness vs normal", "s", "mm"),
    "rh_min_7_anom": ("Humidity vs normal", "s", "%"),
    "tmax_7_anom": ("Heat vs normal", "s", "°C"),
    "month_sin": ("Time of year", None, ""), "month_cos": ("Time of year", None, ""),
    "wind_max": ("Wind speed", "n", "km/h"), "rh_min": ("Afternoon humidity", "n", "%"),
    "rh_min_7": ("Humidity this week", "n", "%"), "tmax": ("Today's high temperature", "f", "°C"),
    "tmax_7": ("Heat this week", "f", "°C"), "et0_7": ("Evaporation this week", "n", "mm"),
    "deficit_change_7": ("Drying in the past week", "s", "mm"),
}


def clean(v, nd=1):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def place_for(z):
    towns = TOWNS.get(z["region"], [])
    if not towns:
        return z["region"]
    return min(towns, key=lambda t: (t[1] - z["lat"]) ** 2 + (t[2] - z["lon"]) ** 2)[0]


def fmt_value(f, v):
    label, kind, unit = FRIENDLY[f]
    if kind is None or v is None or (isinstance(v, float) and math.isnan(v)):
        return label, ""
    if kind == "pct":
        return label, f"{v:.0%}"
    if kind == "f":
        return label, f"{v:+.1f} {unit}".strip() if "Niño" in label or "Dipole" in label else f"{v:.1f} {unit}".strip()
    if kind == "s":
        return label, f"{v:+.0f} {unit}".strip()
    return label, f"{v:,.0f} {unit}".strip()


def drivers_for(r, top=4):
    c = r["_contrib"] or {}
    out, seen = [], set()
    for f, v in sorted(c.items(), key=lambda x: -x[1]):
        if v <= 0 or f not in FRIENDLY:
            continue
        label, val = fmt_value(f, r.get(f))
        if label in seen:
            continue
        seen.add(label)
        out.append([label, val])
        if len(out) == top:
            break
    return out


def export_today(a):
    scored, feats, status = pg.run(a, firms_key=os.environ.get("FIRMS_KEY"), live=True)
    as_of = pd.Timestamp(status["as_of"])
    zones = []
    for _, r in scored.iterrows():
        z = feats[(feats["zone_id"] == r["zone_id"]) &
                  (feats["date"] >= as_of - pd.Timedelta(days=PAST_DAYS))].sort_values("date")
        zones.append({
            "id": r["zone_id"], "region": r["region"], "country": r["country"],
            "place": place_for(r),
            "lat": clean(r["lat"], 3), "lon": clean(r["lon"], 3),
            "p": clean(r["p"], 4), "level": r["level"], "rank": int(r["rank"]),
            "model": r["model"],
            "category": r["category"], "reasons": list(r["reasons"] or []),
            "drivers": drivers_for(r),
            "action": r["action"], "smoke": bool(r["smoke_to_MY"]),
            "rising": bool(r.get("rising", False)),
            "wt": clean(r["wt_est_cm"]), "dryDays": int(r["dry_days"]) if pd.notna(r["dry_days"]) else None,
            "fires7": int(r["hot_zone_7"]) if pd.notna(r["hot_zone_7"]) else 0,
            "series": {
                "dates": z["date"].dt.strftime("%Y-%m-%d").tolist(),
                "wt": [clean(v) for v in z["wt_est_cm"]],
                "rain": [clean(v) for v in z["rain"]],
            },
        })
    hi = scored["level"] == "High"
    el = scored["level"] == "Elevated"
    out = {
        "generatedAt": datetime.now(MYT).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "asOf": status["as_of"],
        "sources": {"weather": status.get("weather"), "fires": status.get("fires"),
                    "firesThrough": a["info"].get("fire_end"),
                    "weatherThrough": a["info"].get("weather_end")},
        "summary": {"high": int(hi.sum()), "elevated": int(el.sum()),
                    "rising": int(scored.get("rising", pd.Series(False, index=scored.index)).sum()),
                    "burning": int((scored["hot_zone_7"] > 0).sum()),
                    "smoke": int((scored["smoke_to_MY"] & (hi | el)).sum())},
        "zones": zones,
    }
    (OUT / "today.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"today.json: {len(zones)} zones for {status['as_of']} "
          f"(weather {status.get('weather')}, fires {status.get('fires')}); "
          f"{out['summary']['high']} high, {out['summary']['elevated']} elevated")
    for k in ("weather_error", "fires_error"):
        if k in status:
            print(f"  note: {k}: {status[k]}")
    return zones


def export_air(zones):
    """Air quality now + next 3 days from Open-Meteo (CAMS global model), US AQI scale."""
    places = [{"name": n, "area": ar, "lat": la, "lon": lo, "kind": "city"} for n, ar, la, lo in AIR_PLACES]
    places += [{"name": z["id"], "area": f"near {z['place']}, {z['region']}", "lat": z["lat"], "lon": z["lon"],
                "kind": "zone"} for z in zones]
    out = []
    try:
        for b in range(0, len(places), 50):
            batch = places[b:b + 50]
            r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
                "latitude": ",".join(str(p["lat"]) for p in batch),
                "longitude": ",".join(str(p["lon"]) for p in batch),
                "current": "us_aqi,pm2_5", "hourly": "us_aqi,pm2_5",
                "forecast_days": 4, "timezone": "Asia/Kuala_Lumpur"}, timeout=60)
            r.raise_for_status()
            js = r.json()
            js = js if isinstance(js, list) else [js]
            for p, j in zip(batch, js):
                h = pd.DataFrame(j.get("hourly", {}))
                days = []
                if len(h):
                    h["day"] = h["time"].str[:10]
                    g = h.groupby("day")["us_aqi"].max().head(4)
                    days = [[d, clean(v, 0)] for d, v in g.items()]
                cur = j.get("current", {})
                out.append({**p, "aqi": clean(cur.get("us_aqi"), 0), "pm25": clean(cur.get("pm2_5"), 1),
                            "time": cur.get("time"), "days": days})
        (OUT / "air.json").write_text(json.dumps({
            "generatedAt": datetime.now(MYT).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "source": "Open-Meteo Air Quality API (CAMS global forecast), US AQI scale",
            "places": out}, separators=(",", ":"), ensure_ascii=False))
        print(f"air.json: {len(out)} places")
    except Exception as e:  # air quality is a bonus; never block the risk export
        print(f"air.json: skipped ({str(e)[:120]}); the app will fetch air quality live instead")


def export_metrics(a):
    m = a["metrics"]
    fy, uc = m["future_years"], m["unseen_country"]

    def pick(res):
        return {"model": res["model"]["patrol_catch"], "rule": res["simple_rule"]["patrol_catch"],
                "random": res["random_patrol_catch"],
                "newModel": res["model"]["new_fire"]["patrol_catch"],
                "newRule": res["simple_rule"]["new_fire"]["patrol_catch"],
                "precisionModel": res["model"]["alerts_2day"]["precision"],
                "precisionRule": res["simple_rule"]["alerts_2day"]["precision"],
                "rocModel": res["model"]["roc_auc"], "rocRule": res["simple_rule"]["roc_auc"],
                "newFires": res["model"]["new_fire"]["new_fires"],
                "warnedModel": res["model"]["new_fire"]["warned_share"],
                "rows": res["rows"], "fireRate": res["fire_rate"]}
    seen, drivers = set(), []
    for f, v in sorted(m["importance"]["ignition"].items(), key=lambda x: -x[1]):
        name = FRIENDLY.get(f, (None,))[0]
        if not name or name in seen:
            continue
        seen.add(name); drivers.append(name)
        if len(drivers) == 5:
            break
    static = 0
    sf = pg.M / "static_sources.csv"
    if sf.exists():
        static = max(0, sum(1 for _ in open(sf)) - 1)
    out = {"testStart": m["test_start"], "patrols": m["patrols_per_day"],
           "futureYears": pick(fy), "unseenCountry": pick(uc), "drivers": drivers,
           "staticSources": static, "zones": 71, "trainStart": "2015-01-01",
           "featureCount": len(m["features"]["spread"])}
    (OUT / "metrics.json").write_text(json.dumps(out, indent=1))
    print(f"metrics.json: model {fy['model']['patrol_catch']:.0%} vs rule "
          f"{fy['simple_rule']['patrol_catch']:.0%} (new fires {fy['model']['new_fire']['patrol_catch']:.0%} "
          f"vs {fy['simple_rule']['new_fire']['patrol_catch']:.0%})")


def export_replay(a):
    ds_file = ROOT / "data" / "dataset.csv.gz"
    if not ds_file.exists():
        print("replay.json: skipped (data/dataset.csv.gz not here); keeping the existing file")
        return
    n_top = a["metrics"]["patrols_per_day"]
    zones = pd.DataFrame(pg.build_zones())[["zone_id", "lat", "lon", "region"]]
    ts = pd.read_csv(pg.M / "test_scores.csv.gz", parse_dates=["date"])
    ds = pd.read_csv(ds_file, usecols=["zone_id", "date", "dry_days", "deficit_mm"], parse_dates=["date"])
    df = ts.merge(ds, on=["zone_id", "date"], how="left").merge(zones, on="zone_id")
    df["rule"] = df["dry_days"].fillna(0) + df["deficit_mm"].fillna(0) / 1000.0
    days = []
    for d, g in df.groupby("date"):
        burned = g["fire_next7"] == 1
        top_m = g.nlargest(n_top, "p")
        top_r = g.nlargest(n_top, "rule")
        days.append({
            "d": d.strftime("%Y-%m-%d"), "b": int(burned.sum()),
            "m": int(top_m["fire_next7"].sum()), "r": int(top_r["fire_next7"].sum()),
            "n": int(len(g)),
            "top": [[row.zone_id, place_for({"region": row.region, "lat": row.lat, "lon": row.lon}),
                     row.region, round(float(row.p), 3), int(row.fire_next7)]
                    for row in top_m.head(3).itertuples()],
        })
    dd = pd.DataFrame(days)
    dd["random"] = dd["b"] * n_top / dd["n"]
    # Featured days: where PeatGuard beat BOTH the rule and random patrols by the widest margin.
    dd["edge"] = dd["m"] - np.maximum(dd["r"], dd["random"])
    dd["year"] = dd["d"].str[:4]
    cand = dd[(dd["m"] > dd["r"]) & (dd["m"] > dd["random"])]
    picks = (cand.sort_values(["edge", "m"], ascending=False).groupby("year").head(1)
             .sort_values(["edge", "m"], ascending=False).head(3).sort_values("d")["d"].tolist())
    out = {"patrols": n_top, "featured": picks, "days": days}
    (OUT / "replay.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"replay.json: {len(days)} days, featured {picks}")


def export_impact(a):
    """Measured on the test years: what PeatGuard's ranking saves compared with the dry-days rule."""
    ds_file = ROOT / "data" / "dataset.csv.gz"
    if not ds_file.exists():
        print("impact.json: skipped (data/dataset.csv.gz not here); keeping the existing file")
        return
    n_top = a["metrics"]["patrols_per_day"]
    ts = pd.read_csv(pg.M / "test_scores.csv.gz", parse_dates=["date"])
    ds = pd.read_csv(ds_file, usecols=["zone_id", "date", "dry_days", "deficit_mm"], parse_dates=["date"])
    df = ts.merge(ds, on=["zone_id", "date"], how="left")
    df["rule"] = df["dry_days"].fillna(0) + df["deficit_mm"].fillna(0) / 1000.0
    total = df["fire_next7"].sum()
    n_days = df["date"].nunique()
    max_n = int(df.groupby("date")["zone_id"].nunique().max())
    # Rank of each area on each day under each method (1 = patrol first).
    df["rank_m"] = df.groupby("date")["p"].rank(ascending=False, method="first")
    df["rank_r"] = df.groupby("date")["rule"].rank(ascending=False, method="first")
    hits = df[df["fire_next7"] == 1]
    curve_m = [float((hits["rank_m"] <= n).sum() / total) for n in range(1, max_n + 1)]
    curve_r = [float((hits["rank_r"] <= n).sum() / total) for n in range(1, max_n + 1)]
    target = curve_m[n_top - 1]
    rule_needed = next((n for n, c in enumerate(curve_r, 1) if c >= target), max_n)
    per_year = 365.0 / n_days
    hits_m = float((hits["rank_m"] <= n_top).sum() * per_year)
    hits_r = float((hits["rank_r"] <= n_top).sum() * per_year)
    out = {
        "patrols": n_top, "testDays": int(n_days), "testStart": str(df["date"].min().date()),
        "testEnd": str(df["date"].max().date()),
        "ruleNeeded": int(rule_needed),
        "extraPatrolDaysPerYear": round((rule_needed - n_top) * 365),
        "usefulVisitsPerYear": {"model": round(hits_m), "rule": round(hits_r), "extra": round(hits_m - hits_r)},
        "curve": {"model": [round(c, 4) for c in curve_m], "rule": [round(c, 4) for c in curve_r]},
        "co2PerHa": [1500, 3300],
        "co2Source": "Severe peat fires release 400 to 900 tonnes of carbon per hectare (Wan Nawang et al., 2026, Fire Ecology); x3.67 to CO2.",
    }
    (OUT / "impact.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"impact.json: rule needs {rule_needed} patrols/day to match PeatGuard's {n_top}; "
          f"{out['usefulVisitsPerYear']['extra']} extra useful patrol visits a year")


def main():
    a = pg.load_artifacts()
    export_metrics(a)
    export_replay(a)
    export_impact(a)
    zones = export_today(a)
    export_air(zones)


if __name__ == "__main__":
    main()
