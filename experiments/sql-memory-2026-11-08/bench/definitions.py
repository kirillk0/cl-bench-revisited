"""Private task specifications and gold evidence. Never stage this module to agents."""
import json, sqlite3
from generate import ms, dump

V1 = '''WITH attempt_rollup AS (
 SELECT operation_id,COUNT(*) attempts,MAX(attempt_no) last_no,
        SUM(CASE WHEN f.is_success=0 THEN 1 ELSE 0 END) failed_attempts
 FROM attempt_events a JOIN failure_codes f USING(code_id) GROUP BY operation_id
), op AS (
 SELECT o.operation_id,o.opened_at_ms,s.service_code,wp.pool_code,reg.region_code,
        cl.class_code,rel.build_code,pp.profile_code,pp.deadline_ms,
        a.attempts,a.failed_attempts,1-f.is_success terminal_failed,
        CASE WHEN a.attempts>1 THEN 1 ELSE 0 END retried,
        last.completed_at_ms-o.opened_at_ms latency_ms,
        last.queue_ms terminal_queue_ms,last.execution_ms terminal_execution_ms
 FROM logical_operations o
 JOIN attempt_rollup a USING(operation_id)
 JOIN attempt_events last ON last.operation_id=o.operation_id AND last.attempt_no=a.last_no
 JOIN failure_codes f ON f.code_id=last.code_id
 JOIN service_routes rt USING(route_id)
 JOIN services s USING(service_id)
 JOIN route_assignments ra ON ra.route_id=o.route_id
  AND o.opened_at_ms>=ra.effective_from_ms AND o.opened_at_ms<ra.effective_to_ms
 JOIN worker_pools wp USING(pool_id) JOIN regions reg USING(region_id)
 JOIN policy_profiles pp USING(profile_id) JOIN releases rel USING(release_id)
 JOIN operation_classes cl USING(class_id)
)
'''
V2 = '''WITH op AS (
 SELECT o.operation_id,o.opened_at_ms,s.service_code,p.pool_code,
        1-f.is_success terminal_failed,
        CASE WHEN e.attempt_count>1 THEN 1 ELSE 0 END retried,
        e.attempt_count attempts,e.completed_at_ms-o.opened_at_ms latency_ms
 FROM outcome_events e JOIN logical_operations o USING(operation_id)
 JOIN execution_cells c USING(cell_id) JOIN worker_pools p USING(pool_id)
 JOIN services s ON s.service_id=c.service_id
 JOIN failure_codes f ON f.code_id=e.final_code_id
)
'''

def window(day, hour, end):
    return f"opened_at_ms >= {ms(f'2026-05-{day:02}T{hour:02}:00:00Z')} AND opened_at_ms < {ms(f'2026-05-{day:02}T{end:02}:00:00Z')}"

def incident_metrics(day, service, detailed=False):
    extra=''' ,SUM(CASE WHEN terminal_failed=1 THEN terminal_queue_ms ELSE 0 END)*1.0/SUM(terminal_failed) failed_terminal_queue_mean_ms,
 SUM(CASE WHEN terminal_failed=1 THEN terminal_execution_ms ELSE 0 END)*1.0/SUM(terminal_failed) failed_terminal_execution_mean_ms''' if detailed else ''
    return V1+f''', tagged AS (SELECT *,CASE WHEN opened_at_ms < {ms(f'2026-05-{day:02}T11:00:00Z')} THEN 'reference' ELSE 'incident' END period FROM op WHERE {window(day,10,12)} AND service_code='{service}')
 SELECT period,pool_code,COUNT(*) operations,SUM(terminal_failed) terminal_failures,
 100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct,
 SUM(attempts) attempts,SUM(failed_attempts) failed_attempts,
 100.0*SUM(failed_attempts)/SUM(attempts) attempt_failure_pct,
 SUM(retried) retried_operations,MIN(deadline_ms) min_deadline_ms,MAX(deadline_ms) max_deadline_ms
 {extra}
 FROM tagged GROUP BY period,pool_code ORDER BY period,pool_code;'''

def telemetry(day,pools):
    return f'''SELECT CASE WHEN measured_at_ms < {ms(f'2026-05-{day:02}T11:00:00Z')} THEN 'reference' ELSE 'incident' END period,
 p.pool_code,s.signal_code,AVG(t.value) mean_value,s.unit
 FROM telemetry_samples t JOIN worker_pools p USING(pool_id) JOIN telemetry_signals s USING(signal_id)
 WHERE t.measured_at_ms >= {ms(f'2026-05-{day:02}T10:00:00Z')} AND t.measured_at_ms < {ms(f'2026-05-{day:02}T12:00:00Z')}
 AND p.pool_code IN ({','.join(repr(x) for x in pools)})
 GROUP BY period,p.pool_code,s.signal_code,s.unit ORDER BY period,p.pool_code,s.signal_code;'''

