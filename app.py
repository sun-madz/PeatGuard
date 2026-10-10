"""PeatGuard - peat-fire early warning for Malaysia and Indonesia.

Run locally:  streamlit run app.py
"""
import hashlib
import html
from datetime import datetime, timedelta, timezone

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import peatguard as pg
from config import DANGER_WATER_TABLE_CM

st.set_page_config(page_title="PeatGuard · Peat-fire early warning", page_icon="🔥", layout="wide")

# ------------------------------------------------------------------ design system

BG, PANEL, PANEL2, LINE = "#0E141B", "#16202B", "#1C2836", "#26313E"
TEXT, MUTED = "#E6EDF3", "#8B98A8"
EMBER, AMBER, TEAL, SLATE = "#FF6B35", "#F5A524", "#2EC4B6", "#5B6B7F"
HIGH = "#FF4D2E"
LEVEL_HEX = {"High": HIGH, "Elevated": AMBER, "Low": SLATE}
LEVEL_RGBA = {"High": [255, 77, 46, 200], "Elevated": [245, 165, 36, 165], "Low": [91, 107, 127, 45]}
MAP_STYLE = getattr(getattr(pdk, "map_styles", None), "CARTO_DARK", "dark")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, select, textarea {{
  font-family: 'Inter', system-ui, sans-serif !important; }}
