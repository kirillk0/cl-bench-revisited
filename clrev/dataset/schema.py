"""DDL of payops.db (v1), the v1 -> v2 migration script, and the SQLite writer."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from .common import Dataset
from .stories import RC_V3_FROM

DDL_V1 = """
CREATE TABLE dim_region (
  region_id   INTEGER PRIMARY KEY,
  name        TEXT NOT NULL
);
CREATE TABLE dim_currency (
  currency_id INTEGER PRIMARY KEY,
  iso_code    TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  exponent    INTEGER NOT NULL            -- number of minor-unit digits (EUR=2, JPY=0, KWD=3)
);
CREATE TABLE dim_country (
  country_id  INTEGER PRIMARY KEY,
  iso2        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  region_id   INTEGER NOT NULL REFERENCES dim_region(region_id),
  currency_id INTEGER NOT NULL REFERENCES dim_currency(currency_id)
);
CREATE TABLE fx_rate (
  fx_rate_id  INTEGER PRIMARY KEY,
  rate_date   TEXT NOT NULL,              -- YYYY-MM-DD
  currency_id INTEGER NOT NULL REFERENCES dim_currency(currency_id),
  rate_to_eur REAL NOT NULL               -- EUR value of 1 unit of the currency on rate_date
);
CREATE UNIQUE INDEX ux_fx_rate_cur_date ON fx_rate(currency_id, rate_date);
CREATE TABLE dim_merchant_group (
  group_id        INTEGER PRIMARY KEY,
  name            TEXT NOT NULL,
  parent_group_id INTEGER REFERENCES dim_merchant_group(group_id),   -- NULL = top level
  level           INTEGER NOT NULL        -- 1 = holding, 2 = division, 3 = chain
);
CREATE TABLE dim_mcc_category (
  mcc_category_id INTEGER PRIMARY KEY,
  name            TEXT NOT NULL
);
CREATE TABLE dim_mcc (
  mcc_id          INTEGER PRIMARY KEY,
  mcc_code        TEXT NOT NULL UNIQUE,
  description     TEXT NOT NULL,
  mcc_category_id INTEGER NOT NULL REFERENCES dim_mcc_category(mcc_category_id)
);
CREATE TABLE dim_merchant (
  merchant_id  INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  group_id     INTEGER NOT NULL REFERENCES dim_merchant_group(group_id),
  mcc_id       INTEGER NOT NULL REFERENCES dim_mcc(mcc_id),
  country_id   INTEGER NOT NULL REFERENCES dim_country(country_id),
  onboarded_at TEXT NOT NULL,
  status       TEXT NOT NULL
);
CREATE INDEX ix_dim_merchant_group ON dim_merchant(group_id);
CREATE TABLE dim_acquirer (
  acquirer_id INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  bic         TEXT,
  country_id  INTEGER REFERENCES dim_country(country_id)
);
CREATE TABLE dim_processor (
  processor_id INTEGER PRIMARY KEY,
  name         TEXT NOT NULL
);
CREATE TABLE route (
  route_id     INTEGER PRIMARY KEY,
  acquirer_id  INTEGER NOT NULL REFERENCES dim_acquirer(acquirer_id),
  processor_id INTEGER NOT NULL REFERENCES dim_processor(processor_id),
  priority     INTEGER NOT NULL,          -- 1 = primary route of the acquirer
  code         TEXT NOT NULL UNIQUE,
  is_active    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE dim_terminal_model (
  model_id        INTEGER PRIMARY KEY,
  vendor          TEXT NOT NULL,
  model_name      TEXT NOT NULL,
  firmware_family TEXT NOT NULL,
  connectivity    TEXT
);
CREATE TABLE dim_terminal (
  terminal_id  INTEGER PRIMARY KEY,
  serial_no    TEXT NOT NULL UNIQUE,
  model_id     INTEGER NOT NULL REFERENCES dim_terminal_model(model_id),
  acquirer_id  INTEGER NOT NULL REFERENCES dim_acquirer(acquirer_id),
  installed_at TEXT NOT NULL
);
CREATE INDEX ix_dim_terminal_model ON dim_terminal(model_id);
CREATE TABLE terminal_assignment (
  assignment_id INTEGER PRIMARY KEY,
  terminal_id   INTEGER NOT NULL REFERENCES dim_terminal(terminal_id),
  merchant_id   INTEGER NOT NULL REFERENCES dim_merchant(merchant_id),
  valid_from    TEXT NOT NULL,            -- inclusive, UTC
  valid_to      TEXT                      -- exclusive, UTC; NULL = still assigned
);
CREATE INDEX ix_terminal_assignment_terminal ON terminal_assignment(terminal_id, valid_from);
CREATE INDEX ix_terminal_assignment_merchant ON terminal_assignment(merchant_id);
CREATE TABLE response_code_dict (
  rc_id          INTEGER PRIMARY KEY,
  code           TEXT NOT NULL,
  scheme_version INTEGER NOT NULL,
  meaning        TEXT NOT NULL,
  is_decline     INTEGER NOT NULL,
  is_timeout     INTEGER NOT NULL,
  valid_from     TEXT NOT NULL,           -- inclusive, UTC
  valid_to       TEXT                     -- exclusive, UTC; NULL = current version
);
CREATE UNIQUE INDEX ux_response_code_dict ON response_code_dict(code, scheme_version);
CREATE TABLE txn_status_dict (
  status_id   INTEGER PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL
);
CREATE TABLE fee_schedule (
  fee_schedule_id INTEGER PRIMARY KEY,
  acquirer_id     INTEGER NOT NULL REFERENCES dim_acquirer(acquirer_id),
  pct_bps         INTEGER NOT NULL,       -- basis points of the settled EUR amount
  fixed_minor     INTEGER NOT NULL,       -- EUR cents per transaction
  valid_from      TEXT NOT NULL,
  valid_to        TEXT
);
CREATE TABLE dim_team (
  team_id INTEGER PRIMARY KEY,
  name    TEXT NOT NULL
);
CREATE TABLE dim_component (
  component_id INTEGER PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  team_id      INTEGER NOT NULL REFERENCES dim_team(team_id),
  tier         TEXT
);
CREATE TABLE dim_severity (
  severity_id INTEGER PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,
  rank        INTEGER NOT NULL,
  description TEXT
);
CREATE TABLE dim_event_type (
  event_type_id INTEGER PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,
  description   TEXT
);
CREATE TABLE dim_root_cause (
  root_cause_id INTEGER PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,
  description   TEXT
);
CREATE TABLE operator (
  operator_id INTEGER PRIMARY KEY,
  login       TEXT NOT NULL UNIQUE,
  full_name   TEXT NOT NULL,
  team_id     INTEGER NOT NULL REFERENCES dim_team(team_id),
  role        TEXT
);
CREATE TABLE txn (
  txn_id        INTEGER PRIMARY KEY,
  ts_utc        TEXT NOT NULL,            -- 'YYYY-MM-DD HH:MM:SS', UTC
  terminal_id   INTEGER NOT NULL REFERENCES dim_terminal(terminal_id),
  amount_minor  INTEGER NOT NULL,         -- minor units of currency_id (see dim_currency.exponent)
  currency_id   INTEGER NOT NULL REFERENCES dim_currency(currency_id),
  status_id     INTEGER NOT NULL REFERENCES txn_status_dict(status_id),
  response_code TEXT NOT NULL,            -- see response_code_dict (versioned)
  route_id      INTEGER NOT NULL REFERENCES route(route_id),
  latency_ms    INTEGER NOT NULL,
  card_scheme   TEXT NOT NULL
);
CREATE INDEX ix_txn_ts ON txn(ts_utc);
CREATE INDEX ix_txn_terminal ON txn(terminal_id);
CREATE INDEX ix_txn_route ON txn(route_id);
CREATE TABLE settlement (
  settlement_id     INTEGER PRIMARY KEY,
  txn_id            INTEGER NOT NULL UNIQUE REFERENCES txn(txn_id),
  settled_at        TEXT NOT NULL,        -- UTC
  fx_rate_applied   REAL NOT NULL,        -- EUR per unit of the txn currency, as applied by fx-service
  settled_eur_minor INTEGER NOT NULL,     -- settled amount, EUR cents
  fee_minor         INTEGER NOT NULL,     -- acquiring fee, EUR cents
  fee_schedule_id   INTEGER NOT NULL REFERENCES fee_schedule(fee_schedule_id)
);
CREATE INDEX ix_settlement_settled_at ON settlement(settled_at);
CREATE TABLE service_event (
  event_id       INTEGER PRIMARY KEY,
  ts_utc         TEXT NOT NULL,           -- UTC
  component_id   INTEGER NOT NULL REFERENCES dim_component(component_id),
  level          TEXT NOT NULL,           -- INFO / WARN / ERROR / FATAL
  event_type_id  INTEGER NOT NULL REFERENCES dim_event_type(event_type_id),
  correlation_id TEXT NOT NULL,
  route_id       INTEGER REFERENCES route(route_id),
  message        TEXT NOT NULL
);
CREATE INDEX ix_service_event_ts ON service_event(ts_utc);
CREATE INDEX ix_service_event_component_ts ON service_event(component_id, ts_utc);
CREATE INDEX ix_service_event_corr ON service_event(correlation_id);
CREATE TABLE deployment (
  deployment_id  INTEGER PRIMARY KEY,
  component_id   INTEGER NOT NULL REFERENCES dim_component(component_id),
  version        TEXT NOT NULL,
  deployed_at    TEXT NOT NULL,           -- UTC
  operator_id    INTEGER NOT NULL REFERENCES operator(operator_id),
  rolled_back_at TEXT                     -- UTC; NULL = not rolled back
);
CREATE INDEX ix_deployment_component_at ON deployment(component_id, deployed_at);
CREATE TABLE config_change (
  change_id    INTEGER PRIMARY KEY,
  component_id INTEGER NOT NULL REFERENCES dim_component(component_id),
  key          TEXT NOT NULL,
  old_value    TEXT,
  new_value    TEXT,
  changed_at   TEXT NOT NULL,             -- UTC
  operator_id  INTEGER NOT NULL REFERENCES operator(operator_id),
  ticket       TEXT
);
CREATE INDEX ix_config_change_component_at ON config_change(component_id, changed_at);
CREATE TABLE incident (
  incident_id   INTEGER PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,     -- 'INC-2025-NNNN'
  opened_at     TEXT NOT NULL,            -- UTC
  closed_at     TEXT,                     -- UTC
  severity_id   INTEGER NOT NULL REFERENCES dim_severity(severity_id),
  component_id  INTEGER NOT NULL REFERENCES dim_component(component_id),
  root_cause_id INTEGER REFERENCES dim_root_cause(root_cause_id),
  summary       TEXT NOT NULL
);
CREATE TABLE incident_link (
  incident_id    INTEGER NOT NULL REFERENCES incident(incident_id),
  correlation_id TEXT NOT NULL,           -- joins service_event.correlation_id
  PRIMARY KEY (incident_id, correlation_id)
);
"""

TABLE_ORDER = ["dim_region", "dim_currency", "dim_country", "fx_rate", "dim_merchant_group", "dim_mcc_category", "dim_mcc",
               "dim_merchant", "dim_acquirer", "dim_processor", "route", "dim_terminal_model", "dim_terminal",
               "terminal_assignment", "response_code_dict", "txn_status_dict", "fee_schedule", "dim_team", "dim_component",
               "dim_severity", "dim_event_type", "dim_root_cause", "operator", "txn", "settlement", "service_event",
               "deployment", "config_change", "incident", "incident_link"]

# v1 -> v2: clean renames + split of the log table + new dictionary version (see SPEC "Migration")
MIGRATION_V2 = f"""
ALTER TABLE terminal_assignment RENAME TO terminal_merchant_link;
ALTER TABLE terminal_merchant_link RENAME COLUMN assignment_id TO link_id;
ALTER TABLE terminal_merchant_link RENAME COLUMN valid_from TO start_ts;
ALTER TABLE terminal_merchant_link RENAME COLUMN valid_to TO end_ts;
DROP INDEX ix_terminal_assignment_terminal;
DROP INDEX ix_terminal_assignment_merchant;
CREATE INDEX ix_terminal_merchant_link_terminal ON terminal_merchant_link(terminal_id, start_ts);
CREATE INDEX ix_terminal_merchant_link_merchant ON terminal_merchant_link(merchant_id);

ALTER TABLE dim_merchant RENAME COLUMN group_id TO merchant_group_id;
DROP INDEX ix_dim_merchant_group;
CREATE INDEX ix_dim_merchant_merchant_group ON dim_merchant(merchant_group_id);

ALTER TABLE fx_rate RENAME TO fx_rate_daily;
ALTER TABLE fx_rate_daily RENAME COLUMN fx_rate_id TO fx_id;
ALTER TABLE fx_rate_daily RENAME COLUMN rate_to_eur TO eur_per_unit;
DROP INDEX ux_fx_rate_cur_date;
CREATE UNIQUE INDEX ux_fx_rate_daily_cur_date ON fx_rate_daily(currency_id, rate_date);

CREATE TABLE service_event_h1 (
  event_id       INTEGER PRIMARY KEY,
  ts_utc         TEXT NOT NULL,           -- UTC, 2025-01-01 .. 2025-06-30
  component_id   INTEGER NOT NULL REFERENCES dim_component(component_id),
  level          TEXT NOT NULL,           -- INFO / WARN / ERROR / FATAL
  event_type_id  INTEGER NOT NULL REFERENCES dim_event_type(event_type_id),
  correlation_id TEXT NOT NULL,
  route_id       INTEGER REFERENCES route(route_id),
  message        TEXT NOT NULL
);
CREATE TABLE service_event_h2 (
  event_id       INTEGER PRIMARY KEY,
  ts_utc         TEXT NOT NULL,           -- UTC, 2025-07-01 .. 2025-12-31
  component_id   INTEGER NOT NULL REFERENCES dim_component(component_id),
  level          TEXT NOT NULL,           -- INFO / WARN / ERROR / FATAL
  event_type_id  INTEGER NOT NULL REFERENCES dim_event_type(event_type_id),
  correlation_id TEXT NOT NULL,
  route_id       INTEGER REFERENCES route(route_id),
  message        TEXT NOT NULL
);
INSERT INTO service_event_h1 SELECT * FROM service_event WHERE ts_utc < '2025-07-01 00:00:00';
INSERT INTO service_event_h2 SELECT * FROM service_event WHERE ts_utc >= '2025-07-01 00:00:00';
DROP TABLE service_event;
CREATE INDEX ix_service_event_h1_ts ON service_event_h1(ts_utc);
CREATE INDEX ix_service_event_h1_component_ts ON service_event_h1(component_id, ts_utc);
CREATE INDEX ix_service_event_h1_corr ON service_event_h1(correlation_id);
CREATE INDEX ix_service_event_h2_ts ON service_event_h2(ts_utc);
CREATE INDEX ix_service_event_h2_component_ts ON service_event_h2(component_id, ts_utc);
CREATE INDEX ix_service_event_h2_corr ON service_event_h2(correlation_id);

UPDATE response_code_dict SET valid_to = '{RC_V3_FROM}' WHERE scheme_version = 2;
"""


def _clean(df: pd.DataFrame) -> list[tuple]:
    """DataFrame -> list of row tuples with NaN/NA/numpy scalars converted for sqlite3."""
    out = df.astype(object).where(pd.notna(df), None)
    rows = []
    for row in out.itertuples(index=False, name=None):
        rows.append(tuple(int(v) if isinstance(v, (np.integer,)) else float(v) if isinstance(v, np.floating) else v
                          for v in row))
    return rows


def write_v1(ds: Dataset, path: Path) -> None:
    """Create payops.db from the in-memory dataset."""
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA page_size=4096;")
    con.executescript(DDL_V1)
    for name in TABLE_ORDER:
        df = ds[name]
        cols = ", ".join(df.columns)
        ph = ", ".join("?" * len(df.columns))
        rows = _clean(df)
        for i in range(0, len(rows), 20000):
            con.executemany(f"INSERT INTO {name} ({cols}) VALUES ({ph})", rows[i:i + 20000])
        con.commit()
    con.execute("ANALYZE")
    con.commit()
    con.execute("VACUUM")
    con.close()


def migrate_v2(ds: Dataset, src: Path, dst: Path) -> None:
    """Copy payops.db to payops_v2.db and apply the silent schema migration."""
    if dst.exists():
        dst.unlink()
    src_con = sqlite3.connect(src)
    dst_con = sqlite3.connect(dst)
    src_con.backup(dst_con)
    src_con.close()
    dst_con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    dst_con.executescript(MIGRATION_V2)
    v3 = ds.meta["response_code_dict_v2db"]
    v3 = v3[v3.scheme_version == 3]
    dst_con.executemany("INSERT INTO response_code_dict (rc_id, code, scheme_version, meaning, is_decline, is_timeout, "
                        "valid_from, valid_to) VALUES (?,?,?,?,?,?,?,?)", _clean(v3))
    dst_con.commit()
    dst_con.execute("ANALYZE")
    dst_con.commit()
    dst_con.execute("VACUUM")
    dst_con.close()


def dump_schema(path: Path, out: Path) -> None:
    """Write the DDL (tables + indexes) of a database to a .sql file."""
    con = sqlite3.connect(path)
    rows = con.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                       "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name").fetchall()
    con.close()
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"-- schema dump of {path.name} (generated by clrev.dataset.build)\n")
        for _, _, sql in rows:
            f.write(sql.strip() + ";\n")
