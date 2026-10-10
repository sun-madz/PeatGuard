"""Feature engineering shared by training (history) and the live app (forecast).

Using the same code for both guarantees the model sees identical inputs.
"""
import numpy as np
import pandas as pd

from config import SPECIFIC_YIELD

DEFICIT_CAP_MM = 400.0   # deepest dryness the bucket can reach
RAIN_DAY_MM = 1.0        # a day with less than this counts as dry
NEAR_DEG = 0.75          # "nearby" radius for hotspot counts (~80 km)

# Values compared against each zone's normal for that month ("anomalies").
# Malaysia and Indonesia have different normal rainfall, so "drier than usual here"
# is a far better drought signal than raw millimetres.
ANOM_BASE = ["rain_30", "rain_90", "deficit_mm", "rh_min_7", "tmax_7"]

WEATHER_FEATURES = [
    "rain_7", "rain_14", "rain_30", "rain_60", "rain_90",
    "dry_days",
    "deficit_mm", "deficit_change_7", "wt_est_cm",
    "tmax", "tmax_7", "rh_min", "rh_min_7",
    "wind_max", "et0_7",
    "month_sin", "month_cos",
] + [f"{c}_anom" for c in ANOM_BASE]

# Ocean-climate drivers of regional drought (last month's value and 3-month average,
# so only information available at prediction time is used).
CLIMATE_FEATURES = ["nino34_lag1", "nino34_3m", "dmi_lag1", "dmi_3m"]

FIRE_FEATURES = [
    "hot_zone_7", "hot_zone_30", "hot_zone_90", "hot_zone_365",
    "days_since_fire", "zone_month_fire_rate",
    "frp_zone_7", "hot_near_7", "hot_near_1", "frp_near_7",
]

FEATURES = WEATHER_FEATURES + CLIMATE_FEATURES + FIRE_FEATURES   # spread model
# Ignition rows have no fire in the zone this week, so the zone's 7-day counts are always 0.
IGNITION_FEATURES = [f for f in FEATURES if f not in ("hot_zone_7", "frp_zone_7")]

RENAME = {
    "precipitation_sum": "rain",
    "temperature_2m_max": "tmax",
    "wind_speed_10m_max": "wind_max",
    "wind_direction_10m_dominant": "wind_dir",
    "et0_fao_evapotranspiration": "et0",
}


def rh_from_dewpoint(dewpoint_c, tmax_c):
    """Relative humidity (%) at the day's maximum temperature, from dew point (Magnus formula).
    This approximates the day's minimum humidity."""
    def es(t):
        return 6.112 * np.exp(17.67 * t / (t + 243.5))
    return np.clip(100.0 * es(np.asarray(dewpoint_c, float)) / es(np.asarray(tmax_c, float)), 0, 100)


def et0_hargreaves(tmax, tmin, lat_deg, doy):
    """Reference evaporation (mm/day), Hargreaves-Samani (FAO-56 eq. 52).
    Needs only temperatures and latitude, so history and forecast use the same formula."""
    tmax, tmin, doy = (np.asarray(x, float) for x in (tmax, tmin, doy))
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))
    tmean = (tmax + tmin) / 2
    return 0.0023 * 0.408 * ra * (tmean + 17.8) * np.sqrt(np.clip(tmax - tmin, 0, None))


def _dry_run_length(rain):
    """Consecutive dry days up to and including each day."""
    out, n = np.zeros(len(rain)), 0
    for i, r in enumerate(rain):
        n = n + 1 if (np.isnan(r) or r < RAIN_DAY_MM) else 0
        out[i] = n
    return out


def _deficit(rain, et0, start=0.0):
    """Simple peat water-balance bucket: dryness grows with evaporation, shrinks with rain."""
    out, d = np.zeros(len(rain)), start
    for i, (r, e) in enumerate(zip(rain, et0)):
        r = 0.0 if np.isnan(r) else r
        e = 0.0 if np.isnan(e) else e
        d = min(DEFICIT_CAP_MM, max(0.0, d + e - r))
        out[i] = d
    return out


