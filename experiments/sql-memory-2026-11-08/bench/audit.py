#!/usr/bin/env python3
"""Hidden offline audit, with a Python oracle independent of gold SQL joins."""
import collections, hashlib, json, math, os, sqlite3, stat, tempfile
from pathlib import Path
from generate import ms, dump, digest
from stage import stage
ROOT=Path(__file__).resolve().parent
CHECKS=[]

def check(ok,msg):
    if not ok: raise AssertionError(msg)
    CHECKS.append(msg)

def rows(c,table):
    return [dict(r) for r in c.execute('SELECT * FROM '+table)]

def keyed(c,table,key):
    return {r[key]:r for r in rows(c,table)}

def compare(a,b,path=''):
    if isinstance(b,dict):
        check(isinstance(a,dict) and set(a)==set(b),path+' keys')
        for k in b: compare(a[k],b[k],path+'.'+k)
    elif isinstance(b,list):
        check(isinstance(a,list) and len(a)==len(b),path+' length')
        # Rows have explicit categorical keys; sorting full canonical JSON is deterministic.
        def sortkey(x): return json.dumps({k:v for k,v in x.items() if isinstance(v,str)},sort_keys=True) if isinstance(x,dict) else str(x)
        for x,y in zip(sorted(a,key=sortkey),sorted(b,key=sortkey)): compare(x,y,path+'[]')
    elif isinstance(b,(float,int)):
        check(isinstance(a,(float,int)) and math.isclose(a,b,abs_tol=1e-8,rel_tol=1e-10),f'{path}: {a} == {b}')
    else: check(a==b,f'{path}: {a} == {b}')

def oracle(c):
    ops=rows(c,'logical_operations'); attempts=collections.defaultdict(list)
    for a in rows(c,'attempt_events'): attempts[a['operation_id']].append(a)
    routes=keyed(c,'service_routes','route_id'); services=keyed(c,'services','service_id')
    pools=keyed(c,'worker_pools','pool_id'); regions=keyed(c,'regions','region_id')
    profiles=keyed(c,'policy_profiles','profile_id'); releases=keyed(c,'releases','release_id')
    codes=keyed(c,'failure_codes','code_id'); classes=keyed(c,'operation_classes','class_id')
    assignments=collections.defaultdict(list)
    for a in rows(c,'route_assignments'): assignments[a['route_id']].append(a)
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    outcomes=keyed(c,'outcome_events','operation_id') if 'outcome_events' in tables else {}
    cells=keyed(c,'execution_cells','cell_id') if outcomes else {}
    registry=rows(c,'feed_registry'); result=[]
    for o in ops:
        oid=o['operation_id']; at=o['opened_at_ms']; route=routes[o['route_id']]
        regs=[r for r in registry if at>=r['effective_from_ms'] and (r['effective_to_ms'] is None or at<r['effective_to_ms'])]
        assert len(regs)==1
        if oid in attempts:
            assert regs[0]['event_grain']=='attempt' and oid not in outcomes
            aa=sorted(attempts[oid],key=lambda a:a['attempt_no'])
            assert [a['attempt_no'] for a in aa]==list(range(1,len(aa)+1))
            a=[a for a in assignments[o['route_id']] if a['effective_from_ms']<=at<a['effective_to_ms']]
            assert len(a)==1; a=a[0]
            pp=profiles[a['profile_id']];pool=pools[a['pool_id']];service=services[route['service_id']]
            assert releases[a['release_id']]['service_id']==route['service_id']
            assert len(aa)<=pp['max_attempts']
            assert aa[0]['started_at_ms']==at
            for i,event in enumerate(aa):
                assert event['completed_at_ms']-event['started_at_ms']==event['queue_ms']+event['execution_ms']
                assert event['queue_ms']+event['execution_ms']<=pp['deadline_ms']
                if i<len(aa)-1:
                    assert not codes[event['code_id']]['is_success']
                    assert aa[i+1]['started_at_ms']-event['completed_at_ms']==20
            last=aa[-1]
            record={'attempts':len(aa),'failed_attempts':sum(not codes[e['code_id']]['is_success'] for e in aa),'terminal_failed':int(not codes[last['code_id']]['is_success']),'retried':int(len(aa)>1),'latency_ms':last['completed_at_ms']-at,'terminal_queue_ms':last['queue_ms'],'terminal_execution_ms':last['execution_ms'],'profile_code':pp['profile_code'],'deadline_ms':pp['deadline_ms'],'build_code':releases[a['release_id']]['build_code']}
        else:
            assert regs[0]['event_grain']=='operation' and oid in outcomes
            e=outcomes[oid];cell=cells[e['cell_id']];pool=pools[cell['pool_id']];service=services[cell['service_id']]
            assert cell['effective_from_ms']<=at and (cell['effective_to_ms'] is None or at<cell['effective_to_ms'])
            assert e['attempt_count']<=profiles[cell['profile_id']]['max_attempts']
            assert e['completed_at_ms']-at==e['total_queue_ms']+e['total_execution_ms']+e['total_backoff_ms']
            assert e['total_backoff_ms']==20*(e['attempt_count']-1)
            record={'attempts':e['attempt_count'],'terminal_failed':int(not codes[e['final_code_id']]['is_success']),'retried':int(e['attempt_count']>1),'latency_ms':e['completed_at_ms']-at}
        result.append(dict(record,operation_id=oid,opened_at_ms=at,service_code=service['service_code'],pool_code=pool['pool_code'],region_code=regions[pool['region_id']]['region_code'],class_code=classes[o['class_id']]['class_code']))
    check(True,'All operations have exactly one interval-valid canonical event grain, valid retries/latencies and valid attribution')
    return result

