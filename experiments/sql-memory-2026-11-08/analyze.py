import pathlib,json,sys,csv,re,statistics
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'bench'));from grade import grade

def extract(s):
 s=s.strip()
 if s.startswith('```'):s=re.sub(r'^```(?:json)?\s*','',s);s=re.sub(r'\s*```$','',s)
 try:return json.loads(s)
 except:
  i=s.find('{');return json.JSONDecoder().raw_decode(s[i:])[0]

def analyze():
 rows=[]
 for p in sorted((ROOT/'runs').glob('*/*/trace.json')):
  d=json.loads(p.read_text());job=p.parent.parent.name;manifest=json.load(open(p.parent.parent/'manifest.json'))
  turns=d.get('turns',[]);tools=[r for t in turns for r in t.get('tool_results',[])];sqls=[s for r in tools for s in r.get('sql_cli_calls',[])];tok=[t.get('token_accounting',{}) for t in turns]
  row={'valid_for_comparison':manifest.get('valid_for_comparison',True),'job':job,'provider':manifest['provider'],'arm':manifest['arm'],'task':d['task_id'],'status':d['status'],'numeric_correct':None,'metric_fraction':None,'schema_valid':None,'evidence_valid':None,'model_calls':len(turns),'shell_calls':len(tools),'sql_cli_invocations':len(sqls),'sql_cli_over_1s':sum(s['wall_seconds']>1 for s in sqls),'sql_cli_seconds':sum(s['wall_seconds'] for s in sqls),'shell_over_1s':sum(r['wall_seconds']>1 for r in tools),'shell_seconds':sum(r['wall_seconds'] for r in tools),'model_seconds':sum(t['elapsed_s'] for t in turns),'elapsed_seconds':d.get('elapsed_s'),'cost_usd':sum(t.get('cost_usd') or 0 for t in turns) if manifest['provider']!='codex' else None,'input_tokens':sum(x.get('input_tokens') or 0 for x in tok),'cached_tokens':sum(x.get('cache_read_input_tokens') or 0 for x in tok),'cache_write_tokens':sum(x.get('cache_creation_input_tokens') or 0 for x in tok),'output_tokens':sum(x.get('output_tokens') or 0 for x in tok),'reasoning_tokens':sum(x.get('reasoning_tokens') or 0 for x in tok),'notes_before_chars':sum(len(v) for v in d.get('memory_before',{}).values()),'notes_after_chars':sum(len(v) for v in d.get('memory_after',{}).values()),'db_unchanged':d.get('db_unchanged'),'truncated_calls':sum(r['truncated'] for r in tools)}
  if d['status']=='completed':
   try:
    answer=extract(d['final_text']);g=grade(d['task_id'],answer);row.update(numeric_correct=g['metric_fraction']==1,metric_fraction=g['metric_fraction'],schema_valid=g['schema_valid'],evidence_valid=bool(g['evidence_execution_checks']) and all(x['read_only_executable_with_table_reads'] for x in g['evidence_execution_checks']))
    (p.parent/'grade.json').write_text(json.dumps(g,indent=2));pub=ROOT/'public_results'/job/d['task_id'];pub.mkdir(parents=True,exist_ok=True);(pub/'grade.json').write_text(json.dumps(g,indent=2))
   except Exception as e:row['grading_error']=str(e)
  rows.append(row)
 out=ROOT/'public_results';out.mkdir(exist_ok=True);(out/'summary.json').write_text(json.dumps(rows,indent=2));keys=list(dict.fromkeys(k for r in rows for k in r))
 with open(out/'summary.csv','w') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
 for r in rows:print(r['job'],r['task'],r['status'],'numeric',r['numeric_correct'],'fraction',round(r['metric_fraction'] or 0,3),'calls',r['shell_calls'],'cache',r['cached_tokens'],'memory',r['notes_after_chars'],'USD',r['cost_usd'])
if __name__=='__main__':analyze()
