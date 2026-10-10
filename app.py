"""PeatGuard - peat-fire early warning for Malaysia and Indonesia.

Run locally:  streamlit run app.py
"""
import hashlib
import json

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import peatguard as pg
from config import DANGER_WATER_TABLE_CM

st.set_page_config(page_title="PeatGuard", page_icon="🔥", layout="wide")

LEVEL_COLOR = {"High": [214, 39, 40, 190], "Elevated": [255, 159, 28, 170], "Low": [46, 160, 67, 60]}
MAP_STYLE = getattr(getattr(pdk, "map_styles", None), "CARTO_LIGHT", "light")


# ------------------------------------------------------------------ data


@st.cache_resource
def artifacts():
    return pg.load_artifacts()


def firms_key():
    try:
        return st.secrets.get("FIRMS_KEY")
    except Exception:
        return None


@st.cache_data(ttl=3 * 3600, show_spinner="Fetching live weather and satellite hotspots...")
def today_view(key):
    return pg.run(artifacts(), firms_key=key, live=True)


@st.cache_data
def test_scores():
    t = pd.read_csv(pg.M / "test_scores.csv.gz", parse_dates=["date"])
    return t.merge(artifacts()["zones"], on="zone_id")


a = artifacts()
M = a["metrics"]
scored, feats, status = today_view(firms_key())
zones = a["zones"]


def zone_map(df, color_col, tooltip, height=480):
    d = df.copy()
    d["polygon"] = [pg.cell_polygon(la, lo) for la, lo in zip(d["lat"], d["lon"])]
    layer = pdk.Layer("PolygonLayer", d, get_polygon="polygon", get_fill_color=color_col,
                      get_line_color=[80, 80, 80, 120], line_width_min_pixels=1, pickable=True)
    layers = [layer]
    if "burned" in d:
        b = d[d["burned"]]
        layers.append(pdk.Layer("ScatterplotLayer", b, get_position=["lon", "lat"],
                                get_radius=9000, get_fill_color=[20, 20, 20, 230]))
    view = pdk.ViewState(latitude=0.8, longitude=107.5, zoom=4.4)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style=MAP_STYLE,
                             tooltip={"text": tooltip}), height=height)


# ------------------------------------------------------------------ header

st.title("🔥 PeatGuard")
st.caption("AI early warning for peat fires, the source of Southeast Asia's haze. "
           "Ranks 71 peatland zones in Malaysia and Indonesia by fire risk for the next 7 days, "
           "explains why, and says what to do.")

src = (f"Risk as of **{status['as_of']}** · weather: **{status['weather']}** · "
       f"satellite hotspots: **{status['fires']}** (latest {a['info']['fire_end']})")
st.markdown(src)
if status["weather"] != "live":
    st.info("Live weather could not be reached just now, so this view uses the latest stored data.")

tab_today, tab_replay, tab_proof, tab_iot = st.tabs(
    ["Today's risk", "Replay 2023–2026", "Proof it works", "IoT sensor upgrade"])

# ------------------------------------------------------------------ TODAY