def weather_features(w, start_deficit=0.0):
    """w: one zone's daily weather, sorted by date. Returns w with weather features added."""
    w = w.rename(columns=RENAME).sort_values("date").reset_index(drop=True).copy()
    w["date"] = pd.to_datetime(w["date"])
    for col in ["rain", "et0", "tmax", "rh_min", "wind_max"]:
        if col not in w:
            w[col] = np.nan
    w["rain_7"] = w["rain"].rolling(7, min_periods=1).sum()
    w["rain_14"] = w["rain"].rolling(14, min_periods=1).sum()
    w["rain_30"] = w["rain"].rolling(30, min_periods=1).sum()
    w["rain_60"] = w["rain"].rolling(60, min_periods=1).sum()
    w["rain_90"] = w["rain"].rolling(90, min_periods=1).sum()
    w["dry_days"] = _dry_run_length(w["rain"].to_numpy())
    w["deficit_mm"] = _deficit(w["rain"].to_numpy(), w["et0"].to_numpy(), start_deficit)
    w["deficit_change_7"] = w["deficit_mm"] - w["deficit_mm"].shift(7)
    # mm of water lost / specific yield = how far the water table fell (mm -> cm)
    w["wt_est_cm"] = w["deficit_mm"] / 10.0 / SPECIFIC_YIELD
    w["tmax_7"] = w["tmax"].rolling(7, min_periods=1).mean()
    w["rh_min_7"] = w["rh_min"].rolling(7, min_periods=1).mean()
    w["et0_7"] = w["et0"].rolling(7, min_periods=1).sum()
    m = w["date"].dt.month
    w["month_sin"] = np.sin(2 * np.pi * m / 12)
    w["month_cos"] = np.cos(2 * np.pi * m / 12)
    return w


def zone_of(lat, lon, zones, half):
    """Map points to zone ids (or None) using the zone grid cells."""
    zl = np.array([z["lat"] for z in zones])
    zo = np.array([z["lon"] for z in zones])
    ids = np.array([z["zone_id"] for z in zones], dtype=object)
    out = np.full(len(lat), None, dtype=object)
    for i in range(len(zones)):
        m = (np.abs(lat - zl[i]) <= half) & (np.abs(lon - zo[i]) <= half)
        out[m] = ids[i]
    return out


def hotspot_counts(hot, zones, half):
    """Daily hotspot counts and fire power per zone: inside the zone cell, and within
    NEAR_DEG of its centre.

    hot: DataFrame with latitude, longitude, date (datetime) and optionally frp.
    Returns a dict of four DataFrames (indexed by date, one column per zone_id):
      inside, near (hotspot counts), frp_in, frp_near (summed fire radiative power, MW).
    """
    lat, lon = hot["latitude"].to_numpy(), hot["longitude"].to_numpy()
    days = pd.DatetimeIndex(hot["date"])
    frp = hot["frp"].fillna(0).to_numpy() if "frp" in hot else np.ones(len(hot))
    out = {"inside": {}, "near": {}, "frp_in": {}, "frp_near": {}}
    for z in zones:
        m_in = (np.abs(lat - z["lat"]) <= half) & (np.abs(lon - z["lon"]) <= half)
        m_nr = np.hypot(lat - z["lat"], lon - z["lon"]) <= NEAR_DEG
        zid = z["zone_id"]
        out["inside"][zid] = pd.Series(1.0, index=days[m_in]).groupby(level=0).sum()
        out["near"][zid] = pd.Series(1.0, index=days[m_nr]).groupby(level=0).sum()
        out["frp_in"][zid] = pd.Series(frp[m_in], index=days[m_in]).groupby(level=0).sum()
        out["frp_near"][zid] = pd.Series(frp[m_nr], index=days[m_nr]).groupby(level=0).sum()
    return {k: pd.DataFrame(v).fillna(0) for k, v in out.items()}


def _zone_series(table, zone_id, full):
    s = table.get(zone_id, pd.Series(dtype=float)) if isinstance(table, pd.DataFrame) else pd.Series(dtype=float)
    return s.reindex(full, fill_value=0).astype(float)