def change_sql(day,service):
    return f'''SELECT k.kind_code,p.pool_code,c.effective_at_ms,c.before_json,c.after_json
 FROM change_events c JOIN change_kinds k USING(kind_id) JOIN services s USING(service_id)
 LEFT JOIN worker_pools p USING(pool_id)
 WHERE c.effective_at_ms >= {ms(f'2026-05-{day:02}T10:00:00Z')} AND c.effective_at_ms < {ms(f'2026-05-{day:02}T12:00:00Z')}
 AND s.service_code='{service}' ORDER BY c.effective_at_ms,c.change_id;'''

TREND=V1+f''', trend AS (
 SELECT *,CASE WHEN opened_at_ms < {ms('2026-05-05T00:00:00Z')} THEN 'early' ELSE 'late' END period
 FROM op WHERE service_code='parcel-index' AND (({window(4,0,1)}) OR ({window(5,0,1)}))
)
'''
COMMON = '''Use only the supplied current.db and README. All windows below are UTC and half-open, selected by logical-operation open time. A terminal-failure percentage has logical operations as its denominator; attempt-failure percentage has attempts as its denominator. Return only JSON matching the provided schema. Percentages use 0–100, differences use percentage points. evidence_sql must contain executable read-only SQLite queries with literal bounds, not pseudocode. Arrays may be in any order; include every requested group. A zero numerator is not missing data. No web or network access is needed.'''