with tab_today:
    n_high = int((scored["level"] == "High").sum())
    n_elev = int((scored["level"] == "Elevated").sum())
    n_active = int((scored["hot_zone_7"] > 0).sum())
    n_smoke = int((scored["smoke_to_MY"] & scored["level"].isin(["High", "Elevated"])).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("High-risk zones", n_high)
    c2.metric("Elevated-risk zones", n_elev)
    c3.metric("Zones with fire this week", n_active)
    c4.metric("Risky zones with smoke blowing toward Malaysia", n_smoke)

    left, right = st.columns([3, 2])
    with left:
        m = scored.assign(color=scored["level"].map(LEVEL_COLOR),
                          pct=(scored["p"] * 100).round(0).astype(int))
        zone_map(m, "color", "{zone_id} ({region})\n{level} risk: {pct}% chance of fire this week\n{category}")
        st.caption("Red = high, orange = elevated, green = low. Each square is a ~55 km zone.")
    with right:
        st.subheader(f"Today's patrol list (top {M['patrols_per_day']})")
        top = scored.head(M["patrols_per_day"])
        st.dataframe(pd.DataFrame({
            "#": top["rank"], "Zone": top["zone_id"], "Region": top["region"],
            "Fire chance": (top["p"] * 100).round(0).astype(int).astype(str) + "%",
            "Level": top["level"], "Type": top["category"],
            "Smoke → MY": np.where(top["smoke_to_MY"], "yes", ""),
        }), hide_index=True, use_container_width=True, height=390)
        st.caption("Priority = chance of fire × people nearby × whether smoke would blow toward Malaysia.")

    st.divider()
    st.subheader("Zone details")
    pick = st.selectbox("Choose a zone", scored["zone_id"],
                        format_func=lambda z: f"{z} · {scored.set_index('zone_id').loc[z, 'region']}")
    r = scored.set_index("zone_id").loc[pick]
    d1, d2 = st.columns([2, 3])
    with d1:
        st.markdown(f"### {pick}: **{r['level']} risk**")
        st.markdown(f"**{r['p']:.0%}** chance of a fire (3+ hotspots) in the next 7 days · "
                    f"priority **#{r['rank']}**")
        st.markdown(f"**Type:** {r['category']}")
        st.markdown("**Why:**")
        for s_ in (r["reasons"] or ["No strong warning signs."]):
            st.markdown(f"- {s_}")
        st.markdown(f"**What to do:** {r['action']}")
        if r["smoke_to_MY"]:
            st.warning("Today's wind would carry smoke from this zone toward Malaysia.")
    with d2:
        z = feats[feats["zone_id"] == pick].copy()
        z = z[z["date"] >= z["date"].max() - pd.Timedelta(days=120)]
        z["kind"] = np.where(z["date"] > pd.Timestamp(status["as_of"]), "forecast", "observed")
        wt = alt.Chart(z).mark_line().encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("wt_est_cm:Q", title="Estimated water table depth (cm)", scale=alt.Scale(reverse=True)),
            strokeDash=alt.StrokeDash("kind:N", legend=alt.Legend(title=None)))
        danger = alt.Chart(pd.DataFrame({"y": [DANGER_WATER_TABLE_CM]})).mark_rule(
            color="#d62728", strokeDash=[4, 4]).encode(y="y:Q")
        rain = alt.Chart(z).mark_bar(opacity=0.6).encode(
            x=alt.X("date:T", title=None), y=alt.Y("rain:Q", title="Daily rain (mm)"),
            color=alt.Color("kind:N", legend=None))
        st.altair_chart((wt + danger).properties(height=220), use_container_width=True)
        st.altair_chart(rain.properties(height=150), use_container_width=True)
        st.caption(f"Water table is estimated from rainfall minus evaporation (dashed red line = "
                   f"{DANGER_WATER_TABLE_CM} cm danger line; lower on the chart = drier). "
                   "IoT sensors would measure it directly; see the IoT tab.")

# ------------------------------------------------------------------ REPLAY

with tab_replay:
    st.subheader("Replay: what PeatGuard would have said on any day from 2023 to 2026")
    st.caption("These years were never used for training. Black dots = zones that really "
               "burned (3+ hotspots) in the following 7 days.")
    ts = test_scores()
    busiest = ts.groupby("date")["fire_next7"].sum().idxmax()
    day = st.slider("Day", min_value=ts["date"].min().date(), max_value=ts["date"].max().date(),
                    value=busiest.date(), format="YYYY-MM-DD")
    d = ts[ts["date"] == pd.Timestamp(day)].copy()
    d["rank"] = d["p"].rank(ascending=False, method="first")
    d["top"] = d["rank"] <= M["patrols_per_day"]
    d["burned"] = d["fire_next7"] == 1
    d["pct"] = (d["p"] * 100).round(0).astype(int)
    d["color"] = [[214, 39, 40, 200] if t else [255, 159, 28, int(40 + 150 * p)]
                  for t, p in zip(d["top"], d["p"])]
    zone_map(d, "color", "{zone_id}: {pct}% fire chance", height=430)
    caught, burned = int((d["top"] & d["burned"]).sum()), int(d["burned"].sum())
    rnd = burned * M["patrols_per_day"] / max(len(d), 1)
    c1, c2, c3 = st.columns(3)
    c1.metric("Zones that burned in the next 7 days", burned)
    c2.metric("Caught by PeatGuard's top 10 (red)", caught)
    c3.metric("Expected from 10 random patrols", f"{rnd:.1f}")

