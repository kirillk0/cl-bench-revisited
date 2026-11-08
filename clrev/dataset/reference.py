"""Reference ("dimension") tables of the PayOps dataset.

All keys are surrogate integers.  The hierarchy of merchant groups has three
levels (holding -> division -> chain); merchants may hang off any level.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .common import Dataset, N_DAYS, T0, rng_for, ts
from .stories import MOVE, RANDOM_MOVE_SHARE, RC_V2_FROM, RC_V3_FROM

# ----------------------------------------------------------------------------- static lists
REGIONS = ["Western Europe", "Northern Europe", "Central & Eastern Europe",
           "Middle East", "Asia-Pacific", "North America"]

# iso_code, name, exponent
CURRENCIES = [
    ("EUR", "Euro", 2), ("GBP", "Pound sterling", 2), ("CHF", "Swiss franc", 2),
    ("SEK", "Swedish krona", 2), ("PLN", "Polish zloty", 2), ("CZK", "Czech koruna", 2),
    ("KWD", "Kuwaiti dinar", 3), ("AED", "UAE dirham", 2), ("JPY", "Japanese yen", 0),
    ("USD", "US dollar", 2),
]
# approximate EUR value of one unit on 2025-01-01 and daily volatility of the random walk
FX_START = {"EUR": (1.0, 0.0), "GBP": (1.208, 0.0030), "CHF": (1.063, 0.0025), "SEK": (0.0873, 0.0035),
            "PLN": (0.2340, 0.0030), "CZK": (0.0397, 0.0025), "KWD": (3.125, 0.0030), "AED": (0.2625, 0.0030),
            "JPY": (0.00614, 0.0050), "USD": (0.9640, 0.0030)}

# iso2, name, region, currency
COUNTRIES = [
    ("DE", "Germany", "Western Europe", "EUR"), ("FR", "France", "Western Europe", "EUR"),
    ("NL", "Netherlands", "Western Europe", "EUR"), ("AT", "Austria", "Western Europe", "EUR"),
    ("GB", "United Kingdom", "Western Europe", "GBP"), ("CH", "Switzerland", "Western Europe", "CHF"),
    ("SE", "Sweden", "Northern Europe", "SEK"), ("FI", "Finland", "Northern Europe", "EUR"),
    ("PL", "Poland", "Central & Eastern Europe", "PLN"), ("CZ", "Czechia", "Central & Eastern Europe", "CZK"),
    ("KW", "Kuwait", "Middle East", "KWD"), ("AE", "United Arab Emirates", "Middle East", "AED"),
    ("JP", "Japan", "Asia-Pacific", "JPY"), ("US", "United States", "North America", "USD"),
]

MCC_CATEGORIES = ["Grocery & Food Retail", "Restaurants & Cafés", "Fuel", "Fashion & Apparel",
                  "Home & Electronics", "Health & Pharmacy", "Hotels & Travel", "Jewellery & Luxury",
                  "General Retail"]
# code, description, category, median ticket EUR, lognormal sigma, txn-rate factor, terminals per merchant (lo, hi)
MCCS = [
    ("5411", "Grocery stores, supermarkets", "Grocery & Food Retail", 38.0, 0.75, 1.5, (4, 9)),
    ("5499", "Misc. food stores, convenience", "Grocery & Food Retail", 14.0, 0.70, 1.6, (2, 4)),
    ("5462", "Bakeries", "Restaurants & Cafés", 7.5, 0.55, 1.4, (1, 3)),
    ("5812", "Eating places, restaurants", "Restaurants & Cafés", 31.0, 0.70, 1.0, (2, 4)),
    ("5814", "Fast food restaurants, cafés", "Restaurants & Cafés", 11.0, 0.60, 1.7, (2, 4)),
    ("5541", "Service stations", "Fuel", 58.0, 0.55, 1.2, (3, 6)),
    ("5651", "Family clothing stores", "Fashion & Apparel", 72.0, 0.80, 0.8, (2, 5)),
    ("5661", "Shoe stores", "Fashion & Apparel", 85.0, 0.70, 0.6, (1, 3)),
    ("5712", "Furniture, home furnishings", "Home & Electronics", 260.0, 0.90, 0.35, (2, 4)),
    ("5719", "Misc. home furnishing", "Home & Electronics", 48.0, 0.80, 0.8, (1, 3)),
    ("5732", "Electronics stores", "Home & Electronics", 240.0, 0.95, 0.5, (2, 5)),
    ("5912", "Drug stores, pharmacies", "Health & Pharmacy", 22.0, 0.70, 1.0, (2, 4)),
    ("7011", "Lodging - hotels, motels, resorts", "Hotels & Travel", 210.0, 0.80, 0.5, (4, 10)),
    ("5944", "Jewelry, watches, clocks", "Jewellery & Luxury", 900.0, 1.00, 0.3, (1, 3)),
    ("5999", "Misc. specialty retail", "General Retail", 45.0, 0.85, 0.7, (1, 4)),
    ("5311", "Department stores", "General Retail", 65.0, 0.85, 1.1, (6, 14)),
]

# Holding (level 1) -> divisions (level 2) -> chains (level 3, with number of merchants).
# Each holding has a home country and a list of other countries where it operates.
HOLDINGS = [
    ("Nordlicht Holding", ["SE", "FI", "DE"], [
        ("Nordlicht Fashion", [("Nordlicht Fashion Nordics", 7, "5651"), ("Nordlicht Fashion DACH", 6, "5651"),
                               ("Nordlicht Outlet", 4, "5651")]),
        ("Nordlicht Home & Living", [("Nordlicht Home Stores", 6, "5712"), ("Nordlicht Kitchen", 4, "5719")]),
    ]),
    ("Helios Group", ["DE", "AT", "NL"], [
        ("Helios Grocery", [("Helios Grocery North", 14, "5411"), ("Helios Grocery South", 12, "5411"),
                            ("Helios Express", 16, "5499"), ("Helios Fresh Markets", 8, "5411")]),
        ("Helios Pharma", [("Helios Apotheken", 10, "5912"), ("Helios Health Online", 3, "5912")]),
    ]),
    ("Aurora Collective", ["FR", "NL", "GB", "US"], [
        ("Aurora Hospitality", [("Aurora Hotels", 9, "7011"), ("Aurora Coffee Chain", 14, "5814"),
                                ("Aurora Bistros", 10, "5812")]),
        ("Aurora Fuel & Convenience", [("Aurora Fuel Stations", 12, "5541"), ("Aurora Convenience", 8, "5499")]),
    ]),
    ("Borealis Retail AG", ["CH", "DE", "AT"], [
        ("Borealis Cafés & Bakeries", [("Borealis Cafés", 11, "5814"), ("Borealis Bakeries", 7, "5462"),
                                       ("Borealis Coffee (ex-Aurora)", 0, "5814")]),   # merchants created by the move
        ("Borealis Electronics", [("Borealis Electronics Stores", 9, "5732"), ("Borealis Online", 2, "5732")]),
    ]),
    ("Sakura Trading K.K.", ["JP"], [
        ("Sakura Dining", [("Sakura Ramen", 9, "5812"), ("Sakura Izakaya", 6, "5812")]),
        ("Sakura Convenience", [("Sakura Konbini", 15, "5499")]),
    ]),
    ("Al-Rashid Trading Co.", ["KW", "AE"], [
        ("Al-Rashid Jewellery", [("Al-Rashid Gold Souk", 5, "5944"), ("Al-Rashid Watches", 3, "5944")]),
        ("Al-Rashid Supermarkets", [("Al-Rashid Hyper", 7, "5411"), ("Al-Rashid Mini", 9, "5499")]),
    ]),
    ("Vistula Retail Partners", ["PL", "CZ"], [
        ("Vistula Fashion", [("Vistula Moda", 8, "5651"), ("Vistula Shoes", 5, "5661")]),
        ("Vistula Food", [("Vistula Delikatesy", 10, "5411"), ("Vistula Bistro", 7, "5812")]),
    ]),
]
# merchants attached directly to a level-1 / level-2 group (flagship stores) use these MCCs
HOLDING_DIRECT_MCC = "5311"
DIVISION_DIRECT_MCC = "5999"

ACQUIRERS = [  # name, bic, country, default for countries
    ("Meridian Acquiring", "MERIFRPP", "FR", ["FR", "NL", "GB", "US"]),
    ("NordPay Merchant Services", "NORDSESS", "SE", ["SE", "FI"]),
    ("Alpenbank Acquiring", "ALPBCHZZ", "CH", ["DE", "AT", "CH"]),
    ("Vistula Payments", "VISTPLPW", "PL", ["PL", "CZ"]),
    ("Gulf Card Services", "GULFKWKW", "KW", ["KW", "AE"]),
    ("Sakura Card Acquiring", "SAKUJPJT", "JP", ["JP"]),
]
PROCESSORS = ["Proxima Switch", "Kestrel Gateway", "Orion Core"]
PROC_ABBR = {"Proxima Switch": "PRX", "Kestrel Gateway": "KST", "Orion Core": "ORN"}
ACQ_ABBR = {"Meridian Acquiring": "MER", "NordPay Merchant Services": "NRD", "Alpenbank Acquiring": "ALP",
            "Vistula Payments": "VST", "Gulf Card Services": "GLF", "Sakura Card Acquiring": "SKR"}
# routes: acquirer -> [(processor, priority)]
ROUTES = {
    "Meridian Acquiring": [("Kestrel Gateway", 1), ("Proxima Switch", 2), ("Orion Core", 3)],
    "NordPay Merchant Services": [("Proxima Switch", 1), ("Kestrel Gateway", 2)],
    "Alpenbank Acquiring": [("Proxima Switch", 1), ("Orion Core", 2), ("Kestrel Gateway", 3)],
    "Vistula Payments": [("Orion Core", 1), ("Proxima Switch", 2)],
    "Gulf Card Services": [("Kestrel Gateway", 1), ("Orion Core", 2)],
    "Sakura Card Acquiring": [("Orion Core", 1), ("Kestrel Gateway", 2)],
}
ROUTE_PRIORITY_P = {1: 0.85, 2: 0.12, 3: 0.03}
# latency median (ms) by processor
PROC_LATENCY = {"Proxima Switch": 380, "Kestrel Gateway": 450, "Orion Core": 520}

# vendor, model, firmware family, connectivity, fleet share
TERMINAL_MODELS = [
    ("Ingenix", "Lane 3000X", "TETRA-9", "ETH", 0.24),
    ("Ingenix", "Move 5000X", "TETRA-9", "4G", 0.14),
    ("Verix", "V240m", "OSX-3", "4G", 0.17),
    ("Verix", "P400", "OSX-3", "ETH", 0.12),
    ("PAXton", "A920", "PayDroid-8", "WIFI", 0.15),
    ("PAXton", "A80", "PayDroid-8", "ETH", 0.07),
    ("Castles", "S1F2", "CTOS-2", "ETH", 0.07),
    ("SoftPOS", "TapToPay v2", "ANDROID-SP", "4G", 0.04),
]

TXN_STATUSES = [("AUTHORIZED", "Authorised, not yet captured"), ("CAPTURED", "Captured / cleared for settlement"),
                ("FAILED", "Authorisation failed (see response_code)"), ("REVERSED", "Approved then reversed"),
                ("REFUNDED", "Captured then refunded")]

# code -> (meaning, is_decline, is_timeout) per scheme version.  v2 and v3 list only the codes that change.
RC_V1 = {
    "00": ("Approved", 0, 0), "10": ("Partial approval", 0, 0),
    "05": ("Do not honour", 1, 0), "14": ("Invalid card number", 1, 0), "51": ("Insufficient funds", 1, 0),
    "54": ("Expired card", 1, 0), "57": ("Transaction not permitted to cardholder", 1, 0),
    "61": ("Exceeds withdrawal amount limit", 1, 0), "62": ("Restricted card", 1, 0),
    "65": ("Exceeds withdrawal frequency limit", 1, 0), "96": ("System malfunction", 1, 0),
    "68": ("Response received too late", 0, 1), "91": ("Issuer or switch inoperative", 0, 1),
    "Z1": ("Processor timeout (no response)", 0, 1), "Z3": ("Acquirer unreachable", 0, 1),
}
RC_V2_CHANGES = {
    "96": ("System malfunction - treated as technical timeout (auto-retry)", 0, 1),
    "68": ("Response received too late - auto-reversed, counted as decline", 1, 0),
    "65": ("Soft decline - strong customer authentication required", 1, 0),   # meaning only
}
RC_V3_CHANGES = {
    "Z1": ("Processor declined - retry budget exhausted", 1, 0),
    "91": ("Issuer unavailable - declined by stand-in processing", 1, 0),
}

TEAMS = ["Payments Core", "Treasury Platform", "Fleet & Devices", "Risk", "Platform SRE", "Data Platform"]
COMPONENTS = [  # name, team, tier
    ("api-edge", "Platform SRE", "edge"), ("auth-router", "Payments Core", "core"),
    ("acquirer-gateway", "Payments Core", "core"), ("tokenization-vault", "Payments Core", "core"),
    ("risk-engine", "Risk", "core"), ("fx-service", "Treasury Platform", "support"),
    ("settlement-engine", "Treasury Platform", "core"), ("ledger", "Treasury Platform", "core"),
    ("terminal-fleet-mgr", "Fleet & Devices", "support"), ("notification-svc", "Platform SRE", "support"),
    ("reporting-etl", "Data Platform", "batch"), ("scheduler", "Platform SRE", "support"),
]
OPERATORS = [  # login, full name, team, role
    ("d.kowalski", "Dariusz Kowalski", "Payments Core", "engineer"),
    ("a.nowak", "Agnieszka Nowak", "Payments Core", "engineer"),
    ("h.alrashid", "Hamad Al-Rashid", "Payments Core", "engineer"),
    ("m.ferreira", "Mariana Ferreira", "Treasury Platform", "engineer"),
    ("l.bergstrom", "Lars Bergström", "Treasury Platform", "lead"),
    ("y.tanaka", "Yui Tanaka", "Fleet & Devices", "engineer"),
    ("e.virtanen", "Eero Virtanen", "Fleet & Devices", "engineer"),
    ("s.okafor", "Sade Okafor", "Risk", "engineer"),
    ("k.novak", "Karel Novák", "Risk", "lead"),
    ("r.svensson", "Rikard Svensson", "Platform SRE", "sre"),
    ("j.mueller", "Jonas Müller", "Platform SRE", "sre"),
    ("p.dubois", "Pauline Dubois", "Data Platform", "engineer"),
]
SEVERITIES = [("SEV1", 1, "Critical - customer-facing outage"), ("SEV2", 2, "Major - degraded service"),
              ("SEV3", 3, "Minor - limited impact"), ("SEV4", 4, "Low - cosmetic / monitoring")]
EVENT_TYPES = [
    ("HEALTHCHECK", "Periodic health probe"), ("REQUEST_OK", "Request processed"),
    ("CONFIG_RELOAD", "Configuration reloaded"), ("CACHE_REFRESH", "Cache refreshed from source"),
    ("BATCH_DONE", "Batch job finished"), ("DEPLOY_START", "Deployment started"), ("DEPLOY_DONE", "Deployment finished"),
    ("FIRMWARE_ROLLOUT", "Terminal firmware update pushed"),
    ("LATENCY_HIGH", "Latency above threshold"), ("RETRY", "Operation retried"), ("RATE_LIMIT", "Rate limit hit"),
    ("CACHE_MISS_STORM", "Burst of cache misses"), ("GC_PAUSE", "Long garbage-collection pause"),
    ("CERT_EXPIRING", "TLS certificate close to expiry"), ("RATE_AGE_HIGH", "FX rate snapshot older than threshold"),
    ("DECLINE_RATE_HIGH", "Decline rate above threshold"),
    ("UPSTREAM_TIMEOUT", "Upstream did not answer in time"), ("POOL_EXHAUSTED", "Connection pool exhausted"),
    ("DB_SLOW_QUERY", "Database query exceeded budget"), ("AUTH_FAILED", "Authentication failure"),
    ("CIRCUIT_OPEN", "Circuit breaker opened"), ("UNHANDLED_EXCEPTION", "Unhandled exception"),
    ("PROCESS_CRASH", "Process crashed"), ("OOM_KILL", "Killed by OOM killer"),
]
ROOT_CAUSES = [("BAD_DEPLOY", "Defect introduced by a deployment"), ("CONFIG_ERROR", "Misconfiguration"),
               ("THIRD_PARTY_OUTAGE", "External provider unavailable"), ("CAPACITY", "Insufficient capacity"),
               ("HARDWARE", "Hardware failure"), ("NETWORK", "Network issue"), ("CERT_EXPIRY", "Expired certificate"),
               ("FIRMWARE_DEFECT", "Defective terminal firmware"), ("UNKNOWN", "Root cause not identified")]


# ----------------------------------------------------------------------------- builders
def build_reference(ds: Dataset) -> None:
    """Populate all dimension tables (except the fact-derived ones) into ``ds``."""
    rng = rng_for("reference")

    ds["dim_region"] = pd.DataFrame({"region_id": range(1, len(REGIONS) + 1), "name": REGIONS})
    region_id = dict(zip(REGIONS, ds["dim_region"].region_id))

    ds["dim_currency"] = pd.DataFrame([(i + 1, c, n, e) for i, (c, n, e) in enumerate(CURRENCIES)],
                                      columns=["currency_id", "iso_code", "name", "exponent"])
    cur_id = dict(zip(ds["dim_currency"].iso_code, ds["dim_currency"].currency_id))

    ds["dim_country"] = pd.DataFrame(
        [(i + 1, iso, n, region_id[r], cur_id[c]) for i, (iso, n, r, c) in enumerate(COUNTRIES)],
        columns=["country_id", "iso2", "name", "region_id", "currency_id"])
    country_id = dict(zip(ds["dim_country"].iso2, ds["dim_country"].country_id))

    _build_fx(ds, rng_for("fx"))

    ds["dim_mcc_category"] = pd.DataFrame({"mcc_category_id": range(1, len(MCC_CATEGORIES) + 1),
                                           "name": MCC_CATEGORIES})
    cat_id = dict(zip(MCC_CATEGORIES, ds["dim_mcc_category"].mcc_category_id))
    ds["dim_mcc"] = pd.DataFrame([(i + 1, code, desc, cat_id[cat]) for i, (code, desc, cat, *_) in enumerate(MCCS)],
                                 columns=["mcc_id", "mcc_code", "description", "mcc_category_id"])
    mcc_id = dict(zip(ds["dim_mcc"].mcc_code, ds["dim_mcc"].mcc_id))
    ds.meta["mcc_params"] = {code: dict(median=m, sigma=s, rate=r, terminals=t) for code, _, _, m, s, r, t in MCCS}

    _build_groups_and_merchants(ds, rng, country_id, mcc_id)

    ds["dim_acquirer"] = pd.DataFrame([(i + 1, n, bic, country_id[c]) for i, (n, bic, c, _) in enumerate(ACQUIRERS)],
                                      columns=["acquirer_id", "name", "bic", "country_id"])
    acq_id = dict(zip(ds["dim_acquirer"].name, ds["dim_acquirer"].acquirer_id))
    ds["dim_processor"] = pd.DataFrame({"processor_id": range(1, len(PROCESSORS) + 1), "name": PROCESSORS})
    proc_id = dict(zip(PROCESSORS, ds["dim_processor"].processor_id))
    routes = []
    for acq, lst in ROUTES.items():
        for proc, prio in lst:
            routes.append((len(routes) + 1, acq_id[acq], proc_id[proc], prio,
                           f"{ACQ_ABBR[acq]}-{PROC_ABBR[proc]}-{prio}", 1))
    ds["route"] = pd.DataFrame(routes, columns=["route_id", "acquirer_id", "processor_id", "priority", "code", "is_active"])

    ds["dim_terminal_model"] = pd.DataFrame(
        [(i + 1, v, m, f, c) for i, (v, m, f, c, _) in enumerate(TERMINAL_MODELS)],
        columns=["model_id", "vendor", "model_name", "firmware_family", "connectivity"])

    _build_terminals(ds, rng_for("terminals"), acq_id)

    ds["txn_status_dict"] = pd.DataFrame([(i + 1, c, d) for i, (c, d) in enumerate(TXN_STATUSES)],
                                         columns=["status_id", "code", "description"])
    ds["response_code_dict"] = _build_rc_dict(include_v3=False)
    ds.meta["response_code_dict_v2db"] = _build_rc_dict(include_v3=True)

    _build_fee_schedule(ds, rng_for("fees"), acq_id)

    ds["dim_team"] = pd.DataFrame({"team_id": range(1, len(TEAMS) + 1), "name": TEAMS})
    team_id = dict(zip(TEAMS, ds["dim_team"].team_id))
    ds["dim_component"] = pd.DataFrame([(i + 1, n, team_id[t], tier) for i, (n, t, tier) in enumerate(COMPONENTS)],
                                       columns=["component_id", "name", "team_id", "tier"])
    ds["dim_severity"] = pd.DataFrame([(i + 1, c, r, d) for i, (c, r, d) in enumerate(SEVERITIES)],
                                      columns=["severity_id", "code", "rank", "description"])
    ds["dim_event_type"] = pd.DataFrame([(i + 1, c, d) for i, (c, d) in enumerate(EVENT_TYPES)],
                                        columns=["event_type_id", "code", "description"])
    ds["dim_root_cause"] = pd.DataFrame([(i + 1, c, d) for i, (c, d) in enumerate(ROOT_CAUSES)],
                                        columns=["root_cause_id", "code", "description"])
    ds["operator"] = pd.DataFrame([(i + 1, l, n, team_id[t], r) for i, (l, n, t, r) in enumerate(OPERATORS)],
                                  columns=["operator_id", "login", "full_name", "team_id", "role"])


def _build_fx(ds: Dataset, rng: np.random.Generator) -> None:
    """Daily EUR rates for every currency, 2025-01-01 .. 2026-01-07 (settlements spill into January)."""
    n_days = N_DAYS + 7
    dates = [(T0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_days)]
    rows = []
    for _, cur in ds["dim_currency"].iterrows():
        start, vol = FX_START[cur.iso_code]
        if vol == 0:
            rates = np.full(n_days, 1.0)
        else:
            steps = rng.normal(0.0, vol, n_days - 1)
            rates = start * np.exp(np.concatenate([[0.0], np.cumsum(steps)]))
        digits = 6 if start >= 0.01 else 8
        for d, r in zip(dates, rates):
            rows.append((len(rows) + 1, d, int(cur.currency_id), round(float(r), digits)))
    ds["fx_rate"] = pd.DataFrame(rows, columns=["fx_rate_id", "rate_date", "currency_id", "rate_to_eur"])


def _build_groups_and_merchants(ds: Dataset, rng: np.random.Generator, country_id: dict, mcc_id: dict) -> None:
    groups, merchants = [], []
    name_cnt: dict[str, int] = {}

    def add_group(name, parent, level):
        groups.append((len(groups) + 1, name, parent, level))
        return len(groups)

    def add_merchant(prefix, gid, mcc, countries, onboarded, status="ACTIVE"):
        name_cnt[prefix] = name_cnt.get(prefix, 0) + 1
        c = countries[0] if rng.random() < 0.7 else countries[rng.integers(len(countries))]
        city = CITY_BY_COUNTRY[c][rng.integers(len(CITY_BY_COUNTRY[c]))]
        merchants.append((len(merchants) + 1, f"{prefix} {city} #{name_cnt[prefix]:02d}", gid, mcc_id[mcc],
                          country_id[c], onboarded, status))
        return len(merchants)

    def rand_onboarded():
        d = datetime(2018, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 6 + 300)))
        return ts(d.replace(hour=int(rng.integers(8, 18)), minute=int(rng.integers(0, 60)), second=0))

    leaf_members: dict[str, list[int]] = {}
    for hname, countries, divisions in HOLDINGS:
        hid = add_group(hname, None, 1)
        add_merchant(hname.split()[0] + " Flagship", hid, HOLDING_DIRECT_MCC, countries, rand_onboarded())
        for dname, chains in divisions:
            did = add_group(dname, hid, 2)
            if rng.random() < 0.7:
                add_merchant(dname + " Store", did, DIVISION_DIRECT_MCC, countries, rand_onboarded())
            for cname, n, mcc in chains:
                cid = add_group(cname, did, 3)
                leaf_members[cname] = []
                for _ in range(n):
                    leaf_members[cname].append(add_merchant(cname, cid, mcc, countries, rand_onboarded()))
    # merchants created by the mid-year acquisition (Story 6)
    to_gid = next(g[0] for g in groups if g[1] == MOVE["to_group"])
    n_moved = len(leaf_members[MOVE["from_group"]])
    new_ids = []
    for _ in range(n_moved):
        new_ids.append(add_merchant(MOVE["to_group"], to_gid, "5814", ["CH", "DE", "AT"], MOVE["move_ts"]))
    ds.meta["move_old_merchants"] = leaf_members[MOVE["from_group"]]
    ds.meta["move_new_merchants"] = new_ids
    for mid in leaf_members[MOVE["from_group"]]:          # the sold chain's legal entities were closed
        merchants[mid - 1] = merchants[mid - 1][:6] + ("CLOSED",)

    ds["dim_merchant_group"] = pd.DataFrame(groups, columns=["group_id", "name", "parent_group_id", "level"])
    ds["dim_merchant_group"]["parent_group_id"] = ds["dim_merchant_group"]["parent_group_id"].astype("Int64")
    ds["dim_merchant"] = pd.DataFrame(merchants, columns=["merchant_id", "name", "group_id", "mcc_id",
                                                          "country_id", "onboarded_at", "status"])


CITY_BY_COUNTRY = {
    "DE": ["Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Leipzig"], "FR": ["Paris", "Lyon", "Marseille", "Lille"],
    "NL": ["Amsterdam", "Rotterdam", "Utrecht"], "AT": ["Wien", "Graz", "Linz"], "GB": ["London", "Manchester", "Leeds"],
    "CH": ["Zürich", "Basel", "Bern", "Genève"], "SE": ["Stockholm", "Göteborg", "Malmö"], "FI": ["Helsinki", "Tampere"],
    "PL": ["Warszawa", "Kraków", "Gdańsk", "Wrocław"], "CZ": ["Praha", "Brno"], "KW": ["Kuwait City", "Hawalli"],
    "AE": ["Dubai", "Abu Dhabi"], "JP": ["Tokyo", "Osaka", "Nagoya", "Fukuoka"], "US": ["New York", "Chicago"],
}


def _build_terminals(ds: Dataset, rng: np.random.Generator, acq_id: dict) -> None:
    """Terminals + effective-dated assignments (including the planted and random moves)."""
    merchants = ds["dim_merchant"]
    mcc_code = dict(zip(ds["dim_mcc"].mcc_id, ds["dim_mcc"].mcc_code))
    iso2 = dict(zip(ds["dim_country"].country_id, ds["dim_country"].iso2))
    default_acq = {c: acq_id[name] for name, _, _, cs in ACQUIRERS for c in cs}
    model_ids = ds["dim_terminal_model"].model_id.to_numpy()
    model_p = np.array([m[4] for m in TERMINAL_MODELS]); model_p /= model_p.sum()
    new_merchants = set(ds.meta["move_new_merchants"])
    old_merchants = ds.meta["move_old_merchants"]

    terminals, assignments = [], []
    merchant_terminals: dict[int, list[int]] = {}
    for _, m in merchants.iterrows():
        if int(m.merchant_id) in new_merchants:
            continue                                  # they receive terminals via the move
        lo, hi = ds.meta["mcc_params"][mcc_code[m.mcc_id]]["terminals"]
        n = int(rng.integers(lo, hi + 1))
        acq = default_acq[iso2[m.country_id]]
        if rng.random() < 0.15:                       # some merchants use the pan-European acquirer
            acq = acq_id["Meridian Acquiring"]
        onboarded = datetime.strptime(m.onboarded_at, "%Y-%m-%d %H:%M:%S")
        for _ in range(n):
            tid = len(terminals) + 1
            installed = onboarded + timedelta(days=int(rng.integers(0, 120)))
            installed = min(installed, datetime(2025, 1, 1)) if installed.year >= 2025 else installed
            if rng.random() < 0.08:                   # some terminals installed during 2025
                installed = T0 + timedelta(days=int(rng.integers(0, 300)))
            installed = installed.replace(hour=0, minute=0, second=0)
            model = int(rng.choice(model_ids, p=model_p))
            terminals.append((tid, f"{TERMINAL_MODELS[model-1][0][:3].upper()}{tid:07d}", model, acq, ts(installed)))
            assignments.append([len(assignments) + 1, tid, int(m.merchant_id), ts(installed), None])
            merchant_terminals.setdefault(int(m.merchant_id), []).append(tid)

    # Story 6: terminals of the sold chain move to the new merchants 1:1 at MOVE['move_ts']
    moved = []
    for old_m, new_m in zip(old_merchants, ds.meta["move_new_merchants"]):
        for tid in merchant_terminals.get(old_m, []):
            a = next(a for a in assignments if a[1] == tid and a[4] is None)
            a[4] = MOVE["move_ts"]
            assignments.append([len(assignments) + 1, tid, new_m, MOVE["move_ts"], None])
            moved.append(tid)
    ds.meta["moved_terminals"] = moved

    # random single moves (other terminals), to other merchants of the same country, not into the story groups
    protected = set(old_merchants) | new_merchants
    by_country: dict[int, list[int]] = {}
    for _, m in merchants.iterrows():
        if int(m.merchant_id) not in protected:
            by_country.setdefault(int(m.country_id), []).append(int(m.merchant_id))
    m_country = dict(zip(merchants.merchant_id, merchants.country_id))
    candidates = [a for a in assignments if a[4] is None and a[2] not in protected and a[1] not in set(moved)]
    n_random = int(RANDOM_MOVE_SHARE * len(terminals))
    chosen = rng.choice(len(candidates), size=n_random, replace=False)
    random_moves = []
    for idx in sorted(chosen):
        a = candidates[idx]
        pool = [x for x in by_country[int(m_country[a[2]])] if x != a[2]]
        if not pool:
            continue
        new_m = int(pool[rng.integers(len(pool))])
        when = T0 + timedelta(days=int(rng.integers(20, N_DAYS - 20)))
        if when <= datetime.strptime(a[3], "%Y-%m-%d %H:%M:%S"):
            continue
        a[4] = ts(when)
        assignments.append([len(assignments) + 1, a[1], new_m, ts(when), None])
        random_moves.append((a[1], a[2], new_m, ts(when)))
    ds.meta["random_moves"] = random_moves

    ds["dim_terminal"] = pd.DataFrame(terminals, columns=["terminal_id", "serial_no", "model_id", "acquirer_id",
                                                          "installed_at"])
    ds["terminal_assignment"] = pd.DataFrame(assignments, columns=["assignment_id", "terminal_id", "merchant_id",
                                                                   "valid_from", "valid_to"])


def _build_rc_dict(include_v3: bool) -> pd.DataFrame:
    rows = []
    v1_to = RC_V2_FROM
    for code, (meaning, dec, to) in RC_V1.items():
        rows.append((len(rows) + 1, code, 1, meaning, dec, to, "2025-01-01 00:00:00", v1_to))
    v2 = {**RC_V1, **RC_V2_CHANGES}
    v2_to = RC_V3_FROM if include_v3 else None
    for code, (meaning, dec, to) in v2.items():
        rows.append((len(rows) + 1, code, 2, meaning, dec, to, RC_V2_FROM, v2_to))
    if include_v3:
        v3 = {**v2, **RC_V3_CHANGES}
        for code, (meaning, dec, to) in v3.items():
            rows.append((len(rows) + 1, code, 3, meaning, dec, to, RC_V3_FROM, None))
    return pd.DataFrame(rows, columns=["rc_id", "code", "scheme_version", "meaning", "is_decline", "is_timeout",
                                       "valid_from", "valid_to"])


def _build_fee_schedule(ds: Dataset, rng: np.random.Generator, acq_id: dict) -> None:
    rows = []
    for name, aid in acq_id.items():
        bps = int(rng.integers(95, 160))
        fixed = int(rng.integers(5, 12))
        if rng.random() < 0.5:                      # schedule renegotiated mid-year
            change = T0 + timedelta(days=int(rng.integers(90, 300)))
            rows.append((len(rows) + 1, aid, bps, fixed, "2024-01-01 00:00:00", ts(change)))
            rows.append((len(rows) + 1, aid, bps - int(rng.integers(3, 12)), fixed, ts(change), None))
        else:
            rows.append((len(rows) + 1, aid, bps, fixed, "2024-01-01 00:00:00", None))
    ds["fee_schedule"] = pd.DataFrame(rows, columns=["fee_schedule_id", "acquirer_id", "pct_bps", "fixed_minor",
                                                     "valid_from", "valid_to"])
