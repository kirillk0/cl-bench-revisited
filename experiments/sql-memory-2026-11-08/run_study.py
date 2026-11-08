#!/usr/bin/env python3
"""Run a sequence with native tools; evaluate only after finishing, never feed gold back."""
import argparse,pathlib,json,time,hashlib,os,uuid,fcntl,traceback
from providers import create,from_state,ProviderError
from sandbox import Sandbox
ROOT=pathlib.Path(__file__).resolve().parent
COMMON='''You are a SQL analyst working with a local SQLite database. You have a generic bash tool. The read-only database is ../data/current.db; README.md describes the business data contract. Inspect files, schema and data as needed; sqlite3 CLI and Python are available. Return the JSON requested by the user, with executable SQL evidence. Your work directory is scratch space and is recreated for every new task. There is no network access. Tool output is limited to 60,000 characters, with explicit truncation; use normal shell filtering or files for larger outputs. There is no score or penalty for the number of SQL queries. Focus on correct, supported answers.'''
MEMORY=' A persistent writable directory ../memory is available for notes between tasks. You may read and maintain it using normal shell commands if useful.'
MEMORY_LIFECYCLE=' Future tasks will start in a fresh conversation with no access to this conversation. Only files in ../memory persist across tasks; other working files are cleared. You may use and maintain that directory to carry forward anything you consider useful, using the normal shell tools. Its contents are not automatically added to your context.'
MEMORY_MAINTAIN=' Future tasks start in fresh conversations without this conversation; only files in ../memory persist across tasks. At the start of a task, inspect your saved notes if any. Before completing a task, maintain notes in ../memory for your future self. You choose what information to retain, change, or delete and how to organize the files. Use the ordinary shell tools. Notes are not automatically added to your context.'
MODELS={'codex':'gpt-6-luna','anthropic':'claude-haiku-5-5','openrouter':'z-ai/glm-5.3-flash'}
def dump(path,obj):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(path)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def sanitize(v):
 if isinstance(v,dict):return {k:({'omitted':True,'sha256':hashlib.sha256(str(x).encode()).hexdigest(),'length':len(str(x))} if k in ['encrypted_content','signature','encrypted_function_args'] else sanitize(x)) for k,x in v.items()}
 if isinstance(v,list):return [sanitize(x) for x in v]
 return v
def cost(provider,turn):
 if provider!='anthropic':return turn.get('cost_usd')
 u=turn['usage'];i=u.get('input_tokens',0);o=u.get('output_tokens',0);r=u.get('cache_read_input_tokens',0);w=u.get('cache_creation_input_tokens',0);tier=5 if i+r+w>100000 else 1
 c=u.get('cache_creation',{});w1=c.get('ephemeral_1h_input_tokens',0);w5=c.get('ephemeral_5m_input_tokens',w-w1)
 return tier*(i*.10+o*.50+r*.01+w5*.125+w1*.20)/1e6

def ledger(provider,entry=None):
 p=ROOT/'ledger.jsonl';p.touch();
 with open(p,'r+') as f:
  fcntl.flock(f,fcntl.LOCK_EX);rows=[json.loads(l) for l in f if l.strip()]
  total=sum((r.get('cost_usd') or 0) for r in rows if r['provider']==provider)
  if entry is not None:f.write(json.dumps({'provider':provider,**entry})+'\n');f.flush();total+=entry.get('cost_usd') or 0
  fcntl.flock(f,fcntl.LOCK_UN)
 return total

