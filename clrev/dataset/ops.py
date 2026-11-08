"""Operational tables: deployment, config_change, incident, incident_link, service_event.

Random background activity plus the planted stories (see stories.py).  All
rows carrying story semantics are created here with exact timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .common import Dataset, N_DAYS, T0, parse_ts, rng_for, sec, secs_to_ts, ts
from .reference import COMPONENTS
from .stories import (BAD_DEPLOY, BAD_DEPLOY_NOISE_ERROR_TS, BAD_DEPLOY_PRELUDE_CFG, BAD_DEPLOY_RESTART,
                      FIRMWARE, FX_STORY, OUTAGE)

TARGET_EVENTS_BASELINE = 136_000
COMPONENT_W = {"api-edge": 0.18, "auth-router": 0.16, "acquirer-gateway": 0.14, "risk-engine": 0.10,
               "settlement-engine": 0.08, "ledger": 0.06, "terminal-fleet-mgr": 0.06, "notification-svc": 0.05,
               "reporting-etl": 0.05, "tokenization-vault": 0.04, "scheduler": 0.03, "fx-service": 0.05}
LEVEL_MIX = {"api-edge": [0.80, 0.15, 0.045, 0.005], "auth-router": [0.78, 0.16, 0.055, 0.005],
             "acquirer-gateway": [0.74, 0.18, 0.075, 0.005], "default": [0.80, 0.14, 0.055, 0.005]}
LEVELS = ["INFO", "WARN", "ERROR", "FATAL"]
TYPES_BY_LEVEL = {
    "INFO": (["HEALTHCHECK", "REQUEST_OK", "CONFIG_RELOAD", "CACHE_REFRESH", "BATCH_DONE"], [0.35, 0.45, 0.04, 0.08, 0.08]),
    "WARN": (["LATENCY_HIGH", "RETRY", "RATE_LIMIT", "CACHE_MISS_STORM", "GC_PAUSE", "CERT_EXPIRING"],
             [0.30, 0.30, 0.15, 0.10, 0.12, 0.03]),
    "ERROR": (["UPSTREAM_TIMEOUT", "POOL_EXHAUSTED", "DB_SLOW_QUERY", "AUTH_FAILED", "CIRCUIT_OPEN", "UNHANDLED_EXCEPTION"],
              [0.30, 0.10, 0.20, 0.15, 0.05, 0.20]),
    "FATAL": (["PROCESS_CRASH", "OOM_KILL"], [0.6, 0.4]),
}
ROUTE_COMPONENTS = {"acquirer-gateway", "auth-router"}
EXCEPTIONS = ["NullPointerException", "IllegalStateException", "SocketTimeoutException", "JsonParseException",
              "ConcurrentModificationException", "IndexOutOfBoundsException"]
BATCH_JOBS = ["settle-daily", "fx-import", "ledger-close", "report-merchant", "cleanup-tokens", "retry-sweep"]
VERSION_MAJOR = {"api-edge": 7, "auth-router": 4, "acquirer-gateway": 3, "tokenization-vault": 2, "risk-engine": 5,
                 "fx-service": 1, "settlement-engine": 6, "ledger": 3, "terminal-fleet-mgr": 2, "notification-svc": 1,
                 "reporting-etl": 9, "scheduler": 1}
DEPLOYS_PER_YEAR = {"edge": 18, "core": 14, "support": 8, "batch": 10}
CONFIG_KEYS = [("timeout_ms", ["3000", "5000", "8000", "10000"]), ("retry.max_attempts", ["2", "3", "4"]),
               ("pool.max_connections", ["32", "48", "64", "96", "128"]), ("log.level", ["INFO", "DEBUG", "WARN"]),
               ("feature.new_router", ["false", "true"]), ("cache.ttl_seconds", ["60", "120", "300", "600"]),
               ("autoscale.min_replicas", ["2", "3", "4", "6"]), ("jvm.heap_mb", ["2048", "3072", "4096"]),
               ("rate_limit.rps", ["200", "250", "400", "500"]), ("circuit.failure_threshold", ["5", "10", "20"])]
ROOT_CAUSE_TYPES = {
    "BAD_DEPLOY": (["UNHANDLED_EXCEPTION", "POOL_EXHAUSTED"], ["LATENCY_HIGH", "RETRY"]),
    "CONFIG_ERROR": (["AUTH_FAILED", "UNHANDLED_EXCEPTION"], ["RETRY", "RATE_LIMIT"]),
    "THIRD_PARTY_OUTAGE": (["UPSTREAM_TIMEOUT", "CIRCUIT_OPEN"], ["RETRY", "LATENCY_HIGH"]),
    "CAPACITY": (["POOL_EXHAUSTED", "DB_SLOW_QUERY"], ["LATENCY_HIGH", "GC_PAUSE"]),
    "HARDWARE": (["DB_SLOW_QUERY", "UNHANDLED_EXCEPTION"], ["RETRY", "LATENCY_HIGH"]),
    "NETWORK": (["UPSTREAM_TIMEOUT", "CIRCUIT_OPEN"], ["RETRY", "LATENCY_HIGH"]),
    "CERT_EXPIRY": (["AUTH_FAILED"], ["CERT_EXPIRING", "RETRY"]),
    "UNKNOWN": (["UNHANDLED_EXCEPTION", "UPSTREAM_TIMEOUT"], ["LATENCY_HIGH", "RETRY"]),
    "FIRMWARE_DEFECT": (["UNHANDLED_EXCEPTION"], ["DECLINE_RATE_HIGH"]),
}
# random incidents: (component, opened_at, duration_min, severity, root cause, summary)
RANDOM_INCIDENTS = [
    ("api-edge", "2025-01-14 08:52:00", 95, "SEV3", "CAPACITY", "Elevated 5xx at the edge during morning peak"),
    ("reporting-etl", "2025-01-28 03:15:00", 240, "SEV4", "HARDWARE", "Nightly merchant report delayed (disk failure on worker)"),
    ("risk-engine", "2025-02-06 15:40:00", 70, "SEV3", "CONFIG_ERROR", "Risk rules rejecting valid tokens after rule-set reload"),
    ("acquirer-gateway", "2025-02-19 11:05:00", 55, "SEV2", "NETWORK", "Packet loss towards NordPay endpoint"),
    ("settlement-engine", "2025-03-27 06:30:00", 180, "SEV3", "CAPACITY", "Settlement batch running late"),
    ("tokenization-vault", "2025-04-09 13:20:00", 45, "SEV2", "CERT_EXPIRY", "Vault client certificate expired"),
    ("api-edge", "2025-04-23 17:10:00", 60, "SEV3", "UNKNOWN", "Intermittent 502s from edge nodes in eu-west"),
    ("ledger", "2025-05-06 09:45:00", 120, "SEV3", "BAD_DEPLOY", "Ledger posting lag after release"),
    ("notification-svc", "2025-06-03 12:00:00", 150, "SEV4", "THIRD_PARTY_OUTAGE", "SMS provider degraded"),
    ("acquirer-gateway", "2025-06-24 16:35:00", 40, "SEV3", "NETWORK", "TLS handshakes failing to Gulf Card Services"),
    ("risk-engine", "2025-07-15 10:25:00", 85, "SEV2", "CAPACITY", "Risk scoring latency above SLO"),
    ("scheduler", "2025-07-29 02:05:00", 200, "SEV4", "HARDWARE", "Scheduler leader election flapping"),
    ("api-edge", "2025-08-12 14:50:00", 50, "SEV3", "CONFIG_ERROR", "Rate limits applied to internal clients"),
    ("settlement-engine", "2025-09-02 07:20:00", 130, "SEV3", "BAD_DEPLOY", "Duplicate fee lines in settlement export"),
    ("auth-router", "2025-10-07 11:20:00", 110, "SEV2", "CAPACITY", "Thread starvation under promotional traffic"),
    ("reporting-etl", "2025-10-21 04:40:00", 260, "SEV4", "UNKNOWN", "ETL checkpoint corruption"),
    ("tokenization-vault", "2025-11-04 09:05:00", 75, "SEV3", "CONFIG_ERROR", "HSM partition quota exhausted"),
    ("acquirer-gateway", "2025-11-18 15:30:00", 65, "SEV2", "THIRD_PARTY_OUTAGE", "Sakura Card Acquiring maintenance overrun"),
    ("ledger", "2025-12-02 10:15:00", 90, "SEV3", "CAPACITY", "Ledger DB connection saturation"),
    ("fx-service", "2025-12-16 08:05:00", 35, "SEV4", "THIRD_PARTY_OUTAGE", "FX rate feed unavailable (fallback to previous day)"),
]
# operator story: which random incidents (index into RANDOM_INCIDENTS) get a change shortly before by whom
#   (index, operator, kind, minutes_before)
STORY_CHANGES = [
    (2, "r.svensson", "config", 38), (7, "r.svensson", "config", 21), (10, "r.svensson", "config", 44),
    (16, "r.svensson", "config", 40),                                        # q18 target (H2)
    (3, "d.kowalski", "deploy", 50),                                        # + BAD_DEPLOY itself = 2
    (0, "j.mueller", "config", 95), (13, "m.ferreira", "deploy", 80), (14, "a.nowak", "deploy", 105),  # outside 60 min
    (16, "j.mueller", "config", 4),                                         # q18 decoy (after first ERROR)
]
Q18_INCIDENT_IDX = 16
Q18_LEAD_MIN = 12
Q16_DECOY_IDX = 14          # auth-router incident in H2 (fewer ERRORs than the March one)


def _business_time(rng: np.random.Generator, day: int) -> int:
    """Seconds since T0 of a random business-hours moment on ``day``."""
    hour = int(rng.choice(np.arange(8, 19), p=np.array([2, 5, 8, 8, 6, 5, 7, 8, 7, 4, 2]) / 62))
    return day * 86400 + hour * 3600 + int(rng.integers(0, 3600))


def build_ops(ds: Dataset) -> None:
    """Build all operational tables into ``ds``."""
    rng = rng_for("ops")
    comp = ds["dim_component"]
    comp_id = dict(zip(comp.name, comp.component_id))
    comp_team = dict(zip(comp.name, comp.team_id))
    ops = ds["operator"]
    op_id = dict(zip(ops.login, ops.operator_id))
    team_ops = {t: list(g.login) for t, g in ops.groupby("team_id")}
    sre_team = int(ds["dim_team"].loc[ds["dim_team"].name == "Platform SRE", "team_id"].iloc[0])
    sev_id = dict(zip(ds["dim_severity"].code, ds["dim_severity"].severity_id))
    rc_id = dict(zip(ds["dim_root_cause"].code, ds["dim_root_cause"].root_cause_id))

    def pick_operator(component: str) -> str:
        pool = team_ops[comp_team[component]] if rng.random() < 0.8 else team_ops[sre_team]
        return pool[int(rng.integers(len(pool)))]

    # ------------------------------------------------------------------ incidents
    incidents = []   # dicts with keys: component, opened, closed, severity, root_cause, summary, tag
    for i, (c, opened, dur, sev, rc, summ) in enumerate(RANDOM_INCIDENTS):
        o = parse_ts(opened)
        incidents.append(dict(component=c, opened=o, closed=o + timedelta(minutes=dur), severity=sev,
                              root_cause=rc, summary=summ, tag=f"random_{i}"))
    incidents.append(dict(component=BAD_DEPLOY["component"], opened=parse_ts(BAD_DEPLOY["incident_opened"]),
                          closed=parse_ts(BAD_DEPLOY["incident_closed"]), severity=BAD_DEPLOY["severity"],
                          root_cause=BAD_DEPLOY["root_cause"], tag="bad_deploy",
                          summary=f"Timeouts and high latency on route {BAD_DEPLOY['route_code']} after auth-router release"))
    incidents.append(dict(component=FX_STORY["component"], opened=parse_ts(FX_STORY["incident_opened"]),
                          closed=parse_ts(FX_STORY["incident_closed"]), severity=FX_STORY["severity"],
                          root_cause=FX_STORY["root_cause"], tag="fx_stale",
                          summary="Finance reports settlement EUR amounts not matching daily rates"))
    incidents.append(dict(component=OUTAGE["component"], opened=parse_ts(OUTAGE["incident_opened"]),
                          closed=parse_ts(OUTAGE["incident_closed"]), severity=OUTAGE["severity"],
                          root_cause=OUTAGE["root_cause"], tag="outage",
                          summary=f"{OUTAGE['acquirer']} not responding - timeouts on all its routes"))
    incidents.append(dict(component=FIRMWARE["component"], opened=parse_ts(FIRMWARE["incident_opened"]),
                          closed=parse_ts(FIRMWARE["incident_closed"]), severity=FIRMWARE["severity"],
                          root_cause=FIRMWARE["root_cause"], tag="firmware",
                          summary=f"Elevated decline rate on {FIRMWARE['family']} terminals since firmware 3.7.2"))
    incidents.sort(key=lambda x: x["opened"])
    for i, inc in enumerate(incidents):
        inc["incident_id"] = i + 1
        inc["code"] = f"INC-2025-{i + 1:04d}"
    ds.meta["incident_by_tag"] = {inc["tag"]: inc["code"] for inc in incidents}
    ds["incident"] = pd.DataFrame([(inc["incident_id"], inc["code"], ts(inc["opened"]), ts(inc["closed"]),
                                    sev_id[inc["severity"]], comp_id[inc["component"]], rc_id[inc["root_cause"]],
                                    inc["summary"]) for inc in incidents],
                                  columns=["incident_id", "code", "opened_at", "closed_at", "severity_id",
                                           "component_id", "root_cause_id", "summary"])
    inc_by_tag = {inc["tag"]: inc for inc in incidents}

    def near_incident(component: str, when: datetime) -> bool:
        """True if ``when`` is within [-75 min, +15 min] of an incident of the same component (avoid coincidences)."""
        for inc in incidents:
            if inc["component"] == component and inc["opened"] - timedelta(minutes=75) <= when <= inc["opened"] + timedelta(minutes=15):
                return True
        return False

    # ------------------------------------------------------------------ deployments
    deploys = []   # dict(component, at, operator, rolled_back, version)
    for cname, _, tier in COMPONENTS:
        n = int(rng.poisson(DEPLOYS_PER_YEAR[tier]))
        for _ in range(n):
            for _try in range(20):
                day = int(rng.integers(0, N_DAYS))
                when = T0 + timedelta(seconds=_business_time(rng, day))
                if when.weekday() >= 5 and rng.random() < 0.85:
                    continue
                if cname == BAD_DEPLOY["component"] and when.date() in (datetime(2025, 3, 11).date(), datetime(2025, 3, 12).date()):
                    continue
                if not near_incident(cname, when):
                    break
            rolled = when + timedelta(minutes=int(rng.integers(25, 200))) if rng.random() < 0.08 else None
            deploys.append(dict(component=cname, at=when, operator=pick_operator(cname), rolled_back=rolled, version=None))
    deploys.append(dict(component=BAD_DEPLOY["component"], at=parse_ts(BAD_DEPLOY["deployed_at"]), operator=BAD_DEPLOY["operator"],
                        rolled_back=parse_ts(BAD_DEPLOY["rolled_back_at"]), version=BAD_DEPLOY["version"], tag="bad"))
    deploys.append(dict(component=BAD_DEPLOY["component"], at=parse_ts(BAD_DEPLOY_RESTART["deployed_at"]),
                        operator=BAD_DEPLOY_RESTART["operator"], rolled_back=None, version=BAD_DEPLOY_RESTART["version"], tag="restart"))
    deploys.append(dict(component=BAD_DEPLOY["component"], at=parse_ts(BAD_DEPLOY["hotfix_at"]), operator=BAD_DEPLOY["operator"],
                        rolled_back=None, version=BAD_DEPLOY["hotfix_version"], tag="hotfix"))
    # config changes (random)
    changes = []   # dict(component, key, old, new, at, operator, ticket)
    for cname, _, tier in COMPONENTS:
        n = int(rng.poisson(7))
        for _ in range(n):
            for _try in range(20):
                day = int(rng.integers(0, N_DAYS))
                when = T0 + timedelta(seconds=_business_time(rng, day))
                if cname == FX_STORY["component"] and datetime(2025, 5, 9) <= when <= datetime(2025, 5, 21):
                    continue
                if cname == BAD_DEPLOY["component"] and when.date() == datetime(2025, 3, 11).date():
                    continue
                if not near_incident(cname, when):
                    break
            key, values = CONFIG_KEYS[int(rng.integers(len(CONFIG_KEYS)))]
            old, new = rng.choice(values, size=2, replace=False)
            ticket = f"OPS-{int(rng.integers(1000, 3999))}" if rng.random() < 0.7 else None
            changes.append(dict(component=cname, key=key, old=str(old), new=str(new), at=when,
                                operator=pick_operator(cname), ticket=ticket))
    # planted config changes
    p = BAD_DEPLOY_PRELUDE_CFG
    changes.append(dict(component=BAD_DEPLOY["component"], key=p["key"], old=p["old"], new=p["new"],
                        at=parse_ts(p["changed_at"]), operator=p["operator"], ticket=p["ticket"]))
    for k in ("change", "revert"):
        c = FX_STORY[k]
        changes.append(dict(component=FX_STORY["component"], key=FX_STORY["key"], old=c["old"], new=c["new"],
                            at=parse_ts(c["changed_at"]), operator=c["operator"], ticket=c["ticket"], tag=f"fx_{k}"))
    c = FX_STORY["decoy"]
    changes.append(dict(component=FX_STORY["component"], key=c["key"], old=c["old"], new=c["new"],
                        at=parse_ts(c["changed_at"]), operator=c["operator"], ticket=c["ticket"], tag="fx_decoy"))
    c = FIRMWARE["rollout_cfg"]
    changes.append(dict(component=FIRMWARE["component"], key=c["key"], old=c["old"], new=c["new"],
                        at=parse_ts(c["changed_at"]), operator=c["operator"], ticket=c["ticket"], tag="fw_rollout"))
    # operator story changes relative to random incidents
    story_keys = [("autoscale.min_replicas", "4", "2"), ("timeout_ms", "8000", "3000"), ("feature.new_router", "false", "true"),
                  ("jvm.heap_mb", "4096", "2048"), ("rate_limit.rps", "500", "200"), ("circuit.failure_threshold", "20", "5")]
    for j, (idx, login, kind, minutes) in enumerate(STORY_CHANGES):
        inc = inc_by_tag[f"random_{idx}"]
        when = inc["opened"] - timedelta(minutes=minutes)
        if kind == "deploy":
            deploys.append(dict(component=inc["component"], at=when, operator=login, rolled_back=None, version=None,
                                tag=f"story_{j}"))
        else:
            key, old, new = story_keys[j % len(story_keys)]
            changes.append(dict(component=inc["component"], key=key, old=old, new=new, at=when, operator=login,
                                ticket=f"OPS-{2500 + j}", tag=f"story_{j}"))

    # versions: sequential per component, with the planted auth-router versions pinned
    deploys.sort(key=lambda d: d["at"])
    for cname in comp.name:
        lst = [d for d in deploys if d["component"] == cname]
        major = VERSION_MAJOR[cname]
        if cname == BAD_DEPLOY["component"]:
            i_bad = next(i for i, d in enumerate(lst) if d.get("tag") == "bad")
            minor = 18 - i_bad
            for i, d in enumerate(lst):
                if d.get("tag") in ("bad", "restart", "hotfix"):
                    continue
                if i > i_bad:
                    minor += 1
                d["version"] = f"v{major}.{minor}.0"
                if i < i_bad:
                    minor += 1
        else:
            minor, patch = int(rng.integers(3, 30)), 0
            for d in lst:
                if rng.random() < 0.3:
                    patch += 1
                else:
                    minor, patch = minor + 1, 0
                d["version"] = f"v{major}.{minor}.{patch}"
    ds["deployment"] = pd.DataFrame([(i + 1, comp_id[d["component"]], d["version"], ts(d["at"]), op_id[d["operator"]],
                                      ts(d["rolled_back"]) if d["rolled_back"] else None) for i, d in enumerate(deploys)],
                                    columns=["deployment_id", "component_id", "version", "deployed_at", "operator_id",
                                             "rolled_back_at"])
    for i, d in enumerate(deploys):
        d["deployment_id"] = i + 1
    changes.sort(key=lambda c: c["at"])
    ds["config_change"] = pd.DataFrame([(i + 1, comp_id[c["component"]], c["key"], c["old"], c["new"], ts(c["at"]),
                                         op_id[c["operator"]], c["ticket"]) for i, c in enumerate(changes)],
                                       columns=["change_id", "component_id", "key", "old_value", "new_value",
                                                "changed_at", "operator_id", "ticket"])
    for i, c in enumerate(changes):
        c["change_id"] = i + 1
    ds.meta["change_by_tag"] = {c["tag"]: c["change_id"] for c in changes if "tag" in c}
    ds.meta["deploy_by_tag"] = {d["tag"]: d["deployment_id"] for d in deploys if "tag" in d}

    # ------------------------------------------------------------------ service events
    ev_rng = rng_for("events")
    events = _baseline_events(ds, ev_rng, comp_id)
    events += _fx_cache_events(ds, comp_id)
    events += _marker_events(ds, deploys, changes, comp_id)
    links = []
    events += _story_events(ds, ev_rng, comp_id, inc_by_tag, links)
    events += _random_incident_events(ds, ev_rng, comp_id, incidents, links)
    ev = pd.DataFrame(events, columns=["secs", "component_id", "level", "event_type", "correlation_id", "route_id", "message"])
    ev = ev.sort_values("secs", kind="stable").reset_index(drop=True)
    et_id = dict(zip(ds["dim_event_type"].code, ds["dim_event_type"].event_type_id))
    ds["service_event"] = pd.DataFrame({
        "event_id": np.arange(1, len(ev) + 1),
        "ts_utc": secs_to_ts(ev.secs.to_numpy()),
        "component_id": ev.component_id.to_numpy(),
        "level": ev.level.to_numpy(),
        "event_type_id": ev.event_type.map(et_id).to_numpy(),
        "correlation_id": ev.correlation_id.to_numpy(),
        "route_id": ev.route_id.astype("Int64").to_numpy(),
        "message": ev.message.to_numpy(),
    })
    ds["incident_link"] = pd.DataFrame(sorted(set(links)), columns=["incident_id", "correlation_id"])


def _corr(rng: np.random.Generator, n: int) -> np.ndarray:
    """n random correlation ids 'c-xxxxxxxx'."""
    vals = rng.integers(0, 2**32, n, dtype=np.int64)
    return np.array([f"c-{v:08x}" for v in vals])


def _baseline_events(ds: Dataset, rng: np.random.Generator, comp_id: dict) -> list:
    """Background log noise for every component (vectorised)."""
    names = list(COMPONENT_W)
    w = np.array([COMPONENT_W[n] for n in names]); w /= w.sum()
    dow_f = np.array([1.0, 1.0, 1.0, 1.0, 0.95, 0.85, 0.85])
    hour_w = 0.6 + np.array([0.10, 0.05, 0.05, 0.05, 0.10, 0.20, 0.30, 0.50, 1.50, 2.50, 3.50, 4.00, 5.00, 4.50, 3.50,
                             3.50, 4.00, 5.00, 5.50, 4.50, 3.00, 1.80, 0.80, 0.40]) / 2
    hour_w /= hour_w.sum()
    per_day = TARGET_EVENTS_BASELINE / N_DAYS
    days = np.arange(N_DAYS)
    dows = np.array([(T0 + timedelta(days=int(d))).weekday() for d in days])
    counts = rng.poisson(per_day * dow_f[dows] / dow_f[dows].mean())
    n = int(counts.sum())
    day = np.repeat(days, counts)
    secs = day * 86400 + rng.choice(24, size=n, p=hour_w) * 3600 + rng.integers(0, 3600, n)
    comp = rng.choice(names, size=n, p=w)
    level = np.empty(n, dtype=object)
    for cname in names:
        m = comp == cname
        level[m] = rng.choice(LEVELS, size=m.sum(), p=LEVEL_MIX.get(cname, LEVEL_MIX["default"]))
    etype = np.empty(n, dtype=object)
    for lv, (types, p) in TYPES_BY_LEVEL.items():
        m = level == lv
        etype[m] = rng.choice(types, size=m.sum(), p=np.array(p) / sum(p))
    routes = ds["route"]
    route_p = np.array([{1: 0.85, 2: 0.12, 3: 0.03}[pr] for pr in routes.priority]); route_p /= route_p.sum()
    route = np.full(n, -1, dtype=np.int64)
    m = np.isin(comp, list(ROUTE_COMPONENTS)) & (rng.random(n) < 0.7)
    route[m] = rng.choice(routes.route_id.to_numpy(), size=m.sum(), p=route_p)
    corr = _corr(rng, n)
    r1 = rng.integers(1, 100, n); r2 = rng.integers(100, 3000, n); r3 = rng.integers(1, 4, n)
    msgs = _messages(etype, r1, r2, r3, rng)
    cid = np.vectorize(comp_id.get)(comp)
    return list(zip(secs.tolist(), cid.tolist(), level.tolist(), etype.tolist(), corr.tolist(),
                    [None if r < 0 else int(r) for r in route], msgs))


def _messages(etype: np.ndarray, r1, r2, r3, rng) -> list[str]:
    out = []
    exc = rng.choice(EXCEPTIONS, size=len(etype))
    jobs = rng.choice(BATCH_JOBS, size=len(etype))
    for i, t in enumerate(etype):
        a, b, c = int(r1[i]), int(r2[i]), int(r3[i])
        if t == "HEALTHCHECK": out.append(f"health ok rtt={a}ms")
        elif t == "REQUEST_OK": out.append(f"request completed in {b // 3}ms")
        elif t == "CONFIG_RELOAD": out.append(f"config reloaded ({a % 12 + 1} keys)")
        elif t == "CACHE_REFRESH": out.append(f"cache refreshed entries={b * 7}")
        elif t == "BATCH_DONE": out.append(f"batch {jobs[i]} done rows={b * 41}")
        elif t == "LATENCY_HIGH": out.append(f"latency p99={1500 + b}ms threshold=1500ms")
        elif t == "RETRY": out.append(f"retry {c}/3 after {b}ms")
        elif t == "RATE_LIMIT": out.append(f"rate limit {(a % 5 + 2) * 100} rps exceeded")
        elif t == "CACHE_MISS_STORM": out.append(f"cache miss ratio {40 + a % 50}%")
        elif t == "GC_PAUSE": out.append(f"gc pause {400 + b}ms")
        elif t == "CERT_EXPIRING": out.append(f"certificate expires in {a % 30 + 1} days")
        elif t == "UPSTREAM_TIMEOUT": out.append(f"upstream timeout after {(c + 1) * 2500}ms")
        elif t == "POOL_EXHAUSTED": out.append(f"connection pool exhausted ({64}/{64} in use)")
        elif t == "DB_SLOW_QUERY": out.append(f"query exceeded budget: {b * 3}ms")
        elif t == "AUTH_FAILED": out.append("client authentication failed")
        elif t == "CIRCUIT_OPEN": out.append("circuit breaker open")
        elif t == "UNHANDLED_EXCEPTION": out.append(f"unhandled exception: {exc[i]}")
        elif t == "PROCESS_CRASH": out.append(f"process exited with code {137 if c == 1 else 1}")
        elif t == "OOM_KILL": out.append("container killed: out of memory")
        else: out.append(t.lower().replace("_", " "))
    return out


def _fx_cache_events(ds: Dataset, comp_id: dict) -> list:
    """Hourly fx-service cache refreshes; missing during the stale-cache window (replaced by RATE_AGE_HIGH warnings)."""
    out = []
    cid = comp_id[FX_STORY["component"]]
    stale_from, stale_to = sec(parse_ts(FX_STORY["stale_from"])), sec(parse_ts(FX_STORY["stale_to"]))
    rng = rng_for("fx_events")
    warn_corr = _corr(rng, 5)
    k = 0
    for s in range(14 * 60, N_DAYS * 86400, 3600):          # every hour at hh:14
        if stale_from <= s < stale_to:
            age = s - stale_from
            if age >= 3600:
                out.append((s, cid, "WARN", "RATE_AGE_HIGH", warn_corr[k % 5], None,
                            f"fx snapshot age={age}s exceeds 3600s"))
                k += 1
        else:
            out.append((s, cid, "INFO", "CACHE_REFRESH", f"c-fx{s:08x}"[:10], None, "rates refreshed age=0s currencies=10"))
    ds.meta["fx_warn_corr"] = list(warn_corr)
    return out


def _marker_events(ds: Dataset, deploys: list, changes: list, comp_id: dict) -> list:
    out = []
    for d in deploys:
        s = sec(d["at"])
        cid = comp_id[d["component"]]
        out.append((s - 90, cid, "INFO", "DEPLOY_START", f"c-dp{d['deployment_id']:06d}", None, f"deploying {d['version']}"))
        out.append((s, cid, "INFO", "DEPLOY_DONE", f"c-dp{d['deployment_id']:06d}", None, f"{d['version']} active"))
        if d["rolled_back"]:
            out.append((sec(d["rolled_back"]), cid, "INFO", "DEPLOY_DONE", f"c-dp{d['deployment_id']:06d}", None,
                        f"rolled back {d['version']}"))
    for c in changes:
        out.append((sec(c["at"]) + 5, comp_id[c["component"]], "INFO", "CONFIG_RELOAD", f"c-cf{c['change_id']:06d}", None,
                    f"config reloaded: {c['key']}={c['new']}"))
    return out


def _story_events(ds: Dataset, rng: np.random.Generator, comp_id: dict, inc_by_tag: dict, links: list) -> list:
    out = []
    routes = ds["route"]
    route_id = dict(zip(routes.code, routes.route_id))
    acq_id = dict(zip(ds["dim_acquirer"].name, ds["dim_acquirer"].acquirer_id))

    # --- Story 1: bad deployment (auth-router, one route)
    inc = inc_by_tag["bad_deploy"]
    cid, gw = comp_id[BAD_DEPLOY["component"]], comp_id["acquirer-gateway"]
    rid = int(route_id[BAD_DEPLOY["route_code"]])
    corr = _corr(rng, 30)
    linked = set(corr[:22])
    out.append((sec(parse_ts(BAD_DEPLOY_NOISE_ERROR_TS)), cid, "ERROR", "DB_SLOW_QUERY", _corr(rng, 1)[0], None,
                "query exceeded budget: 2140ms"))
    s_warn, s_err, s_end = sec(parse_ts(BAD_DEPLOY["warn_from"])), sec(parse_ts(BAD_DEPLOY["first_error_ts"])), sec(parse_ts(BAD_DEPLOY["effect_to"])) + 60
    for s in range(s_warn, s_end, 40):
        out.append((s + int(rng.integers(0, 20)), cid, "WARN", "LATENCY_HIGH", corr[int(rng.integers(30))], rid,
                    f"latency p99={int(rng.integers(2200, 6000))}ms threshold=1500ms"))
    first = True
    for s in range(s_err, s_end, 25):
        c = corr[0] if first else corr[int(rng.integers(30))]
        t = "POOL_EXHAUSTED" if rng.random() < 0.6 else "UPSTREAM_TIMEOUT"
        out.append((s if first else s + int(rng.integers(0, 15)), cid, "ERROR", t, c, rid,
                    "connection pool exhausted (96/96 in use)" if t == "POOL_EXHAUSTED" else f"upstream timeout after {int(rng.integers(2, 5)) * 2500}ms"))
        first = False
    for s in range(s_err + 240, s_end, 120):      # secondary symptoms at the gateway
        out.append((s + int(rng.integers(0, 30)), gw, "ERROR", "UPSTREAM_TIMEOUT", corr[int(rng.integers(30))], rid,
                    "upstream timeout after 8000ms"))
    links += [(inc["incident_id"], c) for c in linked]

    # --- Story 2: stale fx cache -> link the RATE_AGE_HIGH warnings
    inc = inc_by_tag["fx_stale"]
    links += [(inc["incident_id"], c) for c in ds.meta["fx_warn_corr"]]

    # --- Story 3: acquirer outage
    inc = inc_by_tag["outage"]
    mer_routes = routes.loc[routes.acquirer_id == acq_id[OUTAGE["acquirer"]]].sort_values("priority")
    r_ids = mer_routes.route_id.to_numpy()
    r_p = np.array([{1: 0.85, 2: 0.12, 3: 0.03}[p] for p in mer_routes.priority]); r_p /= r_p.sum()
    corr = _corr(rng, 40)
    s0, s1 = sec(parse_ts(OUTAGE["from_ts"])), sec(parse_ts(OUTAGE["to_ts"]))
    for s in range(s0 + 8, s1, 20):
        out.append((s + int(rng.integers(0, 10)), gw, "ERROR", "UPSTREAM_TIMEOUT", corr[int(rng.integers(40))],
                    int(rng.choice(r_ids, p=r_p)), f"upstream timeout after {int(rng.integers(3, 5)) * 2500}ms"))
    for s in range(s0 + 120, s1, 120):
        out.append((s, gw, "WARN", "CIRCUIT_OPEN", corr[int(rng.integers(40))], int(rng.choice(r_ids, p=r_p)),
                    "circuit breaker open"))
    for s in range(s0 + 60, s1, 90):
        out.append((s + int(rng.integers(0, 30)), cid, "WARN", "RETRY", corr[int(rng.integers(40))], int(r_ids[0]),
                    f"retry {int(rng.integers(1, 4))}/3 after {int(rng.integers(5000, 9000))}ms"))
    links += [(inc["incident_id"], c) for c in corr[:30]]

    # --- Story 4: firmware rollout + daily decline-rate warnings from the risk engine
    inc = inc_by_tag["firmware"]
    fleet, risk = comp_id[FIRMWARE["component"]], comp_id["risk-engine"]
    models = ds["dim_terminal_model"]
    fw_models = set(models.loc[models.firmware_family == FIRMWARE["family"], "model_id"])
    terms = ds["dim_terminal"]
    fw_terms = terms.loc[terms.model_id.isin(fw_models)]
    s0 = sec(parse_ts(FIRMWARE["from_ts"]))
    for i, serial in enumerate(fw_terms.serial_no):
        out.append((s0 + int(i * 14400 / max(1, len(fw_terms))) + int(rng.integers(0, 30)), fleet, "INFO", "FIRMWARE_ROLLOUT",
                    f"c-fw{i:06d}", None, f"terminal {serial} firmware 3.7.1 -> 3.7.2"))
    corr = _corr(rng, 15)
    day0 = (parse_ts(FIRMWARE["from_ts"]) - T0).days + 2
    for i, d in enumerate(range(day0, N_DAYS)):
        out.append((d * 86400 + 6 * 3600 + 30 * 60, risk, "WARN", "DECLINE_RATE_HIGH", corr[i % 15], None,
                    f"decline rate {9.5 + rng.random() * 2.5:.1f}% > 9.0% for firmware {FIRMWARE['family']}"))
    links += [(inc["incident_id"], c) for c in corr]
    return out


def _random_incident_events(ds: Dataset, rng: np.random.Generator, comp_id: dict, incidents: list, links: list) -> list:
    out = []
    n_by_sev = {"SEV1": (300, 500), "SEV2": (150, 300), "SEV3": (60, 150), "SEV4": (20, 60)}
    routes = ds["route"]
    for inc in incidents:
        if not inc["tag"].startswith("random_"):
            continue
        idx = int(inc["tag"].split("_")[1])
        n = int(rng.integers(*n_by_sev[inc["severity"]]))
        if idx == Q16_DECOY_IDX:
            n = 260
        lead_min = Q18_LEAD_MIN if idx == Q18_INCIDENT_IDX else int(rng.integers(5, 40))
        s_first = sec(inc["opened"]) - lead_min * 60
        s_end = sec(inc["closed"])
        err_types, warn_types = ROOT_CAUSE_TYPES[inc["root_cause"]]
        k = int(rng.integers(6, 30))
        corr = _corr(rng, k)
        n_linked = max(1, int(round(0.7 * k)))
        cid = comp_id[inc["component"]]
        secs = np.sort(rng.integers(s_first + 1, s_end, n))
        secs[0] = s_first
        lv_p = [0.55, 0.40, 0.05] if inc["severity"] in ("SEV1", "SEV2") else [0.5, 0.5, 0.0]
        for i, s in enumerate(secs):
            lv = "ERROR" if i == 0 else rng.choice(["ERROR", "WARN", "FATAL"], p=lv_p)
            c = corr[0] if i == 0 else corr[int(rng.integers(k))]
            if lv == "ERROR":
                t = err_types[int(rng.integers(len(err_types)))]
            elif lv == "WARN":
                t = warn_types[int(rng.integers(len(warn_types)))]
            else:
                t = "PROCESS_CRASH"
            rid = int(routes.route_id.iloc[int(rng.integers(len(routes)))]) if inc["component"] in ROUTE_COMPONENTS and rng.random() < 0.7 else None
            out.append((int(s), cid, lv, t, c, rid, _messages(np.array([t]), [int(rng.integers(1, 100))],
                                                                [int(rng.integers(100, 3000))], [int(rng.integers(1, 4))], rng)[0]))
        links += [(inc["incident_id"], c) for c in corr[:n_linked]]
    return out
