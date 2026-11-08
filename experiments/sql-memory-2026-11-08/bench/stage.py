#!/usr/bin/env python3
"""Trusted-harness-only staging. Exposes exactly current.db, README.md and TASK.json."""
import argparse, hashlib, json, os, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def stage(task_id,arm,dest):
    manifest=json.loads((ROOT/'manifests/tasks.json').read_text())
    arms=json.loads((ROOT/'manifests/arms.json').read_text())['arms']
    if arm not in arms: raise ValueError('Unknown arm')
    task=next(t for t in manifest['tasks'] if t['id']==task_id)
    dest=Path(dest).absolute()
    # A harness must never expose the private tree or overwrite an existing run.
    if dest.is_symlink() or ROOT==dest.resolve() or ROOT in dest.resolve().parents:
        raise ValueError('Destination must be outside private benchmark root')
    if dest.exists() and any(dest.iterdir()): raise ValueError('Destination must be empty')
    dest.mkdir(parents=True,exist_ok=True);dest.chmod(0o755)
    source=ROOT/'snapshots'/task['snapshot']
    binding=arms[arm]['task_bindings'][task_id]
    actual=hashlib.sha256(source.read_bytes()).hexdigest()
    if actual!=task['snapshot_sha256'] or actual!=binding['sha256'] or binding['snapshot']!=task['snapshot']:
        raise ValueError('Snapshot binding/hash mismatch')
    shutil.copyfile(source,dest/'current.db')
    shutil.copyfile(ROOT/'agent/README.md',dest/'README.md')
    public={k:task[k] for k in ('id','title','instructions','response_schema')}
    (dest/'TASK.json').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
    for p in dest.iterdir(): p.chmod(0o444)
    return {'task':task_id,'arm':arm,'snapshot_sha256':actual,'files':['current.db','README.md','TASK.json']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task',required=True,choices=['W1','W2','T1','T2','T3'])
    p.add_argument('--arm',required=True,choices=['no_memory','raw_history','distilled_memory'])
    p.add_argument('--dest',required=True)
    a=p.parse_args();print(json.dumps(stage(a.task,a.arm,a.dest),indent=2))
