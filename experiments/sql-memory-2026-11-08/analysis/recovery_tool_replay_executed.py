import json,pathlib,sys,hashlib
sys.path.insert(0,'/workspace/memory_sql_study')
from sandbox import Sandbox
R=pathlib.Path('/workspace/sql-memory-repo/experiments/sql-memory-2026-11-08');B=pathlib.Path('/workspace/memory_sql_study/bench')
a=json.load(open(R/'public_results/action_categories.json'))['commands'];todo=[('diag-glm-t2-history-r2','T2'),('diag-glm-t2-reset-r1','T2'),('diag-glm-t2-reset-r2','T2'),('main-glm-stateless','T2'),('main-glm-stateless','T3')]
for idx,(job,task) in enumerate(todo):
 sb=Sandbox('recovered-tools-'+job+'-'+task,24000+idx,False);db=B/'snapshots'/('post.db' if task=='T3' else 'pre.db');sb.prepare(db,B/'agent/README.md')
 d={'provenance':'TOOL-ONLY RE-EXECUTION AFTER CONTAINER LOSS. Commands archived before loss; outputs below newly generated. NO MODEL CALLS. NOT an original trace or original model final answer. Original model/API cost is in cost_summary.json.','original_job':job,'task':task,'snapshot_sha256':hashlib.sha256(db.read_bytes()).hexdigest(),'commands':[]}
 for x in sorted((x for x in a if x['job']==job and x['task']==task),key=lambda x:(x['turn_1based'],x['command_1based'])):
  assert hashlib.sha256(x['command'].encode()).hexdigest()==x['command_sha256']
  r=sb.run(x['command']);d['commands'].append({'original_command_id':x['command_id'],'command_sha256':x['command_sha256'],'original_wall_s':x['shell_wall_s'],'original_exit_code':x['exit_code'],'reexecuted':r});print(job,task,x['turn_1based'],r['exit_code'],flush=True)
 p=R/'public_results/recovery_tool_replays'/job/(task+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