def filt(ops,day,hour,end,service=None):
    lo=ms(f'2026-05-{day:02}T{hour:02}:00:00Z');hi=ms(f'2026-05-{day:02}T{end:02}:00:00Z')
    return [o for o in ops if lo<=o['opened_at_ms']<hi and (service is None or o['service_code']==service)]

def grouped(data,keys):
    out=collections.defaultdict(list)
    for o in data: out[tuple(o[k] for k in keys)].append(o)
    return [(dict(zip(keys,k)),v) for k,v in sorted(out.items())]

def basic(data):
    return {'operations':len(data),'terminal_failures':sum(o['terminal_failed'] for o in data),'terminal_failure_pct':100*sum(o['terminal_failed'] for o in data)/len(data)}

def tag(data,day,hour):
    cut=ms(f'2026-05-{day:02}T{hour:02}:00:00Z')
    return [dict(o,period='reference' if o['opened_at_ms']<cut else 'incident') for o in data]

def py_telemetry(c,day,pools):
    ps=keyed(c,'worker_pools','pool_id');ss=keyed(c,'telemetry_signals','signal_id')
    a=[];lo=ms(f'2026-05-{day:02}T10:00:00Z');cut=lo+3600000
    for r in rows(c,'telemetry_samples'):
        if lo<=r['measured_at_ms']<lo+7200000 and ps[r['pool_id']]['pool_code'] in pools:
            a.append({'period':'reference' if r['measured_at_ms']<cut else 'incident','pool_code':ps[r['pool_id']]['pool_code'],'signal_code':ss[r['signal_id']]['signal_code'],'unit':ss[r['signal_id']]['unit'],'value':r['value']})
    return [dict(k,mean_value=sum(x['value'] for x in v)/len(v)) for k,v in grouped(a,['period','pool_code','signal_code','unit'])]

def py_changes(c,day,service):
    ss=keyed(c,'services','service_id');ks=keyed(c,'change_kinds','kind_id');ps=keyed(c,'worker_pools','pool_id')
    lo=ms(f'2026-05-{day:02}T10:00:00Z')
    return [{'kind_code':ks[x['kind_id']]['kind_code'],'pool_code':ps[x['pool_id']]['pool_code'] if x['pool_id'] else None,'effective_at_ms':x['effective_at_ms'],'before_json':x['before_json'],'after_json':x['after_json']} for x in rows(c,'change_events') if lo<=x['effective_at_ms']<lo+7200000 and ss[x['service_id']]['service_code']==service]

