"""Shared settings for PeatGuard: zones, dates and thresholds."""
from datetime import date, timedelta
import numpy as np

# Grid cell size in degrees (0.5 deg is about 55 km).
CELL = 0.5

# Peatland regions: (lat_min, lat_max, lon_min, lon_max, country, impact_weight)
# impact_weight is a rough 1-3 score for people exposed nearby
# (approximate; replace with WorldPop population data if time allows).
REGIONS = {
    "Selangor":           (2.5, 4.0, 100.75, 101.75, "MY", 3.0),
    "Johor":              (1.25, 2.25, 102.5, 103.75, "MY", 2.5),
    "Pahang":             (3.0, 4.0, 102.75, 103.75, "MY", 1.5),
    "Sarawak":            (1.5, 3.0, 111.0, 112.5, "MY", 1.5),
    "Riau":               (0.0, 2.0, 101.0, 103.0, "ID", 2.0),
    "South Sumatra-Jambi": (-3.5, -1.5, 104.0, 106.0, "ID", 2.0),
    "Central Kalimantan": (-3.5, -1.5, 113.0, 115.0, "ID", 1.5),
}

# Short unique code per region, used in zone ids (e.g. MY-SW-03).
CODES = {"Selangor": "S", "Johor": "J", "Pahang": "P", "Sarawak": "SW",
         "Riau": "R", "South Sumatra-Jambi": "SSJ", "Central Kalimantan": "CK"}

# One bounding box covering every region, used for the fire download:
# west, south, east, north
FIRE_BBOX = "100,-4,116,4.5"

HIST_START = "2015-01-01"
HIST_END = (date.today() - timedelta(days=10)).isoformat()  # reanalysis lags ~5 days
TEST_START = "2023-01-01"   # train before this date, test from it
HORIZON_DAYS = 7            # predict fire within the next 7 days
MIN_HOTSPOTS_FOR_FIRE = 3   # a zone counts as "on fire" with at least this many hotspots in the week

# Static heat sources (factories, flares, power plants): a ~1 km spot detected on
# at least this many days, spread over at least this many different years.
STATIC_MIN_DAYS = 40
STATIC_MIN_YEARS = 5

# Peat "specific yield": how far the water table drops per mm of water lost.
# Used to turn the moisture deficit into an estimated water-table depth.
SPECIFIC_YIELD = 0.3
DANGER_WATER_TABLE_CM = 40  # widely used peat fire danger line


def build_zones():
    """Return a list of zone dicts (one per grid cell)."""
    zones = []
    for region, (la0, la1, lo0, lo1, country, impact) in REGIONS.items():
        n = 0
        for lat in np.arange(la0 + CELL / 2, la1, CELL):
            for lon in np.arange(lo0 + CELL / 2, lo1, CELL):
                n += 1
                code = CODES[region]
                zones.append({
                    "zone_id": f"{country}-{code}-{n:02d}",
                    "region": region,
                    "country": country,
                    "lat": round(float(lat), 3),
                    "lon": round(float(lon), 3),
                    "impact": impact,
                })
    return zones


if __name__ == "__main__":
    z = build_zones()
    print(len(z), "zones")
    for r in REGIONS:
        print(f"  {r}: {sum(1 for x in z if x['region'] == r)}")
