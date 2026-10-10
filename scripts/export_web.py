"""Export PeatGuard predictions as small JSON files for the web app (web/data/).

Run from the project root:
    python scripts/export_web.py

Writes:
  web/data/today.json    today's risk for all 71 zones (live weather + satellite fires)
  web/data/metrics.json  the proof numbers from training
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import peatguard as pg  # noqa: E402

OUT = ROOT / "web" / "data"
OUT.mkdir(parents=True, exist_ok=True)
MYT = timezone(timedelta(hours=8))
PAST_DAYS = 60

FRIENDLY = {
    "hot_zone_7": "Fires in the zone this week", "hot_zone_30": "Fires in the zone this month",
    "hot_zone_90": "Fires in the past 3 months", "hot_zone_365": "Fires in the past year",
    "days_since_fire": "Days since the zone last burned",
    "zone_month_fire_rate": "How often it burns in this month",
    "hot_near_7": "Fires within 80 km this week", "hot_near_1": "Fires within 80 km today",
    "frp_zone_7": "Fire intensity in the zone", "frp_near_7": "Fire intensity nearby",
    "nino34_3m": "El Niño, last 3 months", "nino34_lag1": "El Niño, last month",
    "dmi_3m": "Indian Ocean Dipole, 3 months", "dmi_lag1": "Indian Ocean Dipole, last month",
    "deficit_mm": "How dry the peat is", "wt_est_cm": "Estimated water table",
    "dry_days": "Days without rain", "rain_30": "Rain, past month", "rain_60": "Rain, past 2 months",
    "rain_90": "Rain, past 3 months", "rain_14": "Rain, past 2 weeks", "rain_7": "Rain, past week",
    "month_sin": "Time of year", "month_cos": "Time of year", "wind_max": "Wind speed",
    "rh_min": "Afternoon humidity", "tmax_7": "Heat this week", "tmax": "Today's heat",
    "rain_30_anom": "Rain vs normal, past month", "rain_90_anom": "Rain vs normal, 3 months",
    "deficit_mm_anom": "Peat dryness vs normal", "rh_min_7_anom": "Humidity vs normal",
    "tmax_7_anom": "Heat vs normal", "rh_min_7": "Humidity this week", "et0_7": "Evaporation this week",
    "deficit_change_7": "Drying in the past week",
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


def export_today(a):
    scored, feats, status = pg.run(a, firms_key=os.environ.get("FIRMS_KEY"), live=True)
    as_of = pd.Timestamp(status["as_of"])
    zones = []
    for _, r in scored.iterrows():
        z = feats[(feats["zone_id"] == r["zone_id"]) &
                  (feats["date"] >= as_of - pd.Timedelta(days=PAST_DAYS))].sort_values("date")
        zones.append({
            "id": r["zone_id"], "region": r["region"], "country": r["country"],
            "lat": clean(r["lat"], 3), "lon": clean(r["lon"], 3),
            "p": clean(r["p"], 4), "level": r["level"], "rank": int(r["rank"]),
            "category": r["category"], "reasons": list(r["reasons"] or []),
            "action": r["action"], "smoke": bool(r["smoke_to_MY"]),
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
                    "firesThrough": a["info"].get("fire_end")},
        "summary": {"high": int(hi.sum()), "elevated": int(el.sum()),
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
                "newFires": res["model"]["new_fire"]["new_fires"],
                "warnedModel": res["model"]["new_fire"]["warned_share"]}
    seen, drivers = set(), []
    for f, v in sorted({**m["importance"]["ignition"]}.items(), key=lambda x: -x[1]):
        name = FRIENDLY.get(f)
        if not name:
            continue
        if name not in seen:
            seen.add(name); drivers.append(name)
        if len(drivers) == 5:
            break
    out = {"testStart": m["test_start"], "patrols": m["patrols_per_day"],
           "futureYears": pick(fy), "unseenCountry": pick(uc), "drivers": drivers}
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
    ts = pd.read_csv(pg.M / "test_scores.csv.gz", parse_dates=["date"])
    ds = pd.read_csv(ds_file, usecols=["zone_id", "date", "dry_days", "deficit_mm", "region"],
                     parse_dates=["date"])
    df = ts.merge(ds, on=["zone_id", "date"], how="left")
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
            "top": [[row.zone_id, row.region, round(float(row.p), 3), int(row.fire_next7)]
                    for row in top_m.head(3).itertuples()],
        })
    dd = pd.DataFrame(days)
    dd["year"] = dd["d"].str[:4]
    picks = (dd[dd["b"] > 0].sort_values("b", ascending=False)
             .groupby("year").head(1).sort_values("d")["d"].tolist())
    out = {"patrols": n_top, "featured": picks, "days": days}
    (OUT / "replay.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"replay.json: {len(days)} days, featured {picks}")


def main():
    a = pg.load_artifacts()
    export_metrics(a)
    export_replay(a)
    export_today(a)


if __name__ == "__main__":
    main()