def expected(ops,c,tid):
    if tid=='W1':
        data=filt(ops,1,10,11)
        def counts(x): return {'operations':len(x),**{field:sum(o[src] for o in x) for field,src in [('attempts','attempts'),('failed_attempts','failed_attempts'),('terminal_failures','terminal_failed'),('retried_operations','retried')]}}
        return {'totals':counts(data),'services':[dict(k,**counts(v),terminal_failure_pct=basic(v)['terminal_failure_pct'],physical_pools=len({o['pool_code'] for o in v})) for k,v in grouped(data,['service_code'])]}
    if tid in ('W2','T2'):
        day,service,pools=(2,'parcel-index',['idx-north','idx-south']) if tid=='W2' else (7,'ledger-sync',['sync-north','sync-south'])
        data=tag(filt(ops,day,10,12,service),day,11);out=[]
        for key,v in grouped(data,['period','pool_code']):
            attempts=sum(o['attempts'] for o in v);bad=sum(o['failed_attempts'] for o in v)
            row=dict(key,**basic(v),attempts=attempts,failed_attempts=bad,attempt_failure_pct=100*bad/attempts,retried_operations=sum(o['retried'] for o in v),min_deadline_ms=min(o['deadline_ms'] for o in v),max_deadline_ms=max(o['deadline_ms'] for o in v))
            if tid=='T2':
                vv=[o for o in v if o['terminal_failed']]
                row.update(failed_terminal_queue_mean_ms=sum(o['terminal_queue_ms'] for o in vv)/len(vv),failed_terminal_execution_mean_ms=sum(o['terminal_execution_ms'] for o in vv)/len(vv))
            out.append(row)
        return {'pool_metrics':out,'telemetry':py_telemetry(c,day,pools),'changes':py_changes(c,day,service)}
    if tid=='T1':
        data=[dict(o,period=period) for day,period in ((4,'early'),(5,'late')) for o in filt(ops,day,0,1,'parcel-index')]
        periods=[dict(k,**basic(v),candidate_traffic_pct=100*sum(o['build_code']=='idx-r19' for o in v)/len(v)) for k,v in grouped(data,['period'])]
        builds=[dict(k,**basic(v)) for k,v in grouped(data,['build_code'])]
        matched=[dict(k,**basic(v)) for k,v in grouped(data,['period','region_code','class_code','build_code'])]
        ref=[r['terminal_failure_pct'] for r in matched if r['build_code']=='idx-r18'];can=[r['terminal_failure_pct'] for r in matched if r['build_code']=='idx-r19']
        std={'reference_failure_pct':sum(ref)/8,'candidate_failure_pct':sum(can)/8,'candidate_minus_reference_pp':sum(b-a for a,b in zip(ref,can))/8,'candidate_worse_slices':sum(b>a for a,b in zip(ref,can)),'matched_slices':8}
        mix=[dict(k,operations=len(v),traffic_pct=100*len(v)/sum(o['period']==k['period'] for o in data),terminal_failure_pct=basic(v)['terminal_failure_pct']) for k,v in grouped(data,['period','class_code'])]
        return {'periods':periods,'builds':builds,'matched_cells':matched,'standardized':std,'workload_mix':mix}
    data=tag(filt(ops,9,10,12,'ledger-sync'),9,11)
    out=[dict(k,**basic(v),retried_operations=sum(o['retried'] for o in v),retry_pct=100*sum(o['retried'] for o in v)/len(v),mean_latency_ms=sum(o['latency_ms'] for o in v)/len(v)) for k,v in grouped(data,['period','pool_code'])]
    increases=[]
    for p in {o['pool_code'] for o in data}:
        before=next(x for x in out if x['pool_code']==p and x['period']=='reference')['terminal_failure_pct'];after=next(x for x in out if x['pool_code']==p and x['period']=='incident')['terminal_failure_pct']
        increases.append(dict(pool_code=p,reference_failure_pct=before,incident_failure_pct=after,increase_pp=after-before))
    source=next(r for r in rows(c,'feed_registry') if r['lifecycle']=='active')
    return {'source':{k:source[k] for k in ('version','event_table','event_grain','effective_from_ms')},'pool_metrics':out,'totals':[dict(k,**basic(v)) for k,v in grouped(data,['period'])],'largest_increase':max(increases,key=lambda r:r['increase_pp'])}