SPECS = [
 dict(id='W1',phase='warmup',snapshot='pre.db',title='Orientation and counting calibration',
 question='''For 2026-05-01 10:00–11:00, report total logical operations, attempts, failed attempts, terminal failures, and retried operations across all services. Then report those same five counts for each service, plus its terminal-failure percentage and the number of distinct serving physical pools represented in the window. Explain briefly in caveats why attempts and terminal failures are not interchangeable. This is a counting calibration, not an incident attribution exercise.''',
 queries={
 'totals':(V1+f'''SELECT COUNT(*) operations,SUM(attempts) attempts,SUM(failed_attempts) failed_attempts,SUM(terminal_failed) terminal_failures,SUM(retried) retried_operations FROM op WHERE {window(1,10,11)};''','object'),
 'services':(V1+f'''SELECT service_code,COUNT(*) operations,SUM(attempts) attempts,SUM(failed_attempts) failed_attempts,SUM(terminal_failed) terminal_failures,SUM(retried) retried_operations,100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct,COUNT(DISTINCT pool_code) physical_pools FROM op WHERE {window(1,10,11)} GROUP BY service_code ORDER BY service_code;''','array')},
 rubric=[('grain', 'Distinguishes logical operations, retries and terminal failures; a recovered retry is not a failed operation.')]),
 dict(id='W2',phase='warmup',snapshot='pre.db',title='Early search incident',
 question='''Investigate parcel-index on 2026-05-02, comparing reference 10:00–11:00 with incident 11:00–12:00. For every period and serving physical pool, report operations, terminal failures and their percentage, attempts, failed attempts and their percentage, retried operations, and minimum/maximum applied deadline_ms. Report ordinary window means of every recorded telemetry signal for those pools, and applied changes during 10:00–12:00 (kind, pool, effective time, before/after JSON strings). In assessment, identify the most strongly supported proximal explanation, the affected pool and the terminal-failure increase in percentage points; contrast it with at least one plausible alternative. Distinguish evidence from causal proof. Attribute configuration at the time the operation entered the system, not from today's configuration.''',
 queries={'pool_metrics':(incident_metrics(2,'parcel-index'),'array'),'telemetry':(telemetry(2,['idx-north','idx-south']),'array'),'changes':(change_sql(2,'parcel-index'),'array')},
 assessment='idx-north rises from 2.5% to 21.0% (+18.5 pp), while idx-south stays at 2.5%. The applied deadline falls from 250 to 80 ms; upstream p95 stays 118 ms, queue depth 4, workers 16. A tighter client deadline is the strongest supported proximal explanation, not an observed upstream slowdown. Temporal coincidence plus mechanism is not controlled causal proof.',
 rubric=[('localization','Names idx-north and +18.5 pp; idx-south is unchanged.'),('evidence','Links 250→80 ms applied policy with unchanged 118 ms upstream p95, low queue and stable workers; supports deadline-budget mismatch rather than upstream regression.'),('restraint','Does not claim observational evidence proves a sole cause; distinguishes failed attempts from terminal failures.')]),
 dict(id='T1',phase='test',snapshot='pre.db',title='Rollout trend and matched comparisons',
 question='''Evaluate parcel-index during early 2026-05-04 00:00–01:00 and late 2026-05-05 00:00–01:00. Candidate build is idx-r19 and reference is idx-r18. (1) For each period report operations, terminal failures, failure percentage, and candidate traffic percentage. (2) Pool both periods and report operations, terminal failures and failure percentage per build. (3) Report operations, terminal failures and failure percentage for each period × region × operation-class × build cell. These define eight matched slices (period × region × operation class), each containing both builds. (4) Standardize each build by giving those eight slices equal weight; report both standardized failure percentages, candidate minus reference in pp, and the number of slices where candidate is worse. (5) Report period × operation-class traffic shares and failure percentages. In assessment, explain whether the time trend and pooled build comparison support the claim “expanding the candidate improved reliability.” Identify the strongest measured association and distinguish a possible root-cause hypothesis from causal identification. Do not extrapolate beyond the observed strata. Equal weighting here is the specified target population, not weighting by observed build traffic.''',
 queries={
 'periods':(TREND+'''SELECT period,COUNT(*) operations,SUM(terminal_failed) terminal_failures,100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct,100.0*SUM(build_code='idx-r19')/COUNT(*) candidate_traffic_pct FROM trend GROUP BY period ORDER BY period;''','array'),
 'builds':(TREND+'''SELECT build_code,COUNT(*) operations,SUM(terminal_failed) terminal_failures,100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct FROM trend GROUP BY build_code ORDER BY build_code;''','array'),
 'matched_cells':(TREND+'''SELECT period,region_code,class_code,build_code,COUNT(*) operations,SUM(terminal_failed) terminal_failures,100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct FROM trend GROUP BY period,region_code,class_code,build_code ORDER BY period,region_code,class_code,build_code;''','array'),
 'standardized':(TREND+''', rates AS (SELECT period,region_code,class_code,build_code,100.0*SUM(terminal_failed)/COUNT(*) pct FROM trend GROUP BY period,region_code,class_code,build_code), paired AS (SELECT a.period,a.region_code,a.class_code,a.pct reference_pct,b.pct candidate_pct FROM rates a JOIN rates b USING(period,region_code,class_code) WHERE a.build_code='idx-r18' AND b.build_code='idx-r19') SELECT AVG(reference_pct) reference_failure_pct,AVG(candidate_pct) candidate_failure_pct,AVG(candidate_pct-reference_pct) candidate_minus_reference_pp,SUM(candidate_pct>reference_pct) candidate_worse_slices,COUNT(*) matched_slices FROM paired;''','object'),
 'workload_mix':(TREND+''', cells AS (SELECT period,class_code,COUNT(*) operations,SUM(terminal_failed) terminal_failures FROM trend GROUP BY period,class_code) SELECT period,class_code,operations,100.0*operations/SUM(operations) OVER(PARTITION BY period) traffic_pct,100.0*terminal_failures/operations terminal_failure_pct FROM cells ORDER BY period,class_code;''','array')},
 assessment='Overall failure falls 15%→8.153846%, and the pooled candidate appears better (9.333333% versus 14.6%). But idx-r19 is worse in all eight matched slices: +2 pp for small and +4 pp for large. Equal-slice standardization gives 14% versus 11%, +3 pp. Small-workload share rises from 33.333333% to 76.923077%. The observed trend and pooled comparison are confounded by workload and exposure composition, not evidence that rollout improved reliability. Candidate-associated regression is the strongest measured adverse association conditional on the specified strata; non-random assignment and unmeasured factors prevent identifying the build itself as a proven cause.',
 rubric=[('reversal','Recognizes favorable pooled/time comparisons reverse under matched strata; candidate is worse in 8/8, not safer.'),('composition','Explains the changing small/large mix and unequal build exposure; cites +3 pp standardized difference or +2/+4 pp stratum differences.'),('causality','Treats candidate-associated regression as a hypothesis, not proven root cause; notes observational assignment/unmeasured confounding. No required invented alternative cause.')]),
 dict(id='T2',phase='test',snapshot='pre.db',title='Later settlement incident',
 question='''Investigate ledger-sync on 2026-05-07, reference 10:00–11:00 versus incident 11:00–12:00. For every period and serving physical pool report operations, terminal failures and percentage, attempts, failed attempts and percentage, retried operations, minimum/maximum applied deadline_ms, and mean queue_ms and execution_ms of the terminal attempt among terminally failed operations. Report means of every recorded telemetry signal for those pools and applied changes during 10:00–12:00 (kind, pool, effective time, before/after JSON strings). In assessment identify the strongest supported proximal explanation, the affected pool and failure increase in pp. Explicitly evaluate both a deadline-policy change and worker/queue pressure against the current evidence. Explain the remaining causal limitation.''',
 queries={'pool_metrics':(incident_metrics(7,'ledger-sync',True),'array'),'telemetry':(telemetry(7,['sync-north','sync-south']),'array'),'changes':(change_sql(7,'ledger-sync'),'array')},
 assessment='sync-south rises 2.5%→17.5% (+15 pp); sync-north remains 2.5%. Deadline stays 250 ms. South available workers fall 16→4, queue depth rises 4→180, failed terminal queue time 5→235 ms and execution time 245→15 ms; upstream p95 stays 118 ms. An applied worker-limit reduction with queue starvation is the strongest proximal explanation; there is no observed deadline-policy tightening. This is convergent observational evidence, not an intervention proving exclusivity.',
 rubric=[('localization','Names sync-south +15 pp; sync-north unchanged.'),('mechanism','Uses unchanged 250 ms policy, workers 16→4, queue 4→180 and failed-terminal queue 5→235 ms to favor capacity/queue pressure over deadline tightening or upstream slowdown.'),('restraint','Does not transfer the earlier incident explanation despite matching DEADLINE symptom, and does not claim causal proof.')]),
 dict(id='T3',phase='test',snapshot='post.db',title='Current settlement reliability report',
 question='''Report ledger-sync reliability for 2026-05-09: reference 10:00–11:00 versus incident 11:00–12:00. Report the authoritative event source for these windows (registry version, event table, event grain and effective start). For each period and actual serving PHYSICAL pool, report logical operations, terminal failures, terminal-failure percentage, retried operations, retry percentage and mean end-to-end latency_ms. Do not treat routing intent or an individual execution identity as a physical pool. Also give all-pool operations, terminal failures and terminal-failure percentage per period; identify the physical pool with the largest increase and report that increase in pp. In assessment state what the report establishes and the important attribution/counting limitations.''',
 queries={
 'source':("SELECT version,event_table,event_grain,effective_from_ms FROM feed_registry WHERE effective_from_ms <= "+str(ms('2026-05-09T10:00:00Z'))+" AND (effective_to_ms IS NULL OR effective_to_ms >= "+str(ms('2026-05-09T12:00:00Z'))+") ORDER BY version DESC LIMIT 1;",'object'),
 'pool_metrics':(V2+f''', tagged AS (SELECT *,CASE WHEN opened_at_ms < {ms('2026-05-09T11:00:00Z')} THEN 'reference' ELSE 'incident' END period FROM op WHERE {window(9,10,12)} AND service_code='ledger-sync') SELECT period,pool_code,COUNT(*) operations,SUM(terminal_failed) terminal_failures,100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct,SUM(retried) retried_operations,100.0*SUM(retried)/COUNT(*) retry_pct,AVG(latency_ms) mean_latency_ms FROM tagged GROUP BY period,pool_code ORDER BY period,pool_code;''','array'),
 'totals':(V2+f''', tagged AS (SELECT *,CASE WHEN opened_at_ms < {ms('2026-05-09T11:00:00Z')} THEN 'reference' ELSE 'incident' END period FROM op WHERE {window(9,10,12)} AND service_code='ledger-sync') SELECT period,COUNT(*) operations,SUM(terminal_failed) terminal_failures,100.0*SUM(terminal_failed)/COUNT(*) terminal_failure_pct FROM tagged GROUP BY period ORDER BY period;''','array'),
 'largest_increase':(V2+f''', rates AS (SELECT pool_code,CASE WHEN opened_at_ms < {ms('2026-05-09T11:00:00Z')} THEN 'reference' ELSE 'incident' END period,100.0*SUM(terminal_failed)/COUNT(*) pct FROM op WHERE {window(9,10,12)} AND service_code='ledger-sync' GROUP BY pool_code,period) SELECT a.pool_code,a.pct reference_failure_pct,b.pct incident_failure_pct,b.pct-a.pct increase_pp FROM rates a JOIN rates b USING(pool_code) WHERE a.period='reference' AND b.period='incident' ORDER BY increase_pp DESC,a.pool_code LIMIT 1;''','object')},
 assessment='Registry v2 outcome_events is operation-grain current instrumentation. Aggregate execution cells to actual physical pools, not intended routes, and do not deduplicate by cells. sync-south rises from 3% to 18%, +15 pp; sync-north stays 3%. The old attempt feed is legitimate retained history, not current coverage. Counting outcomes once and using attempt_count for retries produces the report; counts alone do not establish a root cause.',
 rubric=[('source','Uses registry v2 current operation-grain outcomes; old attempt feed is historical, not empty current business activity.'),('attribution','Aggregates actual execution cells to physical pools and does not use stale intended-route assignment as actual service attribution.'),('restraint','Identifies sync-south +15 pp and does not infer a proven root cause from these aggregate metrics.')])
]

