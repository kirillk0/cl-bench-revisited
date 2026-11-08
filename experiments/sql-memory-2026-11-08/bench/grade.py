#!/usr/bin/env python3
"""Private deterministic metric scorer and SQL-safety check (no model/API calls).
Qualitative assessment and whether evidence actually supports claims remain human review.
"""
import argparse, json, math, sqlite3
from pathlib import Path
from audit import run_readonly
ROOT=Path(__file__).resolve().parent
MISSING=object()

def schema_errors(value,schema,path='$'):
    errors=[]; typ=schema.get('type'); types=typ if isinstance(typ,list) else [typ]
    def has_type(t):
        return {'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),'integer':isinstance(value,int) and not isinstance(value,bool),'number':isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value),'null':value is None}.get(t,True)
    if not any(has_type(t) for t in types): return [path+': wrong type']
    if isinstance(value,dict):
        for k in schema.get('required',[]):
            if k not in value: errors.append(path+'.'+k+': required')
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False:
            errors += [path+'.'+k+': unexpected' for k in value if k not in props]
        for k in value:
            if k in props:errors.extend(schema_errors(value[k],props[k],path+'.'+k))
    if isinstance(value,list):
        if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',float('inf')): errors.append(path+': wrong number of items')
        for i,item in enumerate(value): errors.extend(schema_errors(item,schema.get('items',{}),path+f'[{i}]'))
    return errors

def metric_checks(got,want,path='',out=None):
    if out is None:out=[]
    if isinstance(want,dict):
        for k,v in want.items():
            if k=='assessment':continue
            metric_checks(got.get(k,MISSING) if isinstance(got,dict) else MISSING,v,path+'.'+k,out)
    elif isinstance(want,list):
        # All gold row arrays have one or more categorical dimensions.
        dims=[k for k,v in want[0].items() if isinstance(v,str) and k not in ('before_json','after_json')] if want else []
        gl=got if isinstance(got,list) else []
        for row in want:
            matches=[r for r in gl if isinstance(r,dict) and all(r.get(k)==row[k] for k in dims)]
            label=','.join(f'{k}={row[k]}' for k in dims)
            metric_checks(matches[0] if len(matches)==1 else MISSING,row,path+'['+label+']',out)
        extra=[r for r in gl if not isinstance(r,dict) or not any(all(r.get(k)==w[k] for k in dims) for w in want)]
        if extra:out.append({'path':path+'.unexpected_rows','pass':False})
    else:
        if isinstance(want,int):ok=isinstance(got,(int,float)) and not isinstance(got,bool) and got==want
        elif isinstance(want,float):ok=isinstance(got,(int,float)) and not isinstance(got,bool) and math.isfinite(got) and abs(got-want)<=max(0.01,abs(want)*0.00001)
        elif path.endswith(('before_json','after_json')):
            try:ok=json.loads(got)==json.loads(want)
            except (ValueError,TypeError):ok=False
        else:ok=got==want
        out.append({'path':path,'pass':bool(ok)})
    return out

def grade(task_id,response):
    gold=json.loads((ROOT/'gold.json').read_text())[task_id]
    task=next(t for t in json.loads((ROOT/'manifests/tasks.json').read_text())['tasks'] if t['id']==task_id)
    errors=schema_errors(response,task['response_schema'])
    answer=response.get('answer',{}) if isinstance(response,dict) else {}
    sections={}
    for key,want in gold['answer'].items():
        if key=='assessment':continue
        checks=metric_checks(answer.get(key,MISSING) if isinstance(answer,dict) else MISSING,want,key)
        sections[key]={'correct':sum(c['pass'] for c in checks),'total':len(checks),'fraction':sum(c['pass'] for c in checks)/len(checks),'failed_paths':[c['path'] for c in checks if not c['pass']]}
    # Equal weight per answer section avoids letting large matched-cell arrays swamp all else.
    metric_fraction=sum(x['fraction'] for x in sections.values())/len(sections)
    con=sqlite3.connect(f"file:{ROOT/'snapshots'/task['snapshot']}?mode=ro",uri=True);con.row_factory=sqlite3.Row
    evidence=[]
    sqls=response.get('evidence_sql',[]) if isinstance(response,dict) else []
    for i,sql in enumerate(sqls if isinstance(sqls,list) else []):
        try:
            if not isinstance(sql,str):raise ValueError('Not a SQL string')
            rows=run_readonly(con,sql)
            evidence.append({'index':i,'read_only_executable_with_table_reads':True,'rows':len(rows)})
        except Exception as e:evidence.append({'index':i,'read_only_executable_with_table_reads':False,'error':str(e)})
    con.close()
    return {'task':task_id,'schema_valid':not errors,'schema_errors':errors,'metric_fraction':metric_fraction,'suggested_metric_points_out_of_70':70*metric_fraction,'section_results':sections,'evidence_execution_checks':evidence,'human_review_required':{'evidence_points_out_of_10':'Queries must actually support the reported values and attribution. Executing successfully or SELECTing constants is not sufficient.','verdict_points_out_of_20':gold['qualitative_rubric']},'overall_score':None,'note':'No automatic preferred-opinion score. Review factual criteria, uncertainty and evidence support; invalid schema prevents full credit but does not erase diagnostics.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',required=True);p.add_argument('--response',required=True)
    a=p.parse_args();print(json.dumps(grade(a.task,json.loads(Path(a.response).read_text())),indent=2))