# ------------------------------------------------------------------ PROOF

with tab_proof:
    fy, uc = M["future_years"], M["unseen_country"]
    st.subheader("Does it help someone make a better decision? Yes, and here is the proof.")
    st.markdown(
        "**The decision:** a fire agency can only patrol a few zones a day. Which ones?  \n"
        "**The test:** train on 2015–2022, then test on **2023–2026**, years the model never saw. "
        "Compare checking PeatGuard's top 10 zones each day against today's rule of thumb "
        "(most dry days in a row) and against random patrols.")
    rows = []
    for test, res in (("Future years (all zones)", fy), ("Unseen country (Indonesia → Malaysia)", uc)):
        for what, key in (("All fires", None), ("New fires only", "new_fire")):
            for method, mk in (("PeatGuard", "model"), ("Simple rule", "simple_rule")):
                v = res[mk][key]["patrol_catch"] if key else res[mk]["patrol_catch"]
                rows.append({"test": test, "fires": what, "method": method, "caught": v})
            if not key:
                rows.append({"test": test, "fires": what, "method": "Random",
                             "caught": res["random_patrol_catch"]})
    pr = pd.DataFrame(rows)
    order = ["PeatGuard", "Simple rule", "Random"]
    palette = alt.Scale(domain=order, range=["#d62728", "#7f7f7f", "#c7c7c7"])
    for test in pr["test"].unique():
        st.markdown(f"**{test}**")
        cols = st.columns(2)
        for col, what in zip(cols, ["All fires", "New fires only"]):
            sub = pr[(pr["test"] == test) & (pr["fires"] == what)]
            bars = alt.Chart(sub).mark_bar().encode(
                x=alt.X("method:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("caught:Q", axis=alt.Axis(format="%"), title="Fires caught",
                        scale=alt.Scale(domain=[0, 1])),
                color=alt.Color("method:N", scale=palette, legend=None))
            labels = bars.mark_text(dy=-8).encode(text=alt.Text("caught:Q", format=".0%"))
            col.altair_chart((bars + labels).properties(title=what, height=220),
                             use_container_width=True)

    def pct(x):
        return f"{x:.0%}"
    st.markdown("#### Key numbers (test years 2023–2026)")
    st.dataframe(pd.DataFrame({
        "Measure": ["Ranking quality, all fires (ROC AUC)", "Fires caught with 10 patrols/day",
                    "New fires caught with 10 patrols/day", "Ranking quality, new fires (ROC AUC)",
                    "Alerts that were real (precision, 2-day rule)",
                    "New fires flagged in the week before"],
        "PeatGuard": [f"{fy['model']['roc_auc']:.2f}", pct(fy['model']['patrol_catch']),
                      pct(fy['model']['new_fire']['patrol_catch']), f"{fy['model']['new_fire']['roc_auc']:.2f}",
                      pct(fy['model']['alerts_2day']['precision']), pct(fy['model']['new_fire']['warned_share'])],
        "Simple rule": [f"{fy['simple_rule']['roc_auc']:.2f}", pct(fy['simple_rule']['patrol_catch']),
                        pct(fy['simple_rule']['new_fire']['patrol_catch']), f"{fy['simple_rule']['new_fire']['roc_auc']:.2f}",
                        pct(fy['simple_rule']['alerts_2day']['precision']), pct(fy['simple_rule']['new_fire']['warned_share'])],
    }), hide_index=True, use_container_width=True)

    st.markdown("#### What the models rely on")
    c1, c2 = st.columns(2)
    for col, kind, title in ((c1, "spread", "Spread model (fire already nearby)"),
                             (c2, "ignition", "Ignition model (quiet zones, new fires)")):
        imp = pd.Series(M["importance"][kind]).head(8).rename("share").reset_index()
        col.markdown(f"**{title}**")
        col.altair_chart(alt.Chart(imp).mark_bar(color="#d62728").encode(
            x=alt.X("share:Q", axis=alt.Axis(format="%"), title=None),
            y=alt.Y("index:N", sort="-x", title=None)).properties(height=220), use_container_width=True)

    with st.expander("How it works, and its limits"):
        st.markdown(f"""
- **Data:** NASA FIRMS satellite fire hotspots (VIIRS, 2015–now), NASA POWER daily weather,
  NOAA El Niño (Niño 3.4) and Indian Ocean Dipole indices. Live mode adds the Open-Meteo forecast.
- **Cleaning:** low-confidence detections removed; 469 static heat sources (factories, flares) removed;
  a zone counts as burning only with {3}+ hotspots in a week.
- **Two models (LightGBM):** *spread* for zones already burning, *ignition* for quiet zones,
  so the early-warning model cannot rely on "there is already a fire here".
- **Honest testing:** trained on 2015–2022, tested once on 2023–2026; a separate copy trained only
  on Indonesia and tested only on Malaysia. Alert thresholds set on 2022, never on the test years.
- **Limits:** zones are ~55 km, so it says where to patrol, not which field is burning. Weather and
  water table are estimated, not measured. That is exactly what IoT sensors fix.
""")