def zone_month_fire_rate(zin_daily, min_hotspots):
    """Share of PREVIOUS years in which this zone burned (>= min_hotspots) in each calendar month.
    Uses only earlier years, so there is no peeking at the future. Returns {(year, month): rate}."""
    monthly = zin_daily.resample("MS").sum()
    burned = (monthly >= min_hotspots).astype(float)
    df = pd.DataFrame({"burned": burned.to_numpy(), "year": monthly.index.year,
                       "month": monthly.index.month})
    df["rate"] = df.groupby("month")["burned"].transform(lambda s: s.shift(1).expanding().mean())
    return {(y, m): r for y, m, r in zip(df["year"], df["month"], df["rate"])}


def add_fire_features(w, zone_id, counts, min_hotspots=3):
    """Add past-hotspot features for one zone (using data up to and including each day)."""
    idx = pd.DatetimeIndex(w["date"])
    # Use the zone's whole fire history (as in training), at least one year back.
    starts = [idx.min() - pd.Timedelta(days=365)]
    if isinstance(counts.get("inside"), pd.DataFrame) and len(counts["inside"]):
        starts.append(pd.Timestamp(counts["inside"].index.min()))
    full = pd.date_range(min(starts), idx.max())
    zin = _zone_series(counts["inside"], zone_id, full)
    znr = _zone_series(counts["near"], zone_id, full)
    fin = _zone_series(counts["frp_in"], zone_id, full)
    fnr = _zone_series(counts["frp_near"], zone_id, full)
    w = w.copy()
    for n in (7, 30, 90, 365):
        w[f"hot_zone_{n}"] = zin.rolling(n, min_periods=1).sum().reindex(idx).to_numpy()
    w["hot_near_7"] = znr.rolling(7, min_periods=1).sum().reindex(idx).to_numpy()
    w["hot_near_1"] = znr.reindex(idx).to_numpy()
    w["frp_zone_7"] = fin.rolling(7, min_periods=1).sum().reindex(idx).to_numpy()
    w["frp_near_7"] = fnr.rolling(7, min_periods=1).sum().reindex(idx).to_numpy()
    # Days since the last hotspot in the zone (capped at 2 years).
    pos = pd.Series(np.arange(len(full), dtype=float), index=full)
    last = pos.where(zin > 0).ffill()
    w["days_since_fire"] = (pos - last).fillna(730).clip(upper=730).reindex(idx).to_numpy()
    rate = zone_month_fire_rate(zin, min_hotspots)
    w["zone_month_fire_rate"] = [rate.get((d.year, d.month), np.nan) for d in idx]
    w["hot_zone_1"] = zin.reindex(idx).to_numpy()   # today's count (for event analysis, not a feature)
    return w


def add_climate(df, climate):
    """Add El Nino (Nino 3.4) and Indian Ocean Dipole features.
    climate: DataFrame with year, month, nino34, dmi (monthly). Uses last month and the
    3 months before the prediction month; the latest known value is carried forward."""
    dates = pd.to_datetime(df["date"])
    per = pd.PeriodIndex(climate["year"].astype(int).astype(str) + "-" +
                         climate["month"].astype(int).astype(str), freq="M")
    end = max(per.max(), dates.max().to_period("M"))
    rng = pd.period_range(per.min(), end, freq="M")
    out = df.copy()
    for col in ("nino34", "dmi"):
        s = pd.Series(climate[col].to_numpy(), index=per).groupby(level=0).last()
        s = s.reindex(rng).ffill()
        lag1, avg3 = s.shift(1), s.shift(1).rolling(3, min_periods=1).mean()
        p = dates.dt.to_period("M")
        out[f"{col}_lag1"] = lag1.reindex(p).to_numpy()
        out[f"{col}_3m"] = avg3.reindex(p).to_numpy()
    return out


def climatology(df):
    """Each zone's normal value per calendar month (use training years only)."""
    d = df.assign(month=pd.to_datetime(df["date"]).dt.month)
    return d.groupby(["zone_id", "month"])[ANOM_BASE].mean().add_suffix("_norm").reset_index()


def add_anomalies(df, clim):
    """Add <feature>_anom = value minus that zone's normal for the month."""
    d = df.assign(month=pd.to_datetime(df["date"]).dt.month).merge(
        clim, on=["zone_id", "month"], how="left")
    for c in ANOM_BASE:
        d[f"{c}_anom"] = d[c] - d[f"{c}_norm"]
    return d.drop(columns=["month"] + [f"{c}_norm" for c in ANOM_BASE])
