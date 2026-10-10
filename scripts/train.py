"""Step 3: train the fire-risk models and prove they work.

Run from the project root:  python scripts/train.py

Two models, because they answer two different questions:
  SPREAD model    zones with fire in the last 7 days: will fire continue or grow?
  IGNITION model  quiet zones (no fire in the last 7 days): will a NEW fire start?
                  It cannot lean on "there is already a fire here", so it must learn
                  the drought signals. This is the true early-warning model.

Writes:
  models/model_spread.txt, models/model_ignition.txt
  models/metrics.json      every number for the slides and the app's Proof page
  models/test_scores.csv.gz  test-period predictions (for the app's replay mode)

Proof tests, each run for (a) future years and (b) trained on Indonesia, tested on Malaysia:
  - versus a simple rule ("many dry days in a row") and versus random patrols
  - patrol test: checking only 10 zones a day, what share of fires does each method catch
  - false alarms: precision of alerts (with a 2-day persistence rule)
  - early warning: share of NEW fires flagged beforehand, and how many days ahead
"""
import json, sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import TEST_START
from features import FEATURES, IGNITION_FEATURES

MODELS = Path("models")
MODELS.mkdir(exist_ok=True)
PATROLS_PER_DAY = 10
VALID_START = "2022-01-01"   # last training year, used for early stopping and thresholds
PARAMS = dict(
    objective="binary", learning_rate=0.03, num_leaves=31, min_child_samples=200,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    verbose=-1, seed=42,
)
KINDS = {"spread": FEATURES, "ignition": IGNITION_FEATURES}


def is_active(df):
    return df["hot_zone_7"] > 0


def fit(train, feats, valid=None, rounds=None):
    dtr = lgb.Dataset(train[feats], train["fire_next7"])
    if valid is not None:
        dva = lgb.Dataset(valid[feats], valid["fire_next7"], reference=dtr)
        return lgb.train(PARAMS, dtr, num_boost_round=3000, valid_sets=[dva],
                         callbacks=[lgb.early_stopping(100, verbose=False)])
    return lgb.train(PARAMS, dtr, num_boost_round=rounds)


def pick_threshold(y, p):
    """Threshold maximising F0.5 (weights precision over recall = fewer false alarms)."""
    best_t, best_f = 0.5, -1.0
    for t in np.linspace(0.02, 0.95, 94):
        pred = p >= t
        tp = (pred & (y == 1)).sum()
        prec = tp / max(pred.sum(), 1); rec = tp / max((y == 1).sum(), 1)
        f = 1.25 * prec * rec / max(0.25 * prec + rec, 1e-9)
        if f > best_f:
            best_t, best_f = t, f
    return float(best_t)


def train_pair(train):
    """Train spread + ignition models. Returns models, tree counts, thresholds."""
    models, rounds, thr = {}, {}, {}
    for kind, feats in KINDS.items():
        sub = train[is_active(train) == (kind == "spread")]
        tr, va = sub[sub["date"] < VALID_START], sub[sub["date"] >= VALID_START]
        m = fit(tr, feats, va)
        rounds[kind] = max(int(m.best_iteration), 50)
        thr[kind] = pick_threshold(va["fire_next7"].to_numpy(), m.predict(va[feats]))
        models[kind] = fit(sub, feats, rounds=rounds[kind])
    return models, rounds, thr


def score(df, models, thr):
    df = df.copy()
    act = is_active(df).to_numpy()
    df["p"] = 0.0
    df.loc[act, "p"] = models["spread"].predict(df.loc[act, FEATURES])
    df.loc[~act, "p"] = models["ignition"].predict(df.loc[~act, IGNITION_FEATURES])
    df["thr"] = np.where(act, thr["spread"], thr["ignition"])
    df["alert"] = df["p"] >= df["thr"]
    df["base"] = df["dry_days"] + df["deficit_mm"] / 1000.0   # simple rule; deficit breaks ties
    return df


def persistent(df, col):
    df = df.sort_values(["zone_id", "date"])
    prev = df.groupby("zone_id")[col].shift(1)
    return (df[col] & prev.eq(True)).reindex(df.index)


def prf(y, pred):
    tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    return {"precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1),
            "alerts": int(pred.sum())}


def patrol(df, col):
    """Each day check the top-N zones by `col`; share of fire_next7 zone-days caught."""
    top = df.sort_values(col, ascending=False).groupby("date").head(PATROLS_PER_DAY)
    return float(top["fire_next7"].sum() / max(df["fire_next7"].sum(), 1))


def random_patrol(df):
    zones_per_day = df.groupby("date")["zone_id"].nunique().mean()
    return float(min(1.0, PATROLS_PER_DAY / zones_per_day))


def new_fire_events(df, quiet_days=14):
    """(zone, date) where a fire starts after at least 14 quiet days."""
    ev = []
    for zid, g in df.sort_values("date").groupby("zone_id"):
        on = (g["hot_zone_1"].to_numpy() > 0).astype(float)
        quiet = pd.Series(on).shift(1).rolling(quiet_days, min_periods=quiet_days).sum().to_numpy()
        starts = (on > 0) & (quiet == 0)
        ev += [(zid, d) for d in g["date"].to_numpy()[starts]]
    return ev


