#!/usr/bin/env python3
"""Offline, deterministic SQLite benchmark builder. Python standard library only."""
import argparse, datetime as dt, hashlib, json, os, random, secrets, sqlite3, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
    path.chmod(0o600)

def ms(s):
    return int(dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE subsystems(subsystem_id INTEGER PRIMARY KEY, subsystem_code TEXT NOT NULL UNIQUE);
CREATE TABLE services(service_id INTEGER PRIMARY KEY, subsystem_id INTEGER NOT NULL REFERENCES subsystems, service_code TEXT NOT NULL UNIQUE);
CREATE TABLE regions(region_id INTEGER PRIMARY KEY, region_code TEXT NOT NULL UNIQUE);
CREATE TABLE tenant_tiers(tier_id INTEGER PRIMARY KEY, tier_code TEXT NOT NULL UNIQUE);
CREATE TABLE tenants(tenant_id INTEGER PRIMARY KEY, tenant_key TEXT NOT NULL UNIQUE, tier_id INTEGER NOT NULL REFERENCES tenant_tiers);
CREATE TABLE worker_pools(pool_id INTEGER PRIMARY KEY, region_id INTEGER NOT NULL REFERENCES regions, pool_code TEXT NOT NULL UNIQUE);
CREATE TABLE policy_profiles(profile_id INTEGER PRIMARY KEY, profile_code TEXT NOT NULL UNIQUE, deadline_ms INTEGER NOT NULL CHECK(deadline_ms>0), max_attempts INTEGER NOT NULL CHECK(max_attempts>=1));
CREATE TABLE failure_codes(code_id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, is_success INTEGER NOT NULL CHECK(is_success IN (0,1)), description TEXT NOT NULL);
CREATE TABLE releases(release_id INTEGER PRIMARY KEY, service_id INTEGER NOT NULL REFERENCES services, build_code TEXT NOT NULL UNIQUE);
CREATE TABLE change_kinds(kind_id INTEGER PRIMARY KEY, kind_code TEXT NOT NULL UNIQUE);
CREATE TABLE change_events(change_id INTEGER PRIMARY KEY, effective_at_ms INTEGER NOT NULL, kind_id INTEGER NOT NULL REFERENCES change_kinds, service_id INTEGER NOT NULL REFERENCES services, pool_id INTEGER REFERENCES worker_pools, before_json TEXT NOT NULL CHECK(json_valid(before_json)), after_json TEXT NOT NULL CHECK(json_valid(after_json)), change_note TEXT NOT NULL);
CREATE TABLE service_routes(route_id INTEGER PRIMARY KEY, service_id INTEGER NOT NULL REFERENCES services, route_key TEXT NOT NULL UNIQUE);
CREATE TABLE route_assignments(assignment_id INTEGER PRIMARY KEY, route_id INTEGER NOT NULL REFERENCES service_routes, effective_from_ms INTEGER NOT NULL, effective_to_ms INTEGER NOT NULL, pool_id INTEGER NOT NULL REFERENCES worker_pools, profile_id INTEGER NOT NULL REFERENCES policy_profiles, release_id INTEGER NOT NULL REFERENCES releases, CHECK(effective_to_ms>effective_from_ms), UNIQUE(route_id,effective_from_ms));
CREATE TABLE operation_classes(class_id INTEGER PRIMARY KEY, class_code TEXT NOT NULL UNIQUE, description TEXT NOT NULL);
CREATE TABLE logical_operations(operation_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants, route_id INTEGER NOT NULL REFERENCES service_routes, class_id INTEGER NOT NULL REFERENCES operation_classes, opened_at_ms INTEGER NOT NULL);
CREATE TABLE attempt_events(attempt_id INTEGER PRIMARY KEY, operation_id INTEGER NOT NULL REFERENCES logical_operations, attempt_no INTEGER NOT NULL CHECK(attempt_no>=1), started_at_ms INTEGER NOT NULL, completed_at_ms INTEGER NOT NULL, code_id INTEGER NOT NULL REFERENCES failure_codes, queue_ms INTEGER NOT NULL CHECK(queue_ms>=0), execution_ms INTEGER NOT NULL CHECK(execution_ms>=0), CHECK(completed_at_ms-started_at_ms=queue_ms+execution_ms), UNIQUE(operation_id,attempt_no));
CREATE TABLE telemetry_signals(signal_id INTEGER PRIMARY KEY, signal_code TEXT NOT NULL UNIQUE, unit TEXT NOT NULL, description TEXT NOT NULL);
CREATE TABLE telemetry_samples(sample_id INTEGER PRIMARY KEY, pool_id INTEGER NOT NULL REFERENCES worker_pools, signal_id INTEGER NOT NULL REFERENCES telemetry_signals, measured_at_ms INTEGER NOT NULL, value REAL NOT NULL, UNIQUE(pool_id,signal_id,measured_at_ms));
CREATE TABLE incident_windows(incident_id INTEGER PRIMARY KEY, incident_key TEXT NOT NULL UNIQUE, subsystem_id INTEGER NOT NULL REFERENCES subsystems, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, report_summary TEXT NOT NULL, CHECK(end_ms>start_ms));
CREATE TABLE feed_registry(version INTEGER PRIMARY KEY, event_table TEXT NOT NULL UNIQUE, event_grain TEXT NOT NULL CHECK(event_grain IN ('attempt','operation')), effective_from_ms INTEGER NOT NULL, effective_to_ms INTEGER, lifecycle TEXT NOT NULL CHECK(lifecycle IN ('active','historical')), operation_key_column TEXT NOT NULL, attribution_basis TEXT NOT NULL, CHECK(effective_to_ms IS NULL OR effective_to_ms>effective_from_ms));
CREATE INDEX ops_open ON logical_operations(opened_at_ms,route_id);
CREATE INDEX attempts_operation ON attempt_events(operation_id,attempt_no DESC);
CREATE INDEX assignments_effective ON route_assignments(route_id,effective_from_ms,effective_to_ms);
CREATE INDEX samples_window ON telemetry_samples(measured_at_ms,pool_id,signal_id);
'''
MIGRATION = '''
-- V2 changes instrumentation, not historical measurements. Existing tables survive.
CREATE TABLE execution_cells(cell_id INTEGER PRIMARY KEY, cell_key TEXT NOT NULL UNIQUE, service_id INTEGER NOT NULL REFERENCES services, pool_id INTEGER NOT NULL REFERENCES worker_pools, profile_id INTEGER NOT NULL REFERENCES policy_profiles, release_id INTEGER NOT NULL REFERENCES releases, effective_from_ms INTEGER NOT NULL, effective_to_ms INTEGER, CHECK(effective_to_ms IS NULL OR effective_to_ms>effective_from_ms));
CREATE TABLE outcome_events(outcome_id INTEGER PRIMARY KEY, operation_id INTEGER NOT NULL UNIQUE REFERENCES logical_operations, cell_id INTEGER NOT NULL REFERENCES execution_cells, completed_at_ms INTEGER NOT NULL, final_code_id INTEGER NOT NULL REFERENCES failure_codes, attempt_count INTEGER NOT NULL CHECK(attempt_count>=1), total_queue_ms INTEGER NOT NULL CHECK(total_queue_ms>=0), total_execution_ms INTEGER NOT NULL CHECK(total_execution_ms>=0), total_backoff_ms INTEGER NOT NULL CHECK(total_backoff_ms>=0));
CREATE INDEX outcomes_cell ON outcome_events(cell_id,operation_id);
'''

class Builder:
    def __init__(self, con, rng):
        self.c, self.r = con, rng
        self.oid = self.aid = 0
    def cohort(self, start, route, cls, n, failed, recovered, mode='normal', cell=None, alternate_route=None):
        """Counts are designed; randomized membership, timing and tenants are fixed by seed."""
        assert failed + recovered <= n
        states = ['failed']*failed + ['recovered']*recovered + ['ok']*(n-failed-recovered)
        self.r.shuffle(states)
        for i, state in enumerate(states):
            self.oid += 1
            opened = start + (i*3598000//n)  # First operation is exactly on half-open boundary.
            rid = alternate_route if alternate_route and i % 5 != 0 else route
            self.c.execute('INSERT INTO logical_operations VALUES(?,?,?,?,?)', (self.oid,self.r.randint(1,40),rid,cls,opened))
            count = 3 if state=='failed' else 2 if state=='recovered' else 1
            cursor = opened
            tq = te = 0
            for j in range(1,count+1):
                bad = state=='failed' or j<count
                if bad:
                    deadline = 80 if mode=='tight' else 250
                    q = 235 if mode=='queue' else 5
                    ex = deadline-q
                    code = 2
                else:
                    q = 10 if mode!='queue' else 30
                    ex = 35 if cls==1 else 65
                    code = 1
                tq += q; te += ex
                completed = cursor+q+ex
                if cell is None:
                    self.aid += 1
                    self.c.execute('INSERT INTO attempt_events VALUES(?,?,?,?,?,?,?,?)',(self.aid,self.oid,j,cursor,completed,code,q,ex))
                cursor = completed+20
            if cell is not None:
                self.c.execute('INSERT INTO outcome_events VALUES(?,?,?,?,?,?,?,?,?)',(self.oid,self.oid,cell,completed,code,count,tq,te,20*(count-1)))
    def samples(self, start, pools, kind='normal'):
        for minute in range(0,60,5):
            for pool in pools:
                affected = kind=='queue' and pool==4
                values = {1:118.0,2:180.0 if affected else 4.0,3:4.0 if affected else 16.0,4:0.42}
                for signal,value in values.items():
                    self.c.execute('INSERT INTO telemetry_samples(pool_id,signal_id,measured_at_ms,value) VALUES(?,?,?,?)',(pool,signal,start+minute*60000,value))

def populate(c, rng):
    c.executescript(SCHEMA)
    c.executemany('INSERT INTO subsystems VALUES(?,?)',[(1,'search'),(2,'settlement')])
    c.executemany('INSERT INTO services VALUES(?,?,?)',[(1,1,'parcel-index'),(2,2,'ledger-sync')])
    c.executemany('INSERT INTO regions VALUES(?,?)',[(1,'north'),(2,'south')])
    c.executemany('INSERT INTO tenant_tiers VALUES(?,?)',[(1,'standard'),(2,'priority')])
    c.executemany('INSERT INTO tenants VALUES(?,?,?)',[(i,f'tenant-{i:03}',1+(i%2)) for i in range(1,41)])
    c.executemany('INSERT INTO worker_pools VALUES(?,?,?)',[(1,1,'idx-north'),(2,2,'idx-south'),(3,1,'sync-north'),(4,2,'sync-south')])
    c.executemany('INSERT INTO policy_profiles VALUES(?,?,?,?)',[(1,'balanced-250',250,3),(2,'fast-80',80,3)])
    c.executemany('INSERT INTO failure_codes VALUES(?,?,?,?)',[(1,'OK',1,'Completed successfully'),(2,'DEADLINE',0,'Attempt or operation deadline exhausted')])
    c.executemany('INSERT INTO releases VALUES(?,?,?)',[(1,1,'idx-r18'),(2,1,'idx-r19'),(3,2,'sync-r42')])
    c.executemany('INSERT INTO change_kinds VALUES(?,?)',[(1,'deadline_policy'),(2,'worker_limit'),(3,'release_exposure'),(4,'feed_migration')])
    c.executemany('INSERT INTO operation_classes VALUES(?,?,?)',[(1,'small','Small logical payload'),(2,'large','Large logical payload')])
    routes=[(1,1,'idx-primary-n'),(2,1,'idx-primary-s'),(3,2,'sync-primary-n'),(4,2,'sync-primary-s'),(5,1,'idx-canary-n'),(6,1,'idx-canary-s'),(7,1,'idx-alias-n'),(8,2,'sync-alias-s')]
    c.executemany('INSERT INTO service_routes VALUES(?,?,?)',routes)
    lo,hi=ms('2026-05-01T00:00:00Z'),ms('2026-06-01T00:00:00Z')
    for rid,sid,_ in routes:
        pool={1:1,2:2,3:3,4:4,5:1,6:2,7:1,8:4}[rid]
        rel=2 if rid in (5,6) else 1 if sid==1 else 3
        segments=[(lo,hi,1)]
        if rid in (1,7):
            a,z=ms('2026-05-02T11:00:00Z'),ms('2026-05-02T12:00:00Z')
            segments=[(lo,a,1),(a,z,2),(z,hi,1)]
        for a,z,profile in segments:
            c.execute('INSERT INTO route_assignments(route_id,effective_from_ms,effective_to_ms,pool_id,profile_id,release_id) VALUES(?,?,?,?,?,?)',(rid,a,z,pool,profile,rel))
    c.executemany('INSERT INTO telemetry_signals VALUES(?,?,?,?)',[(1,'upstream_latency_p95','ms','Upstream execution p95; sampled independently of client deadlines'),(2,'queue_depth','operations','Pending operations at the pool'),(3,'available_workers','workers','Observed available worker slots'),(4,'cpu_utilization','fraction','Pool CPU utilization')])
    changes=[('2026-05-02T11:00:00Z',1,1,1,{'deadline_ms':250},{'deadline_ms':80},'Apply latency budget profile'),('2026-05-02T12:00:00Z',1,1,1,{'deadline_ms':80},{'deadline_ms':250},'Restore latency budget profile'),('2026-05-04T00:00:00Z',3,1,None,{'candidate':'inactive'},{'candidate':'idx-r19'},'Enable candidate traffic'),('2026-05-05T00:00:00Z',3,1,None,{'allocation':'initial'},{'allocation':'expanded'},'Increase candidate allocation'),('2026-05-07T11:00:00Z',2,2,4,{'worker_limit':16},{'worker_limit':4},'Apply worker concurrency limit')]
    for time,kind,service,pool,before,after,note in changes:
        c.execute('INSERT INTO change_events(effective_at_ms,kind_id,service_id,pool_id,before_json,after_json,change_note) VALUES(?,?,?,?,?,?,?)',(ms(time),kind,service,pool,json.dumps(before,sort_keys=True),json.dumps(after,sort_keys=True),note))
    c.executemany('INSERT INTO incident_windows VALUES(?,?,?,?,?,?)',[(1,'I-early',1,ms('2026-05-02T11:00:00Z'),ms('2026-05-02T12:00:00Z'),'Search deadline alarm'),(2,'I-later',2,ms('2026-05-07T11:00:00Z'),ms('2026-05-07T12:00:00Z'),'Settlement deadline alarm')])
    c.execute('INSERT INTO feed_registry VALUES(?,?,?,?,?,?,?,?)',(1,'attempt_events','attempt',lo,None,'active','operation_id','Routing decision effective at logical operation open'))
    b=Builder(c,rng)
    for route in (1,2,3,4):
        for cls,failed in ((1,5),(2,20)):
            b.cohort(ms('2026-05-01T10:00:00Z'),route,cls,500,failed,50,alternate_route=7 if route==1 else 8 if route==4 else None)
    for hour in (10,11):
        time=ms(f'2026-05-02T{hour}:00:00Z')
        for route in (1,2):
            for cls in (1,2):
                affected=hour==11 and route==1
                failed=({1:60,2:150} if affected else {1:5,2:20})[cls]
                b.cohort(time,route,cls,500,failed,100 if affected else 50,'tight' if affected else 'normal',alternate_route=7 if route==1 else None)
        b.samples(time,(1,2))
    # Ordinary background traffic, outside the task windows.
    for route in (1,2,3,4):
        for cls,failed in ((1,10),(2,40)):
            b.cohort(ms('2026-05-03T10:00:00Z'),route,cls,1000,failed,100)
    # Matched slices: day x region x class; candidate is worse in all eight.
    trend={4:{1:{1:500,2:1500},2:{1:500,2:500}},5:{1:{1:250,2:250},2:{1:2250,2:500}}}
    for day,release_map in trend.items():
        time=ms(f'2026-05-0{day}T00:00:00Z')
        for release,classes in release_map.items():
            for region in (1,2):
                route=region if release==1 else region+4
                for cls,n in classes.items():
                    rate={1:{1:2,2:20},2:{1:4,2:24}}[release][cls]
                    b.cohort(time,route,cls,n,n*rate//100,n//10)
        b.samples(time,(1,2))
    for hour in (10,11):
        time=ms(f'2026-05-07T{hour}:00:00Z')
        for route in (3,4):
            for cls in (1,2):
                affected=hour==11 and route==4
                failed=({1:50,2:125} if affected else {1:5,2:20})[cls]
                b.cohort(time,route,cls,500,failed,100 if affected else 50,'queue' if affected else 'normal',alternate_route=8 if route==4 else None)
        b.samples(time,(3,4),'queue' if hour==11 else 'normal')
    c.execute('PRAGMA user_version=1')
    c.commit()
    return b

def migrate(c,rng):
    cut=ms('2026-05-09T00:00:00Z')
    c.executescript(MIGRATION)
    c.execute("UPDATE feed_registry SET effective_to_ms=?,lifecycle='historical' WHERE version=1",(cut,))
    c.execute('INSERT INTO feed_registry VALUES(?,?,?,?,?,?,?,?)',(2,'outcome_events','operation',cut,None,'active','operation_id','Actual execution cell recorded on the outcome; routing intent is not serving attribution'))
    c.execute('UPDATE route_assignments SET effective_to_ms=? WHERE effective_to_ms>?',(cut,cut))
    c.execute('INSERT INTO change_events(effective_at_ms,kind_id,service_id,pool_id,before_json,after_json,change_note) VALUES(?,?,?,?,?,?,?)',(cut,4,2,None,'{"version": 1}','{"version": 2}','Switch terminal instrumentation to execution outcomes; retain former feed for history'))
    for cid,pool in ((1,3),(2,3),(3,4),(4,4)):
        c.execute('INSERT INTO execution_cells VALUES(?,?,?,?,?,?,?,?)',(cid,f'cell-{cid:02}',2,pool,1,3,cut,None))
    c.execute('INSERT INTO incident_windows VALUES(?,?,?,?,?,?)',(3,'I-current',2,ms('2026-05-09T11:00:00Z'),ms('2026-05-09T12:00:00Z'),'Settlement terminal failure alarm'))
    b=Builder(c,rng)
    b.oid=c.execute('SELECT MAX(operation_id) FROM logical_operations').fetchone()[0]
    b.aid=c.execute('SELECT MAX(attempt_id) FROM attempt_events').fetchone()[0]
    for hour in (10,11):
        time=ms(f'2026-05-09T{hour}:00:00Z')
        for cell,pool,n in ((1,3,500),(2,3,500),(3,4,400),(4,4,600)):
            affected=hour==11 and pool==4
            failed=n*(18 if affected else 3)//100
            recovered=n*(20 if affected else 10)//100
            # Two classes per cell; even terminal failures and recovered counts here.
            for cls in (1,2):
                f=failed//2 if cls==1 else failed-failed//2
                r=recovered//2 if cls==1 else recovered-recovered//2
                b.cohort(time,pool,cls,n//2,f,r,'queue' if affected else 'normal',cell=cell,alternate_route=7-pool)
        b.samples(time,(3,4),'queue' if hour==11 else 'normal')
    c.execute('PRAGMA user_version=2'); c.commit()

AGENT_README = '''# Operations analytics data contract

You receive `current.db` (SQLite), this README and one task. Inspect the database schema, foreign keys and registry yourself. No network or external data is needed. The database is read-only input; use a read-only connection. All observations are synthetic, internally consistent and complete for the requested windows. Do not interpret absent windows as zero traffic. No hidden business definitions depend on an earlier task.

* Times ending `_ms` are integer Unix milliseconds in UTC. Window membership uses the **logical operation open time**, with inclusive lower and exclusive upper bounds. Effective intervals are also half-open; a NULL end means no known end.
* One logical operation is one business request. Retries are attempts, not extra incidents or requests. A terminal failure means the final attempt/outcome has a failure code whose `is_success` is 0; an earlier failed attempt followed by success is not a terminal failure. All included operations are finished and attempt ordinals are complete. An operation with more than one attempt is a retried operation, including ultimately failed operations.
* `feed_registry` is authoritative about event sources, grains, applicable operation-open intervals and serving attribution. The active entry describes current instrumentation; historical entries remain authoritative for their historical intervals. Do not assume the highest version covers all history or that a still-queryable table is current. Historical values are retained without rewriting them into a new meaning.
* Routing identifiers are routing intent, not necessarily unique physical pools. For routing-time instrumentation, select the assignment effective when the operation opens. For execution-time instrumentation, recorded execution attribution is authoritative. Multiple aliases or execution identities may belong to the same physical pool. Never count each identity as an independent pool.
* End-to-end latency is final completion minus operation open, including queueing, execution and retry backoff. Per-attempt queue/execution times exclude backoff. Outcome totals cover all its attempts. Rates use logical-operation denominators unless a task explicitly asks for attempt metrics. Percentages are in percent (0–100); rate differences are percentage points.
* Telemetry is sampled independently. A requested window mean is the ordinary arithmetic mean of samples in that window. An upstream p95 sample is a percentile observation, not an operation-weighted mean. Changes describe applied configuration, not a causal experiment. Tenant tier, operation class, release, region and pool are distinct dimensions.

Return only the JSON requested in the task: `answer`, `evidence_sql` (a list of executable, read-only SQLite SELECT/WITH statements supporting the answer), and `caveats` (a list of short strings). No placeholders, SQL parameters, temporary tables or external files in evidence. State uncertainty; observational association alone does not prove causation.
'''

def build():
    ROOT.chmod(0o700)
    for d in ('private','manifests','snapshots','agent'):
        (ROOT/d).mkdir(exist_ok=True); (ROOT/d).chmod(0o700)
    config=ROOT/'private/generated_config.json'
    if config.exists():
        cfg=json.loads(config.read_text())
        assert hashlib.sha256(bytes.fromhex(cfg['seed_hex'])).hexdigest()==cfg['seed_sha256'], 'seed hash mismatch'
    else:
        seed=secrets.token_bytes(32)
        cfg={'generator_version':1,'seed_hex':seed.hex(),'seed_sha256':hashlib.sha256(seed).hexdigest(),'provenance':'Newly authored local synthetic tasks; not copied from a published benchmark. No network/API calls.','seed_fixed_before_population':True}
        dump(config,cfg)
    assert cfg['generator_version']==1
    rng=random.Random(int(cfg['seed_hex'],16))
    pre,post=ROOT/'snapshots/pre.db',ROOT/'snapshots/post.db'
    for p in (pre,post):
        if p.exists(): p.unlink()
    c=sqlite3.connect(pre); populate(c,rng); c.execute('VACUUM'); c.close()
    shutil.copyfile(pre,post)
    c=sqlite3.connect(post); c.execute('PRAGMA foreign_keys=ON'); migrate(c,rng); c.execute('VACUUM'); c.close()
    for p in (pre,post): p.chmod(0o600)
    (ROOT/'private/migration_v2.sql').write_text(MIGRATION+'\n-- Data and registry migration: see migrate() in generate.py.\n')
    (ROOT/'agent/README.md').write_text(AGENT_README)
    # Import only local private benchmark definitions; never installed dependencies.
    from definitions import make_artifacts
    make_artifacts(ROOT,cfg,digest)
    print(json.dumps({'seed_sha256':cfg['seed_sha256'],'snapshots':{p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in (pre,post)}},indent=2))

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