def run(args):
 tasks_data=json.loads((ROOT/'bench/manifests/tasks.json').read_text());tasks=tasks_data if isinstance(tasks_data,list) else tasks_data['tasks']
 if args.tasks:tasks=[t for t in tasks if t.get('id',t.get('task_id')) in args.tasks.split(',')]
 job=args.job or f'{args.provider}-{args.arm}-{time.strftime("%Y%m%dT%H%M%S")}'
 out=ROOT/'runs'/job;out.mkdir(parents=True,exist_ok=False)
 idx={'codex':0,'anthropic':1,'openrouter':2}[args.provider]*3+{'stateless':0,'icl':1,'managed':2}[args.arm]
 sb=Sandbox(job,22000+idx+args.uid_offset,args.arm=='managed')
 cfg={'max_tokens':args.max_output_tokens,'read_timeout':240}
 if args.provider=='anthropic':cfg.update(thinking={'type':'adaptive'},rates={'input':.10,'output':.50,'cache_read':.01,'cache_write_5m':.125,'cache_write_1h':.20})
 session=None
 if args.state:session=from_state(json.loads(pathlib.Path(args.state).read_text()))
 if args.memory:
  mem=json.loads(pathlib.Path(args.memory).read_text())
  for name,text in mem.items():
   p=sb.root/'memory'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);os.chown(p,sb.uid,sb.uid)
 memory_instruction={'minimal':MEMORY,'lifecycle':MEMORY_LIFECYCLE,'maintain':MEMORY_MAINTAIN}[args.memory_instruction]
 metadata={'job':job,'provider':args.provider,'model':MODELS[args.provider],'arm':args.arm,'tasks':[t.get('id',t.get('task_id')) for t in tasks],'started_at':time.time(),'valid_for_comparison':True,'sandbox_version':'chroot-v2','memory_instruction_variant':args.memory_instruction,'system':COMMON+(memory_instruction if args.arm=='managed' else ''),'guards':{'model_turns':80,'task_wall_s':900,'shell_wall_s':60,'output_chars':60000,'max_output_tokens':args.max_output_tokens},'protocol_sha256':sha(ROOT/'analysis/protocol.md')}
 dump(out/'manifest.json',metadata)
 for task in tasks:
  tid=task.get('id',task.get('task_id'));ep=out/tid;ep.mkdir()
  snapshot=task.get('snapshot','post.db' if tid=='T3' else 'pre.db');db=ROOT/'bench/snapshots'/pathlib.Path(snapshot).name
  sb.prepare(db,ROOT/'bench/agent/README.md');hash_before=sha(db)
  if session is None or args.arm!='icl':session=create(args.provider,MODELS[args.provider],metadata['system'],job+'-'+tid if args.arm!='icl' else job,config=cfg)
  dump(ep/'pre_state.private.json',session.export_state());dump(ep/'memory_before.json',sb.memory())
  prompt=task.get('prompt',task.get('question',task.get('instructions')))
  if task.get('response_schema'):prompt+='\n\nRequired JSON response schema:\n'+json.dumps(task['response_schema'],ensure_ascii=False)
  if not isinstance(prompt,str):raise ValueError('Task prompt missing')
  session.add_user(prompt);start=time.perf_counter();record={'task_id':tid,'db_sha256':hash_before,'snapshot':pathlib.Path(snapshot).name,'prompt':prompt,'turns':[],'status':'running','final_text':None,'memory_before':sb.memory()}
  print(json.dumps({'job':job,'task':tid,'event':'start'}),flush=True)
  for n in range(80):
   if time.perf_counter()-start>900:record['status']='wall_guard';break
   cap={'anthropic':19.,'openrouter':4.5,'codex':float('inf')}[args.provider]
   if ledger(args.provider)>=cap:record['status']='budget_guard';break
   try:
    turn=session.step();turn['cost_usd']=cost(args.provider,turn)
   except Exception as e:
    record['status']='provider_error';record['error']={'type':type(e).__name__,'message':str(e)}
    state=session.export_state();u=(state.get('last_response') or {}).get('usage')
    if u:
     c=cost(args.provider,{'usage':u,'cost_usd':u.get('cost')});ledger(args.provider,{'job':job,'task':tid,'turn':n,'cost_usd':c,'usage':u,'error':str(e),'time':time.time()})
    dump(ep/'error_state.private.json',state);break
   ledger(args.provider,{'job':job,'task':tid,'turn':n,'cost_usd':turn['cost_usd'],'usage':turn['usage'],'time':time.time()})
   state=session.export_state();turn['native_response']=sanitize(state.get('last_response'));turn['state_chars']=len(json.dumps(state.get('native_history',[])));turn['tool_results']=[]
   results=[]
   for call in turn['tool_calls']:
    cmd=call['arguments'].get('command') if isinstance(call.get('arguments'),dict) else json.loads(call['arguments'])['command']
    if call['name'].split('.')[-1]!='bash':raise RuntimeError('Unexpected tool')
    res=sb.run(cmd);turn['tool_results'].append(res);results.append({'id':call['id'],'output':res['output']+f'\n[exit_code={res["exit_code"]}]'})
   record['turns'].append(turn);record['elapsed_s']=time.perf_counter()-start;dump(ep/'trace.json',record)
   print(json.dumps({'job':job,'task':tid,'turn':n+1,'calls':len(results),'cost':turn['cost_usd'],'model_s':round(turn['elapsed_s'],1)}),flush=True)
   if not results:
    record['final_text']=turn['final_text'];record['status']='completed';break
   session.add_tool_results(results)
  else:record['status']='turn_guard'
  record['elapsed_s']=time.perf_counter()-start;record['memory_after']=sb.memory();record['db_hash_after']=sha(sb.root/'data/current.db');record['db_unchanged']=record['db_hash_after']==hash_before
  dump(ep/'trace.json',record);dump(ep/'post_state.private.json',session.export_state());dump(ep/'memory_after.json',sb.memory())
  pub=ROOT/'public_results'/job/tid;dump(pub/'trace.json',record)
  (ep/'final.txt').write_text(record.get('final_text') or '')
  print(json.dumps({'job':job,'task':tid,'event':'finished','status':record['status'],'turns':len(record['turns']),'cost_usd':sum(t['cost_usd'] or 0 for t in record['turns']),'elapsed_s':round(record['elapsed_s'],1)}),flush=True)
  if record['status']!='completed':break
 metadata['finished_at']=time.time();dump(out/'manifest.json',metadata);dump(ROOT/'public_results'/job/'manifest.json',metadata)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--provider',choices=MODELS,required=True);ap.add_argument('--arm',choices=['stateless','icl','managed'],required=True);ap.add_argument('--job');ap.add_argument('--tasks');ap.add_argument('--state');ap.add_argument('--memory');ap.add_argument('--uid-offset',type=int,default=0);ap.add_argument('--max-output-tokens',type=int,default=8192);ap.add_argument('--memory-instruction',choices=['minimal','lifecycle','maintain'],default='minimal');run(ap.parse_args())