def infer_schema(value):
    if isinstance(value,dict):
        return {'type':'object','properties':{k:infer_schema(v) for k,v in value.items()},'required':list(value),'additionalProperties':False}
    if isinstance(value,list):
        return {'type':'array','items':infer_schema(value[0]) if value else {},'minItems':len(value),'maxItems':len(value)}
    if isinstance(value,int): return {'type':'integer'}
    if isinstance(value,float): return {'type':'number'}
    if value is None: return {'type':['null','string']}
    return {'type':'string'}

def make_artifacts(root,cfg,digest):
    tasks=[]; gold={}
    for spec in SPECS:
        con=sqlite3.connect(f"file:{root/'snapshots'/spec['snapshot']}?mode=ro",uri=True);con.row_factory=sqlite3.Row
        answer={}; evidence={}
        for key,(sql,shape) in spec['queries'].items():
            rows=[dict(r) for r in con.execute(sql)]
            assert rows,(spec['id'],key)
            answer[key]=rows[0] if shape=='object' else rows
            evidence[key]=sql
        if 'assessment' in spec: answer['assessment']=spec['assessment']
        schema={'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','additionalProperties':False,'required':['answer','evidence_sql','caveats'],'properties':{'answer':infer_schema(answer),'evidence_sql':{'type':'array','minItems':1,'items':{'type':'string'}},'caveats':{'type':'array','minItems':1,'items':{'type':'string'}}}}
        task={k:spec[k] for k in ('id','phase','title','snapshot')}
        task.update({'instructions':COMMON+'\n\n'+spec['question'],'response_schema':schema,'snapshot_sha256':digest(root/'snapshots'/spec['snapshot']),'order':len(tasks)+1,'independently_answerable':True})
        tasks.append(task)
        gold[spec['id']]={'snapshot':spec['snapshot'],'answer':answer,'evidence_sql':evidence,'numeric_tolerance':{'integer_counts':{'absolute':0,'relative':0},'other_numbers':{'absolute':0.01,'relative':0.00001}},'array_matching':'Unordered; categorical dimensions identify rows. Duplicates or omitted groups are incorrect.','qualitative_rubric':[{'id':k,'criterion':v} for k,v in spec['rubric']],'assessment_policy':'Example assessment is not an exact-match target. Grade factual support and causal restraint, not wording or a preferred opinion.'}
        con.close()
    dump(root/'manifests/tasks.json',{'benchmark_id':'temporal-ops-sql-private-v1','sequence':['W1','W2','T1','T2','T3'],'tasks':tasks})
    dump(root/'gold.json',gold)
    snapshots={p.name:{'path':str(p.relative_to(root)),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted((root/'snapshots').glob('*.db'))}
    arms={arm:{'task_sequence':['W1','W2','T1','T2','T3'],'task_bindings':{t['id']:{'snapshot':t['snapshot'],'sha256':t['snapshot_sha256']} for t in tasks},'instructions_identical':True} for arm in ('no_memory','raw_history','distilled_memory')}
    dump(root/'manifests/arms.json',{'snapshots':snapshots,'arms':arms,'only_experimental_difference':'Harness-managed access to prior interactions/memory. No arm-specific database, task text, schema, README or task order. no_memory receives a fresh context per task; raw_history may retain prior interaction; distilled_memory receives its permitted memory. Benchmark does not execute models.','fresh_baseline':'A fresh T3 baseline MUST receive post.db, not pre.db. Each task can be staged in isolation.'})
    lines=['# Private gold summary','',f"Seed SHA-256: `{cfg['seed_sha256']}` (seed itself stays private).",'']
    for tid,g in gold.items():
        lines.extend([f'## {tid}','```json',json.dumps(g['answer'],indent=2,sort_keys=True),'```',''])
    (root/'private/gold_summary.md').write_text('\n'.join(lines))