def early_warning(df, col, events):
    """For each new fire: was the zone flagged in the 7 days before? Earliest flag = lead time."""
    flagged = set(map(tuple, df.loc[df[col], ["zone_id", "date"]].itertuples(index=False)))
    leads = []
    for zid, d in events:
        lead = 0
        for k in range(7, 0, -1):
            if (zid, pd.Timestamp(d) - pd.Timedelta(days=k)) in flagged:
                lead = k
                break
        leads.append(lead)
    leads = np.array(leads)
    warned = leads > 0
    return {"new_fires": int(len(leads)),
            "warned_share": float(warned.mean()) if len(leads) else 0.0,
            "median_days_ahead": float(np.median(leads[warned])) if warned.any() else 0.0}


def report(name, df):
    y = df["fire_next7"].to_numpy()
    q = df[~is_active(df)]
    yq = q["fire_next7"].to_numpy()
    n_alerts = int(df["alert"].sum())
    base_cut = np.sort(df["base"].to_numpy())[::-1][max(n_alerts - 1, 0)] if n_alerts else np.inf
    df = df.assign(alert_base=df["base"] >= base_cut)
    df["alert2"] = persistent(df, "alert")
    df["alert_base2"] = persistent(df, "alert_base")
    # For new-fire early warning, rank quiet zones each day (top N = patrol targets).
    q = df[~is_active(df)].copy()
    q["flag_model"] = q.groupby("date")["p"].rank(ascending=False, method="first") <= PATROLS_PER_DAY
    q["flag_base"] = q.groupby("date")["base"].rank(ascending=False, method="first") <= PATROLS_PER_DAY
    ev = new_fire_events(df)

    res = {
        "rows": int(len(df)), "fire_rate": float(y.mean()),
        "random_patrol_catch": random_patrol(df),
        "model": {
            "roc_auc": float(roc_auc_score(y, df["p"])),
            "pr_auc": float(average_precision_score(y, df["p"])),
            "patrol_catch": patrol(df, "p"),
            "alerts_2day": prf(y, df["alert2"].to_numpy()),
            "new_fire": {
                "roc_auc": float(roc_auc_score(yq, q["p"])) if yq.any() else None,
                "patrol_catch": patrol(q, "p"),
                **early_warning(q, "flag_model", ev)}},
        "simple_rule": {
            "roc_auc": float(roc_auc_score(y, df["base"])),
            "pr_auc": float(average_precision_score(y, df["base"])),
            "patrol_catch": patrol(df, "base"),
            "alerts_2day": prf(y, df["alert_base2"].to_numpy()),
            "new_fire": {
                "roc_auc": float(roc_auc_score(yq, q["base"])) if yq.any() else None,
                "patrol_catch": patrol(q, "base"),
                **early_warning(q, "flag_base", ev)}},
    }
    print(f"\n=== {name} ===")
    print(f"{len(df):,} test rows | fire rate {y.mean():.1%} | "
          f"random patrols would catch {res['random_patrol_catch']:.0%}")
    print(f"{'':12s} {'ALL FIRES':^40s} | {'NEW FIRES (quiet zones)':^44s}")
    for k in ["model", "simple_rule"]:
        r = res[k]; n = r["new_fire"]
        print(f"{k:12s} ROC {r['roc_auc']:.2f} | patrol catch {r['patrol_catch']:.0%} | "
              f"precision {r['alerts_2day']['precision']:.0%} | "
              f"ROC {n['roc_auc'] or 0:.2f} | patrol catch {n['patrol_catch']:.0%} | "
              f"warned {n['warned_share']:.0%} of {n['new_fires']} "
              f"({n['median_days_ahead']:.0f} days ahead)")
    return res, df


def main():
    df = pd.read_csv("data/dataset.csv.gz", parse_dates=["date"])
    train, test = df[df["date"] < TEST_START], df[df["date"] >= TEST_START]

    models, rounds, thr = train_pair(train)
    res_time, scored = report("Test 1: future years (2023 onwards), all zones",
                              score(test, models, thr))

    m_id, _, thr_id = train_pair(train[train["country"] == "ID"])
    res_country, _ = report("Test 2: trained on Indonesia only, tested on Malaysia",
                            score(test[test["country"] == "MY"], m_id, thr_id))

    importance = {}
    for kind, feats in KINDS.items():
        imp = pd.Series(models[kind].feature_importance("gain"), index=feats)
        imp = (imp / imp.sum()).sort_values(ascending=False)
        importance[kind] = imp.round(4).to_dict()
        print(f"\n{kind.upper()} model relies most on:")
        print(imp.head(6).map("{:.0%}".format).to_string())

    # Final models for the app: same settings, trained on all years.
    for kind, feats in KINDS.items():
        sub = df[is_active(df) == (kind == "spread")]
        fit(sub, feats, rounds=rounds[kind]).save_model(str(MODELS / f"model_{kind}.txt"))

    metrics = {"thresholds": thr, "trees": rounds, "test_start": TEST_START,
               "patrols_per_day": PATROLS_PER_DAY,
               "features": {k: v for k, v in KINDS.items()},
               "future_years": res_time, "unseen_country": res_country,
               "importance": importance}
    (MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    scored[["zone_id", "date", "p", "fire_next7", "hot_zone_1", "hot_zone_7"]].to_csv(
        MODELS / "test_scores.csv.gz", index=False)
    print("\nSaved models/model_spread.txt, models/model_ignition.txt, "
          "models/metrics.json, models/test_scores.csv.gz")


if __name__ == "__main__":
    main()
