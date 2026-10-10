# PeatGuard
**AI early warning for peatland fires in Malaysia and Indonesia**

PeatGuard predicts which peatland areas are likely to catch fire or spread fire **in the next 7 days**. It explains why, says what teams should do, and shows how clean the air is before they go out.

🔗 **Live app:** (https://peatguard-web.vercel.app/)
🔗 **Presentation:** (https://canva.link/g3ldm78cmnneeyv))

## Team - Wizards - Taylor's University 
- Yara Matouk
- Sandrine Madeleine

🏁 **Dormathon 2026 · Track 1: Predictive Model**


## The problem
Peat fires burn underground, are very hard to put out once they start, and send haze across Malaysia almost every dry season. Fire agencies have limited patrol teams. They need to know **where to send them before the fire starts**, not after satellites already see smoke.

## What PeatGuard does
- **Predicts** the 7-day fire risk for **71 peatland zones** across Malaysia and Indonesia
- **Categorises** each zone: *new fire likely* (catch it before it starts) or *existing fire may spread* (stop it spreading)
- **Prioritises** zones by risk, population impact and whether smoke will blow towards Malaysia
- **Explains** every prediction in plain words (e.g. "30 days much drier than normal", "peat water table very low")
- **Recommends actions** specific to each situation, and lets teams assign patrols or send warnings (WhatsApp/SMS, English or Bahasa Melayu)
- **Air quality**: current and 3-day AQI for towns and zones, so teams know the conditions before mobilising

## Results (tested on 2023–2026, data the model never saw)
| | PeatGuard | Simple rule | Random |
|---|---|---|---|
| Fires caught with 10 patrols/day | **40%** | 24% | 14% |
| New fires caught (no fire there before) | **58%** | 32% | – |
| New fires caught in an unseen country (trained on Indonesia, tested on Malaysia) | **88%** | 64% | – |
| ROC-AUC | **0.90** | 0.74 | 0.50 |

- High-risk alerts are only raised after **two days in a row** above the threshold, which cuts false alarms.
- To match PeatGuard with 10 patrols/day, the rule would need **18 patrols/day**. That is about **2,920 extra patrol-days a year (≈ RM 1.5 million at RM 500/day)**.

## How it works
1. **Data (all free and public)**
   - NASA FIRMS VIIRS satellite fire hotspots
   - NASA POWER daily weather (rain, temperature, humidity, wind)
   - Open-Meteo weather forecast (live)
   - NOAA El Niño (Niño 3.4) and Indian Ocean Dipole indices
   - Open-Meteo / CAMS air quality
2. **Cleaning:** removed low-confidence detections and **469 permanent heat sources** (factories, flares) that appear year after year. A zone counts as "on fire" only with **3 or more hotspots in 7 days**.
3. **Features:** rainfall windows, dry-day streaks, an estimated **peat water table** (danger below 40 cm), weather compared with normal for that zone and month, El Niño / IOD, and fire history.
4. **Models:** two **LightGBM** models, one for fire *spreading* in burning zones and one for fire *starting* in quiet zones. Trained 2015–2022 and tested 2023–2026, so the model never sees the future.
5. **Decision layer:** each zone's reasons come from the model's own feature contributions. Priority = risk × region impact × smoke-towards-Malaysia boost.


## 📁 File index

### Start here
| If you want to… | Go to |
|---|---|
| **Use the app** | Live link at the top of this README (works on any phone; add it to your home screen to install) |
| **See the pitch** | `Live link at the top of this README or Peat Guard Presentation.pptx` |
| **Understand how the model works** | `peatguard.py` → `features.py` → `scripts/train.py` (read in that order) |
| **Check our results** | `models/metrics.json` (also shown in the app's **Evidence** tab) |
| **Reproduce everything** | "Run it yourself" section below |

### Repository map
```
PeatGuard/
├── web/                         The app (static site, deployed on Vercel)
│   ├── index.html               Page shell, loads everything below
│   ├── app.js                   All screens: Today, Area briefing, Warn, Map, Air, Evidence
│   ├── style.css                Look and layout (mobile-first)
│   ├── config.js                Map settings (public Mapbox token, map style)
│   ├── leaflet-heat.js          Heat-map layer for the risk map
│   ├── land.json                Coastline outline, keeps the heat map on land
│   ├── manifest.json, sw.js     Make it installable and usable offline
│   ├── icons/                   App icons (Android and iPhone)
│   └── data/                    What the app reads, rebuilt daily by export_web.py
│       ├── today.json           Today's risk, reasons and actions for all 71 zones
│       ├── metrics.json         Test results for the Evidence tab
│       ├── air.json             Air-quality fallback (live data loads in the app)
│       ├── replay.json          Real past days where PeatGuard beat the rule
│       └── impact.json          Patrol-cost and savings figures
│
├── scripts/                     The pipeline, run in this order
│   ├── fetch_weather.py         1a. Daily weather history per zone (NASA POWER)
│   ├── fetch_fires.py           1b. Satellite fire hotspots (NASA FIRMS VIIRS, needs a free key)
│   ├── fetch_climate.py         1c. El Niño and Indian Ocean Dipole indices (NOAA)
│   ├── build_dataset.py         2.  Cleans fires, removes 469 fixed heat sources, builds features and labels
│   ├── train.py                 3.  Trains both models, tests on 2023–2026, saves results
│   └── export_web.py            4.  Scores today with live data, writes web/data/
│
├── models/                      Trained models and results
│   ├── model_spread.txt         Model for areas already burning (will it spread?)
│   ├── model_ignition.txt       Model for quiet areas (will a new fire start?)
│   ├── metrics.json             Every test number used in the app and the pitch
│   └── test_scores.csv.gz       Test-period predictions (used for the replay)
│
├── config.py                    Zones, regions, impact weights and settings (7-day horizon, ≥3 hotspots = fire)
├── features.py                  Feature engineering: rain windows, dry days, peat water table, anomalies, fire history
├── peatguard.py                 Live scoring: risk, plain-language reasons, categories, priority, actions, two-day rule
├── requirements.txt             Python packages
└── Peat Guard Presentation.pptx Pitch deck
```

### How the pieces connect
```
NASA FIRMS + NASA POWER + NOAA
        │  scripts/fetch_*.py
        ▼
scripts/build_dataset.py  ──►  features.py (feature engineering)
        ▼
scripts/train.py  ──►  models/  (2 LightGBM models + test results)
        ▼
scripts/export_web.py  ──►  peatguard.py (score, explain, prioritise, recommend)
        ▼
web/data/*.json  ──►  web/ app on Vercel
```

### Where to find each judging criterion
| Criterion | Where to look |
|---|---|
| Problem and value | App **Evidence → Impact** page; presentation |
| Predictive rigor | `scripts/train.py` (time split, baseline, unseen-country test), `models/metrics.json` |
| Decision support | `peatguard.py` (categories, priority, actions); app **Today** and **Area** screens |
| Explainability | `peatguard.py` (reasons from per-prediction feature contributions); "How this was calculated" in the app |
| Live prototype | The live link; `web/` |

## Project structure
```
web/            The app (static HTML/CSS/JS, deployed on Vercel)
  data/         Daily predictions the app reads (today, air, metrics, replay, impact)
scripts/        Data pipeline: fetch → build dataset → train → export to web
models/         Trained models + test metrics
config.py       Zones, regions and settings
features.py     Feature engineering
peatguard.py    Live scoring, explanations, categories and actions
.github/workflows/refresh.yml   Re-runs the model every morning (06:00 MYT)
```

## Run it yourself
```bash
pip install -r requirements.txt
export FIRMS_KEY=your_free_nasa_firms_key   # https://firms.modaps.eosdis.nasa.gov/api/

# Rebuild everything from scratch (optional, takes a while)
python scripts/fetch_weather.py
python scripts/fetch_fires.py
python scripts/fetch_climate.py
python scripts/build_dataset.py
python scripts/train.py

# Today's predictions for the app
python scripts/export_web.py

# View the app locally
cd web && python -m http.server 8000
```

## Limitations
- Zones are about 55 × 55 km grid cells, not exact plots.
- Satellites miss fires under cloud and smoke, so some real fires are not in the labels.
- IOT Ground sensors (water table, soil moisture) would improve accuracy. The app shows how they would fit in.


