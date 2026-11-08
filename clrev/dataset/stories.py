"""Constants of the planted phenomena ("stories").

Everything that the questions rely on is defined here once, so that the
generator, the ground-truth SQL and STORIES.md all agree.  Dates are UTC,
intervals are half-open [from, to).
"""
from __future__ import annotations

# --- Story 1: bad deployment of auth-router -> latency/timeout spike on ONE route -> incident
BAD_DEPLOY = dict(
    component="auth-router",
    version="v4.18.0",
    deployed_at="2025-03-11 14:05:00",
    operator="d.kowalski",
    rolled_back_at="2025-03-11 16:30:00",
    route_code="ALP-PRX-1",              # the only route affected (Alpenbank via Proxima Switch, priority 1)
    effect_from="2025-03-11 14:05:00",
    effect_to="2025-03-11 16:30:00",
    latency_mult=4.0,                    # x latency for non-timeout txns on the route
    timeout_prob=0.22,                   # share of txns on the route ending in 'Z1' processor timeout
    first_error_ts="2025-03-11 14:21:07",  # earliest ERROR event linked to the incident
    warn_from="2025-03-11 14:12:00",
    incident_opened="2025-03-11 14:40:00",
    incident_closed="2025-03-11 16:55:00",
    severity="SEV2",
    root_cause="BAD_DEPLOY",
    hotfix_version="v4.18.1",
    hotfix_at="2025-03-12 10:10:00",
)
# decoy: on-call "restart" deployment after the first errors but before the incident was opened
BAD_DEPLOY_RESTART = dict(version="v4.18.0+restart", deployed_at="2025-03-11 14:33:00", operator="j.mueller")
# prelude: an unrelated-looking config change on the same component earlier that day
BAD_DEPLOY_PRELUDE_CFG = dict(key="pool.max_connections", old="64", new="96",
                              changed_at="2025-03-11 13:10:00", operator="a.nowak", ticket="OPS-1877")
# unlinked baseline ERROR on auth-router shortly before the deployment (noise for "first ERROR that day")
BAD_DEPLOY_NOISE_ERROR_TS = "2025-03-11 13:52:40"

# --- Story 2: fx-service cache TTL misconfiguration -> stale fx rates -> settlement discrepancies
FX_STORY = dict(
    component="fx-service",
    key="rate_cache_ttl_seconds",
    change=dict(old="300", new="604800", changed_at="2025-05-12 09:14:00", operator="m.ferreira", ticket="OPS-2231"),
    decoy=dict(key="log.level", old="INFO", new="DEBUG", changed_at="2025-05-15 16:40:00",
               operator="l.bergstrom", ticket="OPS-2260"),
    revert=dict(old="604800", new="300", changed_at="2025-05-19 11:30:00", operator="m.ferreira", ticket="OPS-2231"),
    stale_from="2025-05-12 09:14:00",     # fx-service serves the rate snapshot of this date ...
    stale_to="2025-05-19 11:30:00",       # ... until the revert
    stale_rate_date="2025-05-12",
    incident_opened="2025-05-19 10:02:00",
    incident_closed="2025-05-19 12:15:00",
    severity="SEV3",
    root_cause="CONFIG_ERROR",
)

# --- Story 3: acquirer outage -> timeouts on all routes of that acquirer
OUTAGE = dict(
    acquirer="Meridian Acquiring",
    component="acquirer-gateway",
    from_ts="2025-09-18 09:10:00",
    to_ts="2025-09-18 13:40:00",
    timeout_prob=0.75,
    timeout_codes={"Z3": 0.60, "91": 0.25, "96": 0.15},   # '96' is a timeout only in dictionary v2
    retry_prob=0.5,
    incident_opened="2025-09-18 09:31:00",
    incident_closed="2025-09-18 13:55:00",
    severity="SEV1",
    root_cause="THIRD_PARTY_OUTAGE",
)

# --- Story 4: terminal firmware family with elevated declines from a date
FIRMWARE = dict(
    family="OSX-3",
    component="terminal-fleet-mgr",
    rollout_cfg=dict(key="fleet.firmware.OSX-3.target_version", old="3.7.1", new="3.7.2",
                     changed_at="2025-08-04 01:30:00", operator="y.tanaka", ticket="FLT-512"),
    from_ts="2025-08-04 02:00:00",
    decline_add=0.045,                   # +4.5 pp decline probability
    extra_codes={"05": 0.5, "57": 0.3, "62": 0.2},
    incident_opened="2025-08-21 09:15:00",
    incident_closed="2025-08-29 17:00:00",
    severity="SEV4",
    root_cause="FIRMWARE_DEFECT",
)

# --- Story 5: weekly seasonality + growth for one merchant group (level 2)
SEASONAL_GROUP = dict(
    group="Helios Grocery",
    growth=0.70,                         # linear +70 % over the year
    dow=[0.85, 0.90, 0.95, 1.00, 1.35, 1.50, 0.55],   # Mon..Sun
    week_bump={"2025-W50": 1.12, "2025-W51": 1.30, "2025-W52": 0.90, "2026-W01": 0.80},
)
BASE_DOW = [0.95, 0.97, 1.00, 1.02, 1.12, 1.10, 0.80]
MONTH_FACTOR = [0.93, 0.90, 0.98, 1.00, 1.02, 1.03, 1.05, 1.00, 0.98, 1.00, 1.03, 1.12]

# --- Story 6: a chain sold mid-year -> its terminals re-assigned to new merchants of another holding
MOVE = dict(
    from_group="Aurora Coffee Chain",          # level 3, under Aurora Hospitality / Aurora Collective
    to_group="Borealis Coffee (ex-Aurora)",    # level 3, under Borealis Cafés & Bakeries / Borealis Retail AG
    move_ts="2025-06-16 00:00:00",
)
RANDOM_MOVE_SHARE = 0.06                        # other terminals that move once during the year

# --- Story 7: one operator whose changes are repeatedly followed by incidents within 60 min
OPERATOR_STORY = dict(operator="r.svensson", n_incidents=4, second_operator="d.kowalski", n_second=2)

# --- Response code dictionary versions
RC_V2_FROM = "2025-07-01 00:00:00"
RC_V3_FROM = "2025-10-01 00:00:00"      # exists only in payops_v2.db