#MainMenu, footer, header [data-testid="stToolbar"], .stDeployButton,
[data-testid="stStatusWidget"] {{ visibility: hidden; height: 0; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.2rem; max-width: 1500px; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}

/* header */
.pg-top {{ display:flex; align-items:center; justify-content:space-between; gap:16px;
  padding: 14px 20px; background: linear-gradient(90deg, {PANEL} 0%, #1a1410 100%);
  border: 1px solid {LINE}; border-radius: 14px; margin-bottom: 14px; flex-wrap: wrap; }}
.pg-brand {{ display:flex; align-items:center; gap:12px; }}
.pg-logo {{ width:40px; height:40px; border-radius:10px; display:grid; place-items:center;
  background: radial-gradient(circle at 35% 30%, #FFB347, {EMBER} 55%, #B8321A); font-size:22px;
  box-shadow: 0 0 18px rgba(255,107,53,.45); }}
.pg-name {{ font-size: 1.55rem; font-weight: 800; color:{TEXT}; line-height:1; }}
.pg-name span {{ color:{EMBER}; }}
.pg-tag {{ color:{MUTED}; font-size:.85rem; margin-top:4px; }}
.pg-pills {{ display:flex; gap:8px; flex-wrap:wrap; }}
.pill {{ font-size:.75rem; font-weight:600; padding:6px 11px; border-radius:999px;
  border:1px solid {LINE}; background:{PANEL2}; color:{MUTED}; white-space:nowrap; }}
.pill.live {{ color:#7CF0C5; border-color:rgba(46,196,182,.45); background:rgba(46,196,182,.08); }}
.pill.stored {{ color:{AMBER}; border-color:rgba(245,165,36,.4); background:rgba(245,165,36,.08); }}
.dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px;
  background: currentColor; vertical-align: 1px; }}
.pill.live .dot {{ animation: pulse 1.6s infinite; }}
@keyframes pulse {{ 0% {{ box-shadow:0 0 0 0 rgba(124,240,197,.7); }}
  70% {{ box-shadow:0 0 0 8px rgba(124,240,197,0); }} 100% {{ box-shadow:0 0 0 0 rgba(124,240,197,0); }} }}

/* KPI tiles */
.kpis {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:12px; margin: 4px 0 14px; }}
@media (max-width: 900px) {{ .kpis {{ grid-template-columns: repeat(2, minmax(0,1fr)); }} }}
.kpi {{ background:{PANEL}; border:1px solid {LINE}; border-radius:12px; padding:14px 16px; }}
.kpi .k-label {{ color:{MUTED}; font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }}
.kpi .k-val {{ font-size:2rem; font-weight:800; font-variant-numeric: tabular-nums; margin-top:4px; }}
.kpi .k-sub {{ color:{MUTED}; font-size:.78rem; }}
.kpi.hot {{ border-color: rgba(255,77,46,.55); background: linear-gradient(180deg, rgba(255,77,46,.12), {PANEL}); }}

/* patrol cards */
.cards {{ display:flex; flex-direction:column; gap:8px; max-height: 560px; overflow-y:auto; padding-right:4px; }}
.card {{ background:{PANEL}; border:1px solid {LINE}; border-left:4px solid var(--c);
  border-radius:10px; padding:10px 12px; }}
.card .row1 {{ display:flex; align-items:center; gap:10px; }}
.rank {{ font-weight:800; color:{MUTED}; width:26px; font-variant-numeric: tabular-nums; }}
.zname {{ font-weight:700; color:{TEXT}; }}
.zreg {{ color:{MUTED}; font-size:.8rem; }}
.pct {{ margin-left:auto; font-size:1.35rem; font-weight:800; color:var(--c); font-variant-numeric: tabular-nums; }}
.chips {{ display:flex; gap:6px; flex-wrap:wrap; margin:6px 0 4px 36px; }}
.chip {{ font-size:.7rem; font-weight:600; padding:3px 8px; border-radius:999px; background:{PANEL2}; color:{MUTED}; border:1px solid {LINE}; }}
.chip.lvl {{ color:var(--c); border-color:var(--c); }}
.chip.smoke {{ color:#FFB4A0; border-color:rgba(255,107,53,.5); background:rgba(255,107,53,.1); }}
.why {{ margin-left:36px; color:#C3CDD8; font-size:.82rem; }}

/* decision card */
.decision {{ background:{PANEL}; border:1px solid {LINE}; border-radius:14px; padding:18px 20px; }}
.big {{ font-size:3rem; font-weight:800; line-height:1; color:var(--c); font-variant-numeric: tabular-nums; }}
.reasons {{ margin: 10px 0 0 0; padding-left: 20px; color:#D5DDE6; }}
.reasons li {{ margin-bottom:6px; }}
.action {{ margin-top:14px; padding:12px 14px; border-radius:10px; background:rgba(255,107,53,.10);
  border:1px solid rgba(255,107,53,.45); color:{TEXT}; }}
.action b {{ color:{EMBER}; }}
.note {{ color:{MUTED}; font-size:.8rem; }}

/* headline stats on proof page */
.heads {{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:12px; margin:8px 0 18px; }}
@media (max-width: 900px) {{ .heads {{ grid-template-columns: 1fr; }} }}
.head {{ background:{PANEL}; border:1px solid {LINE}; border-radius:14px; padding:18px; }}
.head .h-val {{ font-size:2.6rem; font-weight:800; color:{EMBER}; line-height:1.05; }}
.head .h-txt {{ color:#C3CDD8; font-size:.9rem; margin-top:6px; }}

/* tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ background:{PANEL}; border:1px solid {LINE}; border-bottom:none;
  border-radius:10px 10px 0 0; padding: 8px 16px; color:{MUTED}; }}
.stTabs [aria-selected="true"] {{ color:{TEXT} !important; background:{PANEL2}; border-color:{EMBER}; }}
.section-title {{ font-size:1.05rem; font-weight:700; color:{TEXT}; margin: 2px 0 8px; }}
</style>
""", unsafe_allow_html=True)


FRIENDLY = {
    "rain_7": "Rain, past week", "rain_14": "Rain, past 2 weeks", "rain_30": "Rain, past month",
    "rain_60": "Rain, past 2 months", "rain_90": "Rain, past 3 months", "dry_days": "Dry days in a row",
    "deficit_mm": "Peat dryness (water lost)", "deficit_change_7": "Drying in past week",
    "wt_est_cm": "Estimated water table", "tmax": "Max temperature", "tmax_7": "Temperature, past week",
    "rh_min": "Afternoon humidity", "rh_min_7": "Humidity, past week", "wind_max": "Wind speed",
    "et0_7": "Evaporation, past week", "month_sin": "Season", "month_cos": "Season (2)",
    "rain_30_anom": "Rain vs normal, month", "rain_90_anom": "Rain vs normal, 3 months",
    "deficit_mm_anom": "Dryness vs normal", "rh_min_7_anom": "Humidity vs normal",
    "tmax_7_anom": "Heat vs normal", "nino34_lag1": "El Niño, last month", "nino34_3m": "El Niño, 3 months",
    "dmi_lag1": "Indian Ocean Dipole, last month", "dmi_3m": "Indian Ocean Dipole, 3 months",
    "hot_zone_7": "Fires here, past week", "hot_zone_30": "Fires here, past month",
    "hot_zone_90": "Fires here, past 3 months", "hot_zone_365": "Fires here, past year",
    "days_since_fire": "Days since last fire", "zone_month_fire_rate": "Burns in this month historically",
    "frp_zone_7": "Fire intensity here", "hot_near_7": "Fires within 80 km, week",
    "hot_near_1": "Fires within 80 km, today", "frp_near_7": "Fire intensity nearby",
}


def chart_style(c):
    return (c.configure(background="transparent", padding={"left": 4, "right": 8, "top": 14, "bottom": 4})
             .configure_view(strokeWidth=0)
             .configure_axis(labelColor=MUTED, titleColor=MUTED, gridColor=LINE, domainColor=LINE,
                             tickColor=LINE, labelFont="Inter, sans-serif", titleFont="Inter, sans-serif", titleFontWeight=500,
                             labelLimit=220)
             .configure_legend(labelColor=MUTED, titleColor=MUTED, labelFont="Inter, sans-serif", orient="bottom")
             .configure_title(color=TEXT, font="Inter, sans-serif", fontSize=13, anchor="start", offset=10))


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
    s, f, stt = pg.run(artifacts(), firms_key=key, live=True)
    stt["fetched"] = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M MYT, %d %b")
    return s, f, stt


@st.cache_data
def test_scores():
    t = pd.read_csv(pg.M / "test_scores.csv.gz", parse_dates=["date"])
    return t.merge(artifacts()["zones"], on="zone_id")


@st.cache_data
def counts():
    return pg.load_counts()


a = artifacts()
M = a["metrics"]
scored, feats, status = today_view(firms_key())
zones = a["zones"]
esc = html.escape

# ------------------------------------------------------------------ header

live = status["weather"] == "live"
pill = (f'<span class="pill live"><span class="dot"></span>LIVE · updated {status["fetched"]}</span>'
        if live else '<span class="pill stored"><span class="dot"></span>STORED DATA</span>')
st.markdown(f"""
<div class="pg-top">
  <div class="pg-brand"><div class="pg-logo">🔥</div>
    <div><div class="pg-name">Peat<span>Guard</span></div>
    <div class="pg-tag">AI early warning for peat fires, the source of Southeast Asia's haze</div></div></div>
  <div class="pg-pills">{pill}
    <span class="pill">Risk for {pd.Timestamp(status['as_of']).strftime('%d %b %Y')}</span>
    <span class="pill">71 zones · Malaysia + Indonesia</span>
    <span class="pill">Hotspots: {status['fires']}</span></div>
</div>""", unsafe_allow_html=True)
if not live:
    st.caption("Live weather was not reachable just now, so risk is shown from the latest stored data.")


def zone_map(df, fill, tooltip_html, points=None, height=560):
    d = df.copy()
    d["polygon"] = [pg.cell_polygon(la, lo) for la, lo in zip(d["lat"], d["lon"])]
    layers = [pdk.Layer("PolygonLayer", d, get_polygon="polygon", get_fill_color=fill,
                        get_line_color=[255, 255, 255, 40], line_width_min_pixels=1,
                        pickable=True, auto_highlight=True, highlight_color=[255, 255, 255, 60])]
    if points is not None and len(points):
        layers.append(pdk.Layer("ScatterplotLayer", points, get_position=["lon", "lat"],
                                get_radius="r", radius_min_pixels=2, radius_max_pixels=14,
                                get_fill_color=[255, 196, 120, 220], stroked=True,
                                get_line_color=[255, 107, 53, 160], line_width_min_pixels=2))
    view = pdk.ViewState(latitude=0.6, longitude=107.6, zoom=4.5, pitch=0)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style=MAP_STYLE,
                             tooltip={"html": tooltip_html,
                                      "style": {"backgroundColor": PANEL, "color": TEXT,
                                                "fontFamily": "Inter", "fontSize": "12px",
                                                "border": f"1px solid {LINE}", "borderRadius": "8px"}}),
                    height=height)


tab_today, tab_replay, tab_proof, tab_iot = st.tabs(
    ["🗺️  Live risk", "⏪  Replay 2023–2026", "📊  Proof it works", "📡  IoT sensor upgrade"])

# ------------------------------------------------------------------ TODAY

with tab_today:
    n_high = int((scored["level"] == "High").sum())
    n_elev = int((scored["level"] == "Elevated").sum())
    n_active = int((scored["hot_zone_7"] > 0).sum())
    n_smoke = int((scored["smoke_to_MY"] & scored["level"].isin(["High", "Elevated"])).sum())
    st.markdown(f"""
<div class="kpis">
 <div class="kpi"><div class="k-label">High-risk zones</div><div class="k-val" style="color:{HIGH}">{n_high}</div>
   <div class="k-sub">patrol today</div></div>
 <div class="kpi"><div class="k-label">Elevated-risk zones</div><div class="k-val" style="color:{AMBER}">{n_elev}</div>
   <div class="k-sub">patrol within 3 days</div></div>
 <div class="kpi"><div class="k-label">Zones burning this week</div><div class="k-val">{n_active}</div>
   <div class="k-sub">3+ satellite hotspots</div></div>
 <div class="kpi hot"><div class="k-label">Smoke heading to Malaysia</div><div class="k-val" style="color:{EMBER}">{n_smoke}</div>
   <div class="k-sub">risky zones upwind of Malaysia</div></div>
</div>""", unsafe_allow_html=True)

    left, right = st.columns([5, 3], gap="medium")
    with left:
        m = scored.assign(fill=scored["level"].map(LEVEL_RGBA),
                          pct=(scored["p"] * 100).round(0).astype(int),
                          cat=scored["category"].map(esc))
        pts = None
        if status.get("points"):
            pts = pd.DataFrame(status["points"]).rename(columns={"latitude": "lat", "longitude": "lon"})
            frp = pts["frp"] if "frp" in pts else pd.Series(10.0, index=pts.index)
            pts["r"] = 2500 + 120 * frp.fillna(10).clip(upper=100)
        else:
            act = scored[scored["hot_zone_7"] > 0]
            pts = act[["lat", "lon"]].assign(r=4000 + 600 * np.sqrt(act["hot_zone_7"]))
        zone_map(m, "fill", "<b>{zone_id}</b> · {region}<br/>{level} risk · <b>{pct}%</b> chance of fire this week<br/>{cat}",
                 points=pts)
        st.markdown(f'<div class="note">Squares = ~55 km zones, coloured by risk '
                    f'(<span style="color:{HIGH}">high</span>, <span style="color:{AMBER}">elevated</span>, '
                    f'<span style="color:{SLATE}">low</span>). Glowing dots = fire detected this week.</div>',
                    unsafe_allow_html=True)
    with right:
        st.markdown(f'<div class="section-title">Today\'s patrol list · top {M["patrols_per_day"]}</div>',
                    unsafe_allow_html=True)
        cards = []
        for _, r in scored.head(M["patrols_per_day"]).iterrows():
            c = LEVEL_HEX[r["level"]]
            why = esc(r["reasons"][0]) if r["reasons"] else "No strong warning signs"
            smoke = ('<span class="chip smoke">smoke → Malaysia</span>'
                     if r["smoke_to_MY"] and r["level"] != "Low" else "")
            cards.append(f"""
<div class="card" style="--c:{c}">
  <div class="row1"><span class="rank">#{r['rank']}</span>
    <div><div class="zname">{esc(r['zone_id'])}</div><div class="zreg">{esc(r['region'])}</div></div>
    <span class="pct">{r['p']:.0%}</span></div>
  <div class="chips"><span class="chip lvl">{r['level']}</span><span class="chip">{esc(r['category'])}</span>{smoke}</div>
  <div class="why">{why}</div>
</div>""")
        st.markdown(f'<div class="cards">{"".join(cards)}</div>', unsafe_allow_html=True)
        st.markdown('<div class="note" style="margin-top:6px">Ranked by chance of fire × people nearby × '
                    'whether smoke would blow toward Malaysia.</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Zone briefing</div>', unsafe_allow_html=True)
    pick = st.selectbox("Zone", scored["zone_id"], label_visibility="collapsed",
                        format_func=lambda z: f"#{scored.set_index('zone_id').loc[z, 'rank']} · {z} · "
                                              f"{scored.set_index('zone_id').loc[z, 'region']}")
    r = scored.set_index("zone_id").loc[pick]
    c = LEVEL_HEX[r["level"]]
    d1, d2 = st.columns([2, 3], gap="medium")
    with d1:
        reasons = "".join(f"<li>{esc(x)}</li>" for x in (r["reasons"] or ["No strong warning signs."]))
        smoke = ('<div class="note" style="color:#FFB4A0;margin-top:10px">⚠ Today\'s wind would carry '
                 'smoke from this zone toward Malaysia.</div>') if r["smoke_to_MY"] and r["level"] != "Low" else ""
        st.markdown(f"""
<div class="decision" style="--c:{c}">
  <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:10px">
    <div><div class="note">{esc(pick)} · {esc(r['region'])}</div>
      <div style="font-size:1.25rem;font-weight:700;color:{c};margin-top:4px">{r['level']} risk</div>
      <div class="note">{esc(r['category'])} · priority #{r['rank']}</div></div>
    <div style="text-align:right"><div class="big">{r['p']:.0%}</div>
      <div class="note">chance of fire<br>in the next 7 days</div></div></div>
  <div style="margin-top:14px;font-weight:600">Why</div>
  <ol class="reasons">{reasons}</ol>
  <div class="action"><b>Recommended action</b><br>{esc(r['action'])}</div>{smoke}
</div>""", unsafe_allow_html=True)
    with d2:
        z = feats[feats["zone_id"] == pick].copy()
        z = z[z["date"] >= z["date"].max() - pd.Timedelta(days=120)]
        z["kind"] = np.where(z["date"] > pd.Timestamp(status["as_of"]), "Forecast", "Observed")
        ymax = max(float(z["wt_est_cm"].max()), DANGER_WATER_TABLE_CM + 15)
        band = alt.Chart(pd.DataFrame({"y": [DANGER_WATER_TABLE_CM], "y2": [ymax]})).mark_rect(
            color=HIGH, opacity=0.10).encode(y="y:Q", y2="y2:Q")
        rule = alt.Chart(pd.DataFrame({"y": [DANGER_WATER_TABLE_CM]})).mark_rule(
            color=HIGH, strokeDash=[4, 4]).encode(y="y:Q")
        line = alt.Chart(z).mark_line(strokeWidth=2.5).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("wt_est_cm:Q", title="Depth (cm)",
                    scale=alt.Scale(reverse=True, domain=[0, ymax])),
            color=alt.Color("kind:N", scale=alt.Scale(domain=["Observed", "Forecast"], range=[TEAL, "#9FE8E0"]),
                            legend=alt.Legend(title=None)),
            strokeDash=alt.StrokeDash("kind:N", legend=None,
                                      scale=alt.Scale(domain=["Observed", "Forecast"], range=[[1, 0], [5, 4]])))
        st.markdown('<div class="section-title" style="font-size:.85rem;margin:0">Estimated peat water table · '
                    'red zone = fire danger (deeper than 40 cm)</div>', unsafe_allow_html=True)
        st.altair_chart(chart_style(alt.layer(band, rule, line).properties(height=300)),
                        use_container_width=True)
        rain = alt.Chart(z).mark_bar(opacity=0.85, cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
            x=alt.X("date:T", title=None), y=alt.Y("rain:Q", title="mm"),
            color=alt.Color("kind:N", scale=alt.Scale(domain=["Observed", "Forecast"], range=["#4E7CA8", "#9CC3E6"]),
                            legend=None))
        st.altair_chart(chart_style(rain.properties(height=120, title="Daily rainfall")),
                        use_container_width=True)
        # Fire activity this season vs the same weeks in past years (GFW-style context)
        zc = counts()
        zz = zc[zc["zone_id"] == pick].set_index("date")["inside"].resample("W").sum()
        if len(zz):
            wk = zz.to_frame("fires")
            wk["year"], wk["week"] = wk.index.year, wk.index.isocalendar().week.astype(int)
            this_year = pd.Timestamp(status["as_of"]).year
            cur = wk[wk["year"] == this_year]
            hist = wk[wk["year"] < this_year].groupby("week")["fires"].mean().rename("past").reset_index()
            comp = hist.merge(cur[["week", "fires"]], on="week", how="left")
            comp = comp.melt("week", ["past", "fires"], var_name="series", value_name="hotspots")
            comp["series"] = comp["series"].map({"past": "Average of past years", "fires": str(this_year)})
            ch = alt.Chart(comp.dropna()).mark_line(strokeWidth=2).encode(
                x=alt.X("week:Q", title="Week of year"), y=alt.Y("hotspots:Q", title="Hotspots"),
                color=alt.Color("series:N", scale=alt.Scale(domain=["Average of past years", str(this_year)],
                                                            range=[SLATE, EMBER]),
                                legend=alt.Legend(title=None)))
            st.altair_chart(chart_style(ch.properties(height=150, title="Fire activity: this year vs past years")),
                            use_container_width=True)

# ------------------------------------------------------------------ REPLAY

with tab_replay:
    st.markdown('<div class="section-title">What PeatGuard would have said on any day from 2023 to 2026</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="note">These years were never used in training. Orange = PeatGuard\'s top 10 '
                'patrol picks that day. Glowing dots = zones that really burned in the next 7 days.</div>',
                unsafe_allow_html=True)
    ts = test_scores()
    busiest = ts.groupby("date")["fire_next7"].sum().idxmax()
    day = st.slider("Day", min_value=ts["date"].min().date(), max_value=ts["date"].max().date(),
                    value=busiest.date(), format="DD MMM YYYY")
    d = ts[ts["date"] == pd.Timestamp(day)].copy()
    d["rank"] = d["p"].rank(ascending=False, method="first").astype(int)
    d["top"] = d["rank"] <= M["patrols_per_day"]
    d["pct"] = (d["p"] * 100).round(0).astype(int)
    d["fill"] = [[255, 107, 53, 200] if t else [91, 107, 127, int(30 + 120 * p)] for t, p in zip(d["top"], d["p"])]
    burned = d[d["fire_next7"] == 1]
    zone_map(d, "fill", "<b>{zone_id}</b><br/>#{rank} · {pct}% fire chance",
             points=burned[["lat", "lon"]].assign(r=9000), height=500)
    caught, nb = int((d["top"] & (d["fire_next7"] == 1)).sum()), int(len(burned))
    rnd = nb * M["patrols_per_day"] / max(len(d), 1)
    st.markdown(f"""
<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">
 <div class="kpi"><div class="k-label">Zones that burned in the next 7 days</div><div class="k-val">{nb}</div></div>
 <div class="kpi hot"><div class="k-label">Caught by PeatGuard's top 10</div><div class="k-val" style="color:{EMBER}">{caught}</div></div>
 <div class="kpi"><div class="k-label">Expected from 10 random patrols</div><div class="k-val">{rnd:.1f}</div></div>
</div>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ PROOF

with tab_proof:
    fy, uc = M["future_years"], M["unseen_country"]

    def lift(m, b):
        return (m / b - 1) if b else 0
    st.markdown(f"""
<div class="heads">
 <div class="head"><div class="h-val">+{lift(fy['model']['patrol_catch'], fy['simple_rule']['patrol_catch']):.0%}</div>
  <div class="h-txt">more fires caught with the same 10 patrols a day than today's rule of thumb
  ({fy['model']['patrol_catch']:.0%} vs {fy['simple_rule']['patrol_catch']:.0%}; random: {fy['random_patrol_catch']:.0%})</div></div>
 <div class="head"><div class="h-val">+{lift(fy['model']['new_fire']['patrol_catch'], fy['simple_rule']['new_fire']['patrol_catch']):.0%}</div>
  <div class="h-txt">more <b>new</b> fires caught in quiet zones, the true early-warning test
  ({fy['model']['new_fire']['patrol_catch']:.0%} vs {fy['simple_rule']['new_fire']['patrol_catch']:.0%})</div></div>
 <div class="head"><div class="h-val">{uc['model']['new_fire']['patrol_catch']:.0%}</div>
  <div class="h-txt">of new fires caught in <b>Malaysia</b> by a model trained only on Indonesia
  (rule: {uc['simple_rule']['new_fire']['patrol_catch']:.0%})</div></div>
</div>""", unsafe_allow_html=True)
    st.markdown('<div class="note">Test: trained on 2015–2022, tested once on 2023–2026 (never seen in '
                'training). Decision: which 10 zones to patrol each day.</div>', unsafe_allow_html=True)

    rows = []
    for test, res in (("Future years · all zones", fy), ("Unseen country · Indonesia → Malaysia", uc)):
        for what, key in (("All fires", None), ("New fires only", "new_fire")):
            for method, mk in (("PeatGuard", "model"), ("Simple rule", "simple_rule")):
                v = res[mk][key]["patrol_catch"] if key else res[mk]["patrol_catch"]
                rows.append({"test": test, "fires": what, "method": method, "caught": v})
            if not key:
                rows.append({"test": test, "fires": what, "method": "Random", "caught": res["random_patrol_catch"]})
    pr = pd.DataFrame(rows)
    order = ["PeatGuard", "Simple rule", "Random"]
    palette = alt.Scale(domain=order, range=[EMBER, SLATE, "#3A4757"])
    for test in pr["test"].unique():
        st.markdown(f'<div class="section-title" style="margin-top:14px">{test}</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for col, what in zip(cols, ["All fires", "New fires only"]):
            sub = pr[(pr["test"] == test) & (pr["fires"] == what)]
            bars = alt.Chart(sub).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                x=alt.X("method:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("caught:Q", axis=alt.Axis(format="%"), title="Fires caught (10 patrols/day)",
                        scale=alt.Scale(domain=[0, 1])),
                color=alt.Color("method:N", scale=palette, legend=None))
            labels = bars.mark_text(dy=-9, color=TEXT, fontWeight=700).encode(
                text=alt.Text("caught:Q", format=".0%"))
            col.altair_chart(chart_style((bars + labels).properties(title=what, height=230)),
                             use_container_width=True)

    def pct(x):
        return f"{x:.0%}"
    st.markdown('<div class="section-title" style="margin-top:10px">Key numbers · test years 2023–2026</div>',
                unsafe_allow_html=True)
    st.dataframe(pd.DataFrame({
        "Measure": ["Ranking quality, all fires (ROC AUC)", "Fires caught with 10 patrols/day",
                    "New fires caught with 10 patrols/day", "Ranking quality, new fires (ROC AUC)",
                    "Alerts that were real (precision, 2-day rule)", "New fires flagged in the week before"],
        "PeatGuard": [f"{fy['model']['roc_auc']:.2f}", pct(fy['model']['patrol_catch']),
                      pct(fy['model']['new_fire']['patrol_catch']), f"{fy['model']['new_fire']['roc_auc']:.2f}",
                      pct(fy['model']['alerts_2day']['precision']), pct(fy['model']['new_fire']['warned_share'])],
        "Simple rule": [f"{fy['simple_rule']['roc_auc']:.2f}", pct(fy['simple_rule']['patrol_catch']),
                        pct(fy['simple_rule']['new_fire']['patrol_catch']), f"{fy['simple_rule']['new_fire']['roc_auc']:.2f}",
                        pct(fy['simple_rule']['alerts_2day']['precision']), pct(fy['simple_rule']['new_fire']['warned_share'])],
    }), hide_index=True, use_container_width=True)

    st.markdown('<div class="section-title" style="margin-top:14px">What the models rely on</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for col, kind, title in ((c1, "spread", "Spread model · zones already burning"),
                             (c2, "ignition", "Ignition model · quiet zones, new fires")):
        imp = pd.Series(M["importance"][kind]).head(8).rename("share").reset_index()
        imp["index"] = imp["index"].map(lambda f: FRIENDLY.get(f, f))
        col.altair_chart(chart_style(alt.Chart(imp).mark_bar(color=EMBER, cornerRadiusEnd=3).encode(
            x=alt.X("share:Q", axis=alt.Axis(format="%"), title=None),
            y=alt.Y("index:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False))
        ).properties(height=260, title=title)),
            use_container_width=True)

    with st.expander("How it works, and its limits"):
        st.markdown("""
- **Data:** NASA FIRMS satellite fire hotspots (VIIRS, 2015–now), NASA POWER daily weather,
  NOAA El Niño (Niño 3.4) and Indian Ocean Dipole indices. Live mode adds the Open-Meteo forecast.
- **Cleaning:** low-confidence detections removed; 469 static heat sources (factories, flares) removed;
  a zone counts as burning only with 3+ hotspots in a week.
- **Two models (LightGBM):** *spread* for zones already burning, *ignition* for quiet zones,
  so the early-warning model cannot rely on "there is already a fire here".
- **Honest testing:** trained on 2015–2022, tested once on 2023–2026; a separate copy trained only
  on Indonesia and tested only on Malaysia. Alert thresholds set on 2022, never on the test years.
- **Limits:** zones are ~55 km, so it says where to patrol, not which field is burning. Weather and
  water table are estimated, not measured. That is exactly what IoT sensors fix.
""")

# ------------------------------------------------------------------ IoT

with tab_iot:
    st.markdown('<div class="section-title">From satellite estimates to ground truth</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="note" style="font-size:.92rem;color:#C3CDD8">Today PeatGuard <b>estimates</b> how dry '
                f'the peat is and <b>waits</b> for satellites to see fire. Ground sensors let it <b style="color:{TEAL}">'
                f'measure</b> the fuel and <b style="color:{EMBER}">catch fire underground</b>, before any satellite can.</div>',
                unsafe_allow_html=True)
    st.graphviz_chart(f"""
digraph {{ rankdir=LR; bgcolor="transparent"; pad=0.2;
  node [shape=box, style="rounded,filled", fillcolor="{PANEL}", color="{LINE}", fontcolor="{TEXT}", fontname="Helvetica", fontsize=11];
  edge [color="{MUTED}", fontcolor="{MUTED}", fontname="Helvetica", fontsize=10];
  s1 [label="Water-table sensor\\npeat dryness", color="{TEAL}"]; s2 [label="Soil temperature\\n20 cm deep", color="{TEAL}"];
  s3 [label="CO gas sensor\\nsmoke", color="{TEAL}"]; mcu [label="ESP32 node\\nsolar powered"];
  gw [label="LoRaWAN gateway\\nkm range, low power"]; cloud [label="Cloud\\nMQTT + database"];
  sat [label="Satellite hotspots\\nweather + El Niño"]; model [label="PeatGuard AI\\nrisk + reasons", color="{EMBER}", fillcolor="#2A1A14"];
  out [label="Patrol list\\nSMS alerts · dashboard"];
  s1 -> mcu; s2 -> mcu; s3 -> mcu; mcu -> gw [label="LoRa"]; gw -> cloud [label="4G"];
  cloud -> model; sat -> model; model -> out; }}""")

    st.markdown('<div class="section-title" style="margin-top:8px">1 · Live sensor simulation</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="note">Simulated readings, showing how a real sensor node would feed PeatGuard.</div>',
                unsafe_allow_html=True)
    zsim = st.selectbox("Sensor node in zone", scored["zone_id"], key="sim_zone")
    base = scored.set_index("zone_id").loc[zsim]
    if "smoulder" not in st.session_state:
        st.session_state.smoulder = False
    b1, b2, _ = st.columns([2, 1, 4])
    if b1.button("🔥 Simulate underground smoulder", type="primary", use_container_width=True):
        st.session_state.smoulder = True
    if b2.button("Reset", use_container_width=True):
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
    limits = {"Water table depth (cm)": (DANGER_WATER_TABLE_CM, TEAL),
              "Soil temperature at 20 cm (°C)": (40, EMBER), "CO near ground (ppm)": (10, AMBER)}
    cols = st.columns(3)
    for col, (name, (lim, colr)) in zip(cols, limits.items()):
        val = sim[name].iloc[-1]
        over = val > lim
        col.markdown(f'<div class="kpi {"hot" if over else ""}"><div class="k-label">{name}</div>'
                     f'<div class="k-val" style="color:{HIGH if over else colr}">{val:.1f}</div>'
                     f'<div class="k-sub">alert line {lim}</div></div>', unsafe_allow_html=True)
        ch = alt.Chart(sim).mark_line(color=colr, strokeWidth=2).encode(
            x=alt.X("time:T", title=None), y=alt.Y(f"{name}:Q", title=None))
        rule = alt.Chart(pd.DataFrame({"y": [lim]})).mark_rule(color=HIGH, strokeDash=[4, 4]).encode(y="y:Q")
        col.altair_chart(chart_style((ch + rule).properties(height=170)), use_container_width=True)
    alarm = soil[-1] > 40 and co[-1] > 10
    if alarm:
        new = scored.copy()
        i = new["zone_id"] == zsim
        new.loc[i, "priority"] = 0.97 * new.loc[i, "impact"] * 2
        new_rank = int(new["priority"].rank(ascending=False, method="first")[i].iloc[0])
        st.markdown(f"""
<div class="action" style="background:rgba(255,77,46,.14);border-color:{HIGH}">
<b style="color:{HIGH}">🚨 Ground sensor alert · {esc(zsim)}</b><br>
Underground smouldering detected (soil {soil[-1]:.0f} °C, CO {co[-1]:.0f} ppm) <b>before any satellite hotspot</b>.
Priority jumps from <b>#{int(base['rank'])}</b> to <b>#{new_rank}</b>. Action: send a team now with deep-water injection equipment.
</div>""", unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="action" style="background:rgba(46,196,182,.08);border-color:rgba(46,196,182,.45)">'
                    f'<b style="color:{TEAL}">Sensors normal</b><br>Zone priority #{int(base["rank"])} '
                    f'from satellite and weather data alone.</div>', unsafe_allow_html=True)
    st.markdown('<div class="note" style="margin-top:6px">Alert lines are illustrative; real thresholds '
                'would be set during a field pilot.</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title" style="margin-top:18px">2 · What-if: how many more new fires would be caught?</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="note">Replays the real new fires of 2023–2026. Change the assumptions to see the effect.</div>',
                unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    cov = s1.slider("Zones with sensors", 0, 100, 30, 5, format="%d%%") / 100
    det = s2.slider("Sensor catches smouldering", 0, 100, 70, 5, format="%d%%") / 100
    head = s3.slider("Head start before satellites see it (days)", 1, 7, 2)

    @st.cache_data
    def events_and_flags(top_n):
        ts_ = test_scores().sort_values(["zone_id", "date"])
        quiet = ts_[ts_["hot_zone_7"] == 0].copy()
        quiet["flag"] = quiet.groupby("date")["p"].rank(ascending=False, method="first") <= top_n
        flagged = set(zip(quiet.loc[quiet["flag"], "zone_id"], quiet.loc[quiet["flag"], "date"]))
        ev = []
        for zid, g in ts_.groupby("zone_id"):
            on = (g["hot_zone_1"].to_numpy() > 0).astype(float)
            q = pd.Series(on).shift(1).rolling(14, min_periods=14).sum().to_numpy()
            for d_ in g["date"].to_numpy()[(on > 0) & (q == 0)]:
                d_ = pd.Timestamp(d_)
                lead = next((k for k in range(7, 0, -1) if (zid, d_ - pd.Timedelta(days=k)) in flagged), 0)
                ev.append((zid, d_, lead))
        return pd.DataFrame(ev, columns=["zone_id", "date", "lead"])

    ev = events_and_flags(M["patrols_per_day"])
    zl = sorted(zones["zone_id"], key=lambda z_: hashlib.md5(z_.encode()).hexdigest())
    covered = set(zl[:int(round(cov * len(zl)))])
    rng2 = np.random.default_rng(42)
    got = (ev["zone_id"].isin(covered).to_numpy()) & (rng2.random(len(ev)) < det)
    lead_iot = np.where(got, np.maximum(ev["lead"], head), ev["lead"])
    before, after = (ev["lead"] > 0).mean(), (lead_iot > 0).mean()
    st.markdown(f"""
<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">
 <div class="kpi"><div class="k-label">New fires, 2023–2026</div><div class="k-val">{len(ev):,}</div></div>
 <div class="kpi"><div class="k-label">Warned in advance · satellite only</div><div class="k-val" style="color:{SLATE}">{before:.0%}</div></div>
 <div class="kpi hot"><div class="k-label">Warned in advance · with sensors</div><div class="k-val" style="color:{EMBER}">{after:.0%}</div>
  <div class="k-sub">{(after - before) * 100:+.0f} percentage points</div></div>
</div>""", unsafe_allow_html=True)
    st.markdown('<div class="note">Assumptions are shown on the sliders. Sensors also measure the real water '
                'table, which should sharpen the drought signal itself; that gain is not counted here.</div>',
                unsafe_allow_html=True)