# ------------------------------------------------------------------ IoT

with tab_iot:
    st.subheader("From satellite estimates to ground truth: the IoT upgrade")
    st.markdown(
        "Today PeatGuard **estimates** how dry the peat is and **waits** for satellites to see fire. "
        "Ground sensors let it **measure** the fuel and **catch fire underground**, before any "
        "satellite can.")
    st.graphviz_chart("""
digraph { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#fff5f0", fontname=Helvetica];
  s1 [label="Water-table sensor\\n(peat dryness)"]; s2 [label="Soil temperature\\n20 cm deep"];
  s3 [label="CO gas sensor\\n(smoke)"]; mcu [label="ESP32 node\\nsolar powered"];
  gw [label="LoRaWAN gateway\\n(km range, low power)"]; cloud [label="Cloud\\n(MQTT + database)"];
  sat [label="Satellite hotspots\\n+ weather + El Niño"]; model [label="PeatGuard AI\\nrisk + reasons", fillcolor="#fde0dd"];
  out [label="Patrol list, SMS alerts,\\ndashboard"];
  s1 -> mcu; s2 -> mcu; s3 -> mcu; mcu -> gw [label="LoRa"]; gw -> cloud [label="4G"];
  cloud -> model; sat -> model; model -> out; }""")

    st.markdown("#### 1. Live sensor simulation")
    st.caption("Simulated readings, showing how a real sensor node would feed PeatGuard.")
    zsim = st.selectbox("Sensor node in zone", scored["zone_id"], key="sim_zone")
    base = scored.set_index("zone_id").loc[zsim]
    if "smoulder" not in st.session_state:
        st.session_state.smoulder = False
    b1, b2 = st.columns(2)
    if b1.button("🔥 Simulate underground smoulder", type="primary"):
        st.session_state.smoulder = True
    if b2.button("Reset"):
        st.session_state.smoulder = False

    seed = int(hashlib.md5(zsim.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    t = pd.date_range(end=pd.Timestamp(status["as_of"]) + pd.Timedelta(hours=23, minutes=45),
                      periods=48 * 4, freq="15min")
    hours = np.asarray(t.hour + t.minute / 60, dtype=float)
    wt0 = float(base["wt_est_cm"])
    water = wt0 + np.linspace(-2, 2, len(t)) + rng.normal(0, 0.6, len(t))
    soil = 27 + 1.2 * np.sin((hours - 9) / 24 * 2 * np.pi) + rng.normal(0, 0.2, len(t))
    co = np.clip(0.4 + rng.normal(0, 0.15, len(t)), 0, None)
    if st.session_state.smoulder:
        k = 36  # last 9 hours
        ramp = np.linspace(0, 1, k) ** 1.5
        soil[-k:] += ramp * 30
        co[-k:] += ramp * 35
        water[-k:] += ramp * 3
    sim = pd.DataFrame({"time": t, "Water table depth (cm)": water,
                        "Soil temperature at 20 cm (°C)": soil, "CO near ground (ppm)": co})
    limits = {"Water table depth (cm)": DANGER_WATER_TABLE_CM,
              "Soil temperature at 20 cm (°C)": 40, "CO near ground (ppm)": 10}
    cols = st.columns(3)
    for col, (name, lim) in zip(cols, limits.items()):
        ch = alt.Chart(sim).mark_line().encode(x=alt.X("time:T", title=None), y=alt.Y(f"{name}:Q", title=name))
        rule = alt.Chart(pd.DataFrame({"y": [lim]})).mark_rule(color="#d62728", strokeDash=[4, 4]).encode(y="y:Q")
        col.altair_chart((ch + rule).properties(height=200), use_container_width=True)
        col.metric(name, f"{sim[name].iloc[-1]:.1f}", help=f"Alert line: {lim}")
    alarm = sim["Soil temperature at 20 cm (°C)"].iloc[-1] > 40 and sim["CO near ground (ppm)"].iloc[-1] > 10
    if alarm:
        new = scored.copy()
        i = new["zone_id"] == zsim
        new.loc[i, "p"] = 0.97
        new.loc[i, "priority"] = 0.97 * new.loc[i, "impact"] * 2
        new["rank2"] = new["priority"].rank(ascending=False, method="first").astype(int)
        st.error(f"🚨 **Ground sensor alert in {zsim}:** underground smouldering detected "
                 f"(soil {soil[-1]:.0f} °C, CO {co[-1]:.0f} ppm) before any satellite hotspot. "
                 f"Priority jumps from **#{int(base['rank'])} to #{int(new.loc[i, 'rank2'].iloc[0])}**. "
                 "Action: send a team now with deep-water injection equipment.")
    else:
        st.success(f"Sensors normal. Zone priority #{int(base['rank'])} from satellite and weather data alone.")
    st.caption("Alert lines are illustrative. Real thresholds would be set during a field pilot.")

    st.markdown("#### 2. What-if: how many more new fires would be caught?")
    st.caption("Replays the real new fires of 2023–2026. Change the assumptions to see the effect.")
    s1, s2, s3 = st.columns(3)
    cov = s1.slider("Zones with sensors", 0, 100, 30, 5, format="%d%%") / 100
    det = s2.slider("Sensor catches smouldering", 0, 100, 70, 5, format="%d%%") / 100
    head = s3.slider("Head start before satellites see it (days)", 1, 7, 2)

    @st.cache_data
    def events_and_flags(top_n):
        ts = test_scores().sort_values(["zone_id", "date"])
        quiet = ts[ts["hot_zone_7"] == 0].copy()
        quiet["flag"] = quiet.groupby("date")["p"].rank(ascending=False, method="first") <= top_n
        flagged = set(zip(quiet.loc[quiet["flag"], "zone_id"], quiet.loc[quiet["flag"], "date"]))
        ev = []
        for zid, g in ts.groupby("zone_id"):
            on = (g["hot_zone_1"].to_numpy() > 0).astype(float)
            q = pd.Series(on).shift(1).rolling(14, min_periods=14).sum().to_numpy()
            for d_ in g["date"].to_numpy()[(on > 0) & (q == 0)]:
                d_ = pd.Timestamp(d_)
                lead = next((k for k in range(7, 0, -1) if (zid, d_ - pd.Timedelta(days=k)) in flagged), 0)
                ev.append((zid, d_, lead))
        return pd.DataFrame(ev, columns=["zone_id", "date", "lead"])

    ev = events_and_flags(M["patrols_per_day"])
    zl = sorted(zones["zone_id"], key=lambda z: hashlib.md5(z.encode()).hexdigest())
    covered = set(zl[:int(round(cov * len(zl)))])
    rng2 = np.random.default_rng(42)
    caught = (ev["zone_id"].isin(covered).to_numpy()) & (rng2.random(len(ev)) < det)
    lead_iot = np.where(caught, np.maximum(ev["lead"], head), ev["lead"])
    before, after = (ev["lead"] > 0).mean(), (lead_iot > 0).mean()
    c1, c2, c3 = st.columns(3)
    c1.metric("New fires (2023–2026)", f"{len(ev):,}")
    c2.metric("Warned in advance: satellite only", f"{before:.0%}")
    c3.metric("Warned in advance: with sensors", f"{after:.0%}", f"{(after - before) * 100:+.0f} points")
    st.caption("Assumptions are shown on the sliders. Sensors also measure the real water table, "
               "which should sharpen the drought signal itself; that gain is not counted here.")
