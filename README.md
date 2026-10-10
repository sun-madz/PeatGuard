# PeatGuard
**AI early warning for peatland fires in Malaysia and Indonesia**

PeatGuard predicts which peatland areas are likely to catch fire or spread fire **in the next 7 days**. It explains why, says what teams should do, and shows how clean the air is before they go out.

🔗 **Live app:** (https://peatguard-web.vercel.app/)
👥 **Team:** Wizards · Taylor's University
🏁 **Dormathon 2026 · Track 1: Predictive Model**

---

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
- Region impact weights are set by hand (disclosed in the app).
- Ground sensors (water table, soil moisture) would improve accuracy. The app shows how they would fit in.

## Team
- NAME 1
- NAME 2
- NAME 3
- NAME 4
