"""Fact tables: ``txn`` and ``settlement`` (vectorised with numpy).

The transaction intensity is a product of a per-terminal base rate, a
month factor, a day-of-week factor (stronger for the seasonal group) and the
planted stories; outcome probabilities are modified inside the story windows.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .common import Dataset, N_DAYS, T0, iso_week_label, parse_ts, rng_for, sec, secs_to_ts
from .reference import PROC_LATENCY, ROUTE_PRIORITY_P
from .stories import (BAD_DEPLOY, BASE_DOW, FIRMWARE, FX_STORY, MONTH_FACTOR, OUTAGE, SEASONAL_GROUP)

TARGET_TXN = 248_000
HOUR_W = np.array([0.10, 0.05, 0.05, 0.05, 0.10, 0.20, 0.30, 0.50, 1.50, 2.50, 3.50, 4.00,
                   5.00, 4.50, 3.50, 3.50, 4.00, 5.00, 5.50, 4.50, 3.00, 1.80, 0.80, 0.40])
HOUR_W = HOUR_W / HOUR_W.sum()

P_DECLINE, P_TIMEOUT = 0.065, 0.012
APPROVED_CODES = (["00", "10"], [0.97, 0.03])
DECLINE_CODES = (["05", "51", "54", "57", "61", "62", "65", "14", "96"],
                 [0.32, 0.28, 0.08, 0.07, 0.05, 0.05, 0.05, 0.03, 0.07])
TIMEOUT_CODES = (["91", "68", "Z1", "Z3"], [0.37, 0.33, 0.22, 0.08])
STATUS_APPROVED = (["CAPTURED", "AUTHORIZED", "REVERSED", "REFUNDED"], [0.94, 0.02, 0.025, 0.015])
SCHEMES = (["VISA", "MASTERCARD", "AMEX", "JCB", "DINERS", "MAESTRO"], [0.47, 0.42, 0.05, 0.02, 0.01, 0.03])
SCHEMES_JP = (["VISA", "MASTERCARD", "AMEX", "JCB", "DINERS", "MAESTRO"], [0.35, 0.30, 0.05, 0.27, 0.02, 0.01])


def group_ancestors(ds: Dataset) -> dict[int, list[int]]:
    """group_id -> [group_id, parent, grandparent, ...]."""
    g = ds["dim_merchant_group"]
    parent = {int(r.group_id): (None if pd.isna(r.parent_group_id) else int(r.parent_group_id)) for r in g.itertuples()}
    out = {}
    for gid in parent:
        chain, cur = [], gid
        while cur is not None:
            chain.append(cur)
            cur = parent[cur]
        out[gid] = chain
    return out


def merchants_in_group(ds: Dataset, group_name: str) -> set[int]:
    """All merchant_ids whose group is ``group_name`` or one of its descendants."""
    g = ds["dim_merchant_group"]
    gid = int(g.loc[g.name == group_name, "group_id"].iloc[0])
    anc = group_ancestors(ds)
    m = ds["dim_merchant"]
    return {int(r.merchant_id) for r in m.itertuples() if gid in anc[int(r.group_id)]}


def fx_matrix(ds: Dataset) -> tuple[np.ndarray, int]:
    """rate[currency_id, day_index] for the whole fx_rate table; returns (matrix, n_days)."""
    fx = ds["fx_rate"]
    n_days = fx.rate_date.nunique()
    mat = np.zeros((ds["dim_currency"].currency_id.max() + 1, n_days))
    day_idx = (pd.to_datetime(fx.rate_date) - pd.Timestamp(T0)).dt.days.to_numpy()
    mat[fx.currency_id.to_numpy(), day_idx] = fx.rate_to_eur.to_numpy()
    return mat, n_days


def _merchant_at_matrix(ds: Dataset) -> np.ndarray:
    """merchant_at[terminal_id, day] (0 = not assigned)."""
    n_t = int(ds["dim_terminal"].terminal_id.max())
    mat = np.zeros((n_t + 1, N_DAYS), dtype=np.int32)
    for a in ds["terminal_assignment"].itertuples():
        d0 = max(0, (parse_ts(a.valid_from) - T0).days)
        d1 = N_DAYS if a.valid_to is None or pd.isna(a.valid_to) else min(N_DAYS, (parse_ts(a.valid_to) - T0).days)
        if d1 > d0:
            mat[a.terminal_id, d0:d1] = a.merchant_id
    return mat


def build_txn(ds: Dataset) -> None:
    """Generate the ``txn`` table (~250k rows) with all planted phenomena."""
    rng = rng_for("txn")
    term = ds["dim_terminal"]
    merch = ds["dim_merchant"]
    models = ds["dim_terminal_model"]
    routes = ds["route"]
    n_t = int(term.terminal_id.max())

    merchant_at = _merchant_at_matrix(ds)                          # (n_t+1, N_DAYS)
    mcc_code = dict(zip(ds["dim_mcc"].mcc_id, ds["dim_mcc"].mcc_code))
    m_mcc = np.zeros(int(merch.merchant_id.max()) + 1, dtype=object)
    m_cur = np.zeros_like(m_mcc, dtype=np.int32)
    m_country = np.zeros_like(m_cur)
    c_cur = dict(zip(ds["dim_country"].country_id, ds["dim_country"].currency_id))
    for r in merch.itertuples():
        m_mcc[r.merchant_id] = mcc_code[r.mcc_id]
        m_cur[r.merchant_id] = c_cur[r.country_id]
        m_country[r.merchant_id] = r.country_id
    seasonal = merchants_in_group(ds, SEASONAL_GROUP["group"])
    is_seasonal_m = np.zeros(len(m_mcc), dtype=bool)
    is_seasonal_m[list(seasonal)] = True

    # --- intensity matrix
    params = ds.meta["mcc_params"]
    first_merchant = np.array([next((x for x in merchant_at[t] if x > 0), 0) for t in range(n_t + 1)])
    rate_factor = np.array([params[m_mcc[m]]["rate"] if m > 0 else 0.0 for m in first_merchant])
    base = rate_factor * rng.lognormal(0.0, 0.5, n_t + 1)
    days = np.arange(N_DAYS)
    dates = [T0.date() + timedelta(days=int(d)) for d in days]
    dow = np.array([d.weekday() for d in dates])
    month_f = np.array([MONTH_FACTOR[d.month - 1] for d in dates])
    base_dow = np.array(BASE_DOW)[dow]
    growth = 1.0 + SEASONAL_GROUP["growth"] * days / (N_DAYS - 1)
    bump = np.array([SEASONAL_GROUP["week_bump"].get(iso_week_label(d), 1.0) for d in dates])
    seasonal_dow = np.array(SEASONAL_GROUP["dow"])[dow] * growth * bump
    assigned = merchant_at > 0
    is_seasonal = is_seasonal_m[merchant_at] & assigned
    lam = base[:, None] * month_f[None, :] * np.where(is_seasonal, seasonal_dow[None, :], base_dow[None, :]) * assigned
    lam *= TARGET_TXN / lam.sum()
    counts = rng.poisson(lam)
    flat = np.repeat(np.arange(counts.size), counts.ravel())
    t_id = (flat // N_DAYS).astype(np.int32)
    d_idx = (flat % N_DAYS).astype(np.int32)
    n = len(t_id)

    # --- timestamps
    hour = rng.choice(24, size=n, p=HOUR_W)
    secs = d_idx.astype(np.int64) * 86400 + hour * 3600 + rng.integers(0, 3600, n)

    # --- merchant / currency / amount
    merchant = merchant_at[t_id, d_idx]
    currency = m_cur[merchant]
    fx, _ = fx_matrix(ds)
    exponent = np.zeros(fx.shape[0], dtype=np.int64)
    exponent[ds["dim_currency"].currency_id.to_numpy()] = ds["dim_currency"].exponent.to_numpy()
    med = np.array([params[m_mcc[m]]["median"] for m in merchant])
    sig = np.array([params[m_mcc[m]]["sigma"] for m in merchant])
    amount_eur = np.exp(np.log(med) + sig * rng.standard_normal(n))
    amount_local = amount_eur / fx[currency, d_idx]
    amount_minor = np.maximum(1, np.floor(amount_local * 10.0 ** exponent[currency] + 0.5)).astype(np.int64)

    # --- route (by the terminal's acquirer and route priority)
    t_acq = np.zeros(n_t + 1, dtype=np.int32)
    t_acq[term.terminal_id.to_numpy()] = term.acquirer_id.to_numpy()
    t_model = np.zeros(n_t + 1, dtype=np.int32)
    t_model[term.terminal_id.to_numpy()] = term.model_id.to_numpy()
    acq = t_acq[t_id]
    route_by_acq = {}
    for a, grp in routes.sort_values("priority").groupby("acquirer_id"):
        ids = grp.route_id.to_numpy()
        p = np.array([ROUTE_PRIORITY_P[pr] for pr in grp.priority])
        route_by_acq[a] = (ids, p / p.sum())
    route = np.zeros(n, dtype=np.int32)
    for a, (ids, p) in route_by_acq.items():
        m = acq == a
        route[m] = rng.choice(ids, size=m.sum(), p=p)
    route_proc = dict(zip(routes.route_id, routes.processor_id))
    proc_name = dict(zip(ds["dim_processor"].processor_id, ds["dim_processor"].name))
    route_lat = np.zeros(int(routes.route_id.max()) + 1)
    for rid in routes.route_id:
        route_lat[rid] = PROC_LATENCY[proc_name[route_proc[rid]]]

    # --- story windows
    acq_name = dict(zip(ds["dim_acquirer"].name, ds["dim_acquirer"].acquirer_id))
    fam = dict(zip(models.model_id, models.firmware_family))
    bad_route = int(routes.loc[routes.code == BAD_DEPLOY["route_code"], "route_id"].iloc[0])
    in_deploy = (route == bad_route) & (secs >= sec(parse_ts(BAD_DEPLOY["effect_from"]))) & \
                (secs < sec(parse_ts(BAD_DEPLOY["effect_to"])))
    in_outage = (acq == acq_name[OUTAGE["acquirer"]]) & (secs >= sec(parse_ts(OUTAGE["from_ts"]))) & \
                (secs < sec(parse_ts(OUTAGE["to_ts"])))
    fw_models = {mid for mid, f in fam.items() if f == FIRMWARE["family"]}
    in_fw = np.isin(t_model[t_id], list(fw_models)) & (secs >= sec(parse_ts(FIRMWARE["from_ts"])))

    def outcomes(rng, n, in_deploy, in_outage, in_fw):
        p_to = np.full(n, P_TIMEOUT)
        p_to[in_deploy] = BAD_DEPLOY["timeout_prob"]
        p_to[in_outage] = OUTAGE["timeout_prob"]
        p_de = np.full(n, P_DECLINE) + FIRMWARE["decline_add"] * in_fw
        u = rng.random(n)
        cat = np.where(u < p_to, 2, np.where(u < p_to + p_de, 1, 0))     # 0 approved, 1 decline, 2 timeout
        code = np.empty(n, dtype=object)
        m = cat == 0
        code[m] = rng.choice(APPROVED_CODES[0], size=m.sum(), p=APPROVED_CODES[1])
        m = cat == 1
        code[m] = rng.choice(DECLINE_CODES[0], size=m.sum(), p=DECLINE_CODES[1])
        m = (cat == 1) & in_fw
        extra = rng.random(n) < FIRMWARE["decline_add"] / (P_DECLINE + FIRMWARE["decline_add"])
        mm = m & extra
        code[mm] = rng.choice(list(FIRMWARE["extra_codes"]), size=mm.sum(), p=list(FIRMWARE["extra_codes"].values()))
        m = cat == 2
        code[m] = rng.choice(TIMEOUT_CODES[0], size=m.sum(), p=TIMEOUT_CODES[1])
        m = (cat == 2) & in_deploy
        code[m] = "Z1"
        m = (cat == 2) & in_outage
        code[m] = rng.choice(list(OUTAGE["timeout_codes"]), size=m.sum(), p=list(OUTAGE["timeout_codes"].values()))
        return cat, code

    cat, code = outcomes(rng, n, in_deploy, in_outage, in_fw)

    # --- retries during the acquirer outage (cardholder/terminal re-tries a timed-out payment)
    retry_src = np.flatnonzero(in_outage & (cat == 2) & (rng.random(n) < OUTAGE["retry_prob"]))
    n_r = len(retry_src)
    r_secs = secs[retry_src] + rng.integers(20, 90, n_r)
    r_cat, r_code = outcomes(rng, n_r, np.zeros(n_r, bool), np.ones(n_r, bool), in_fw[retry_src])

    def concat(a, b):
        return np.concatenate([a, b])
    t_id, d_idx, secs = concat(t_id, t_id[retry_src]), concat(d_idx, d_idx[retry_src]), concat(secs, r_secs)
    merchant, currency = concat(merchant, merchant[retry_src]), concat(currency, currency[retry_src])
    amount_minor, route, acq = concat(amount_minor, amount_minor[retry_src]), concat(route, route[retry_src]), concat(acq, acq[retry_src])
    cat, code = concat(cat, r_cat), concat(code, r_code)
    in_deploy = concat(in_deploy, np.zeros(n_r, bool))
    in_outage = concat(in_outage, np.ones(n_r, bool))
    n = len(t_id)
    ds.meta["n_outage_retries"] = int(n_r)

    # --- latency
    lat = np.exp(np.log(route_lat[route]) + 0.35 * rng.standard_normal(n))
    lat = np.where(cat == 1, lat * 1.05, lat)
    lat = np.where(in_deploy & (cat != 2), lat * BAD_DEPLOY["latency_mult"], lat)
    lat = np.where(in_outage & (cat != 2), lat * 2.5, lat)
    lat = np.where(cat == 2, rng.uniform(8000, 30000, n), lat)
    latency_ms = np.maximum(35, np.floor(lat + 0.5)).astype(np.int64)

    # --- status, card scheme
    status_code = np.where(cat == 0, rng.choice(STATUS_APPROVED[0], size=n, p=STATUS_APPROVED[1]), "FAILED")
    status_id_map = dict(zip(ds["txn_status_dict"].code, ds["txn_status_dict"].status_id))
    status_id = np.vectorize(status_id_map.get)(status_code)
    jp_country = int(ds["dim_country"].loc[ds["dim_country"].iso2 == "JP", "country_id"].iloc[0])
    is_jp = m_country[merchant] == jp_country
    scheme = rng.choice(SCHEMES[0], size=n, p=SCHEMES[1])
    scheme[is_jp] = rng.choice(SCHEMES_JP[0], size=is_jp.sum(), p=SCHEMES_JP[1])

    order = np.argsort(secs, kind="stable")
    txn = pd.DataFrame({
        "txn_id": np.arange(1, n + 1),
        "ts_utc": secs_to_ts(secs[order]),
        "terminal_id": t_id[order],
        "amount_minor": amount_minor[order],
        "currency_id": currency[order],
        "status_id": status_id[order],
        "response_code": code[order],
        "route_id": route[order],
        "latency_ms": latency_ms[order],
        "card_scheme": scheme[order],
    })
    ds["txn"] = txn
    # internal helper columns for validation (never written to the DB)
    ds.meta["txn_secs"] = secs[order]
    ds.meta["txn_merchant"] = merchant[order]
    ds.meta["txn_day"] = d_idx[order]
    ds.meta["txn_acquirer"] = acq[order]
    ds.meta["bad_route_id"] = bad_route


def build_settlement(ds: Dataset) -> None:
    """One settlement row per CAPTURED transaction, converted to EUR by the fx-service.

    Inside the stale-cache window (Story 2) the fx-service applies the rate
    snapshot of ``FX_STORY['stale_rate_date']`` instead of the settlement date.
    """
    rng = rng_for("settlement")
    txn = ds["txn"]
    captured_id = int(ds["txn_status_dict"].loc[ds["txn_status_dict"].code == "CAPTURED", "status_id"].iloc[0])
    m = (txn.status_id == captured_id).to_numpy()
    secs = ds.meta["txn_secs"][m]
    day = ds.meta["txn_day"][m]
    hour = (secs % 86400) // 3600
    settle_day = day + np.where(hour < 22, 1, 2)
    settled_secs = settle_day.astype(np.int64) * 86400 + 6 * 3600 + rng.integers(0, 1800, m.sum())

    fx, n_fx_days = fx_matrix(ds)
    cur = txn.currency_id.to_numpy()[m]
    exponent = np.zeros(fx.shape[0], dtype=np.int64)
    exponent[ds["dim_currency"].currency_id.to_numpy()] = ds["dim_currency"].exponent.to_numpy()
    assert settle_day.max() < n_fx_days
    rate = fx[cur, settle_day]
    stale = (settled_secs >= sec(parse_ts(FX_STORY["stale_from"]))) & (settled_secs < sec(parse_ts(FX_STORY["stale_to"])))
    stale_day = (date.fromisoformat(FX_STORY["stale_rate_date"]) - T0.date()).days
    rate = np.where(stale, fx[cur, stale_day], rate)
    amount_minor = txn.amount_minor.to_numpy()[m]
    eur_minor = np.floor(amount_minor / 10.0 ** exponent[cur] * rate * 100 + 0.5).astype(np.int64)

    # fee schedule valid at settlement time, by the terminal's acquirer
    acq = ds.meta["txn_acquirer"][m]
    fs = ds["fee_schedule"]
    fee_id = np.zeros(m.sum(), dtype=np.int64)
    bps = np.zeros(m.sum(), dtype=np.int64)
    fixed = np.zeros(m.sum(), dtype=np.int64)
    for r in fs.itertuples():
        lo = sec(parse_ts(r.valid_from)) if r.valid_from >= "2025" else -10**12
        hi = sec(parse_ts(r.valid_to)) if isinstance(r.valid_to, str) else 10**12
        sel = (acq == r.acquirer_id) & (settled_secs >= lo) & (settled_secs < hi)
        fee_id[sel], bps[sel], fixed[sel] = r.fee_schedule_id, r.pct_bps, r.fixed_minor
    assert (fee_id > 0).all()
    fee_minor = np.floor(eur_minor * bps / 10000.0 + 0.5).astype(np.int64) + fixed

    ds["settlement"] = pd.DataFrame({
        "settlement_id": np.arange(1, m.sum() + 1),
        "txn_id": txn.txn_id.to_numpy()[m],
        "settled_at": secs_to_ts(settled_secs),
        "fx_rate_applied": np.round(rate, 8),
        "settled_eur_minor": eur_minor,
        "fee_minor": fee_minor,
        "fee_schedule_id": fee_id,
    })
    ds.meta["n_stale_settlements"] = int(stale.sum())