def run_readonly(c,sql):
    # Engine-level protection also rejects writes hidden behind WITH, PRAGMA, ATTACH, etc.
    allowed={sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE}
    reads=set()
    def auth(action,arg1,arg2,db,trigger):
        if action==sqlite3.SQLITE_READ: reads.add(arg1)
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    budget=[0]
    def progress():
        budget[0]+=1
        return int(budget[0]>100000)
    c.set_authorizer(auth);c.set_progress_handler(progress,1000)
    try: result=[dict(r) for r in c.execute(sql)]
    finally: c.set_authorizer(None);c.set_progress_handler(None,0)
    check(bool(reads),'Evidence reads actual database tables')
    return result

def main():
    check(stat.S_IMODE(ROOT.stat().st_mode)==0o700,'Benchmark root is chmod 700')
    check(stat.S_IMODE(ROOT.parent.stat().st_mode)==0o700,'Study root is chmod 700')
    config=json.loads((ROOT/'private/generated_config.json').read_text())
    check(hashlib.sha256(bytes.fromhex(config['seed_hex'])).hexdigest()==config['seed_sha256'],'Private precommitted seed hash matches')
    gold=json.loads((ROOT/'gold.json').read_text());manifest=json.loads((ROOT/'manifests/tasks.json').read_text());arms=json.loads((ROOT/'manifests/arms.json').read_text())
    dbs={};py={};sizes={}
    for name in ('pre.db','post.db'):
        path=ROOT/'snapshots'/name;c=sqlite3.connect(f'file:{path}?mode=ro',uri=True);c.row_factory=sqlite3.Row;dbs[name]=c
        check(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok',name+' integrity')
        check(not c.execute('PRAGMA foreign_key_check').fetchall(),name+' foreign keys')
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
        check(15<=len(tables)<=22,name+' table budget')
        counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
        event_count=counts['attempt_events']+counts.get('outcome_events',0)
        check(40000<=event_count<=100000,name+' 40–100k event-row budget')
        check(path.stat().st_size<30*1024*1024,name+' <30 MiB')
        check(digest(path)==arms['snapshots'][name]['sha256'],name+' manifest hash')
        sizes[name]={'bytes':path.stat().st_size,'tables':len(tables),'event_rows':event_count,'row_counts':counts,'sha256':digest(path)}
        py[name]=oracle(c)
    check(rows(dbs['pre.db'],'attempt_events')==rows(dbs['post.db'],'attempt_events'),'Migration preserves every old attempt byte-for-value')
    pre_ops=rows(dbs['pre.db'],'logical_operations');post_ops=rows(dbs['post.db'],'logical_operations')
    check(pre_ops==post_ops[:len(pre_ops)],'Migration preserves all historical logical operations')
    check(not filt(py['pre.db'],9,10,12),'Pre snapshot cannot answer T3 (not a substituted baseline)')
    check(len(filt(py['post.db'],9,10,12))==4000,'Post snapshot contains 4000 current T3 operations')
    check(dbs['post.db'].execute('SELECT COUNT(*) FROM attempt_events a JOIN logical_operations o USING(operation_id) WHERE o.opened_at_ms>=?',(ms('2026-05-09T00:00:00Z'),)).fetchone()[0]==0,'Historical attempt feed has no fabricated new data')
    for task in manifest['tasks']:
        tid=task['id'];snap=task['snapshot'];g=gold[tid]
        expect=expected(py[snap],dbs[snap],tid)
        answer={k:v for k,v in g['answer'].items() if k!='assessment'}
        compare(answer,expect,tid+' independent Python oracle')
        for key,sql in g['evidence_sql'].items():
            result=run_readonly(dbs[snap],sql)
            compare(result[0] if isinstance(answer[key],dict) else result,answer[key],tid+' SQL '+key)
        # Every historical task also remains valid on post, using its historical canonical feed.
        if tid!='T3': compare(expected(py['post.db'],dbs['post.db'],tid),expect,tid+' retained-history equivalence')
        check(not any('\u0400' <= ch <= '\u04ff' for ch in task['instructions']),tid+' instructions English (no Cyrillic)')
    # Independent hand-designed anchors, not generated from the gold query results.
    compare(gold['W1']['answer']['totals'],{'operations':4000,'attempts':4600,'failed_attempts':700,'terminal_failures':100,'retried_operations':500},'W1 design anchor')
    compare(gold['T1']['answer']['standardized'],{'reference_failure_pct':11.0,'candidate_failure_pct':14.0,'candidate_minus_reference_pp':3.0,'candidate_worse_slices':8,'matched_slices':8},'T1 design anchor')
    for tid,pool,rate in [('W2','idx-north',21.0),('T2','sync-south',17.5),('T3','sync-south',18.0)]:
        r=next(x for x in gold[tid]['answer']['pool_metrics'] if x['period']=='incident' and x['pool_code']==pool)
        check(r['terminal_failure_pct']==rate,tid+' incident design anchor')
    with tempfile.TemporaryDirectory(prefix='sql-bench-isolation-') as tmp:
        for task in manifest['tasks']:
            tid=task['id'];all_hashes=[]
            for arm in arms['arms']:
                dest=Path(tmp)/tid/arm;stage(tid,arm,dest)
                check({p.name for p in dest.iterdir()}=={'current.db','README.md','TASK.json'},tid+' '+arm+' exact exposure allowlist')
                all_hashes.append({p.name:digest(p) for p in dest.iterdir()})
                public=(dest/'TASK.json').read_text()+(dest/'README.md').read_text()
                check(config['seed_hex'] not in public and 'gold.json' not in public and str(ROOT) not in public,tid+' '+arm+' no private leakage')
                fresh=sqlite3.connect(f'file:{dest/"current.db"}?mode=ro',uri=True);fresh.row_factory=sqlite3.Row
                # A brand-new isolated task context needs only these three public files.
                for key,sql in gold[tid]['evidence_sql'].items():
                    result=run_readonly(fresh,sql);want=gold[tid]['answer'][key]
                    compare(result[0] if isinstance(want,dict) else result,want,tid+' '+arm+' fresh staged evidence')
                fresh.close()
            check(all(x==all_hashes[0] for x in all_hashes),tid+' all three arms have byte-identical db/README/task')
    # Attribution trap is real: 80% of v2 outcomes are executed outside intended pool.
    post=dbs['post.db']
    mismatch=post.execute('SELECT COUNT(*) FROM outcome_events e JOIN logical_operations o USING(operation_id) JOIN execution_cells c USING(cell_id) WHERE o.route_id != c.pool_id').fetchone()[0]
    check(mismatch==3200,'T3 actual attribution differs from routing intent for 3200/4000 operations')
    # Only source tables/operational metadata; no task/gold material in snapshots.
    check(all('gold' not in t and 'answer' not in t and 'task' not in t for s in sizes.values() for t in s['row_counts']),'No answer/task tables in snapshots')
    for c in dbs.values():c.close()
    report={'status':'PASS','checks_passed':len(CHECKS),'snapshots':sizes,'seed_sha256':config['seed_sha256'],'checks':CHECKS,'scope':'Offline structural/numerical/isolation audit, not an empirical tested-agent solvability trial. No API/model calls.'}
    dump(ROOT/'private/audit_report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))

if __name__=='__main__': main()
