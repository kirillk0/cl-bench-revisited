"""Static standalone evidence viewer. No network, Javascript, model API or private states."""
from pathlib import Path
import json,html,subprocess,collections
R=Path(__file__).resolve().parents[1];P=R/'public_results'
def esc(x):return html.escape(str(x))
def md(p):return subprocess.check_output(['pandoc','-f','markdown','-t','html',str(p)],text=True)
def pre(x):return '<pre>'+esc(x)+'</pre>'
inv=json.loads((P/'recovery_inventory.json').read_text());cmds=json.loads((P/'action_categories.json').read_text())['commands'];cost=json.loads((P/'cost_summary.json').read_text());tasks={(t['job'],t['task']):t for t in cost['tasks']}
css='''body{max-width:1250px;margin:auto;padding:24px;font:16px/1.6 system-ui,sans-serif;color:#24344b;background:#f5f7fc}h1,h2,h3{color:#17396a;line-height:1.25}h2{margin-top:2.1em;border-bottom:2px solid #b9cee9;padding-bottom:.3em}a{color:#126ca8}table{border-collapse:collapse;width:100%;margin:18px 0;background:white;font-size:14px}td,th{border:1px solid #d3dce9;padding:8px;text-align:left;vertical-align:top}th{background:#dfebfa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f8;padding:14px;border-radius:6px;font:13px/1.5 ui-monospace,monospace;max-height:650px;overflow:auto}details{background:white;padding:12px 18px;margin:12px 0;border:1px solid #ccd8e7;border-radius:8px}summary{cursor:pointer;font-weight:650;color:#214775}.warning{background:#fff0da;border-left:5px solid #c6811c;padding:15px}.ok{background:#e2f5e9;padding:10px}.badge{font-size:13px;border-radius:8px;padding:4px 9px;background:#e6edf6}nav{position:sticky;top:0;background:#edf3fbed;padding:12px;border:1px solid #c4d1e5;z-index:2}nav a{margin-right:15px}blockquote{border-left:4px solid #5f92c6;padding-left:18px}code{overflow-wrap:anywhere} @media(max-width:650px){body{padding:10px;font-size:14px}table{display:block;overflow:auto}pre{font-size:11px}nav{position:static}}'''
out=['<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SQL-память: результаты и сохранённые доказательства</title><style>'+css+'</style><body>', '<nav><a href="#summary">Выводы</a><a href="#recovery">Сохранность</a><a href="#traces">Траектории</a><a href="#cost">Аудит затрат</a></nav><section id="summary">',md(R/'REPORT.md'),'</section><section id="recovery">',md(R/'RECOVERY.md'),'</section><h2 id="traces">Траектории и восстановленные команды</h2><p>Раскрывайте блоки. Ctrl/Cmd+F — поиск модели, задания или SQL. Показаны только валидные попытки. Старый contaminated pilot исключён. Синие блоки — оригиналы; жёлтые предупреждают об утрате исходного диалога.</p>']
for row in inv:
 job,task=row['job'],row['task'];c=tasks[(job,task)];p=P/job/task/'trace.json'
 out.append('<details id="'+esc(job+'-'+task)+'"><summary>'+esc(job+' · '+task)+' <span class="badge">'+esc('ОРИГИНАЛ · SHA совпал' if p.exists() else 'ОРИГИНАЛ УТРАЧЕН · команды/аудит сохранены')+'</span></summary>')
 out.append('<p>Provider: '+esc(c['provider'])+'; режим: '+esc(c['arm'])+'; cohort: '+esc(c['cohort'])+'; исходный статус: '+esc(c['status'])+'</p><details><summary>Исходные затраты и token accounting</summary>'+pre(json.dumps(c['cost_and_tokens'],ensure_ascii=False,indent=2))+'</details>')
 if p.exists():
  d=json.loads(p.read_text());out.append('<details><summary>Постановка задачи</summary>'+pre(d['prompt'])+'</details><details><summary>Память до / после</summary>'+pre(json.dumps({'before':d.get('memory_before'),'after':d.get('memory_after')},ensure_ascii=False,indent=2))+'</details><h3>Финальный ответ модели</h3>'+pre(d.get('final_text') or json.dumps(d.get('error'))))
  for i,t in enumerate(d['turns'],1):
   out.append('<details><summary>Ход '+str(i)+' · model '+str(round(t.get('elapsed_s',0),2))+' s</summary>')
   for z in t.get('tool_results',[]):out.extend(['<h4>bash</h4>',pre(z['command']),'<p>exit '+str(z['exit_code'])+'; shell '+str(round(z['wall_seconds'],3))+' s</p>',pre(z['output'])])
   out.append('<details><summary>Provider usage</summary>'+pre(json.dumps(t.get('usage'),ensure_ascii=False,indent=2))+'</details></details>')
 else:
  out.append('<p class="warning">Полного исходного разговора и final response здесь нет. Ниже — команды, заархивированные ДО сбоя. Если доступны результаты tool-only re-execution, они обозначены отдельно и НЕ являются исходными tool outputs.</p>')
  rp=P/'recovery_tool_replays'/job/(task+'.json');replay={}
  if rp.exists():replay={x['original_command_id']:x for x in json.loads(rp.read_text())['commands']}
  for x in (x for x in cmds if x['job']==job and x['task']==task):
   out.append('<details><summary>'+esc(x['command_id'])+' · исходный exit '+str(x['exit_code'])+'</summary>'+pre(x['command']))
   if x['command_id'] in replay:
    y=replay[x['command_id']]['reexecuted'];out.append('<p class="warning">ПОВТОРНОЕ ИСПОЛНЕНИЕ ИНСТРУМЕНТА ПОСЛЕ СБОЯ; API модели не вызывался.</p>'+pre(y['output']))
   out.append('</details>')
 out.append('</details>')
out.extend(['<h2 id="cost">Сохранённый до сбоя аудит затрат</h2><details><summary>Полный текст аудита, включая кэш и длительные SQL</summary>',md(R/'analysis/cost_audit.md'),'</details><footer>Автономный HTML: без JavaScript, внешних библиотек и сетевых запросов. Generated from recovered archive; original native_response/reasoning payloads deliberately excluded.</footer></body></html>'])
p=P/'report.html';p.write_text(''.join(out));print(p,p.stat().st_size,'bytes')
