"""Generic shell execution, no SQL-specific agent API; private dataset/gold isolation."""
import os,pathlib,subprocess,time,signal,resource,ctypes,errno,shutil,json,re
BASE=pathlib.Path('/workspace/sql_sandboxes');BASE.mkdir(exist_ok=True);BASE.chmod(0o755)
BIN=pathlib.Path('/opt/sql-study-bin');BIN.mkdir(exist_ok=True)
WRAPPER='''#!/usr/local/bin/python3
import subprocess,sys,time,json
s=time.perf_counter()
p=subprocess.run(['/usr/bin/sqlite3','-readonly']+sys.argv[1:])
print('\\n__SQL_CLI_TIMING__'+json.dumps({'wall_seconds':time.perf_counter()-s,'exit_code':p.returncode}),file=sys.stderr)
sys.exit(p.returncode)
'''
(BIN/'sqlite3').write_text(WRAPPER);(BIN/'sqlite3').chmod(0o755)
def lockdown(uid):
 os.setgroups([]);os.setgid(uid);os.setuid(uid)
 resource.setrlimit(resource.RLIMIT_AS,(600*1024**2,600*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(45,45));resource.setrlimit(resource.RLIMIT_NPROC,(48,48));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
 lib=ctypes.CDLL('libseccomp.so.2');lib.seccomp_init.restype=ctypes.c_void_p;lib.seccomp_init.argtypes=[ctypes.c_uint32];ctx=lib.seccomp_init(0x7fff0000)
 lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint];lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
 for name in [b'socket',b'connect']:
  n=lib.seccomp_syscall_resolve_name(name);lib.seccomp_rule_add(ctx,0x00050000|errno.EPERM,n,0)
 if lib.seccomp_load(ctx)!=0:os._exit(125)
 lib.seccomp_release(ctx)
class Sandbox:
 def __init__(self,name,uid,managed=False):
  self.root=BASE/name;self.uid=uid;self.managed=managed
  
  if not self.root.exists():
   shutil.copytree('/opt/sql-jail-template',self.root,copy_function=os.link,ignore=shutil.ignore_patterns('null','zero','random','urandom'))
   import stat
   for name,minor in [('null',3),('zero',5),('random',8),('urandom',9)]:
    os.mknod(self.root/'dev'/name,stat.S_IFCHR|0o666,os.makedev(1,minor));(self.root/'dev'/name).chmod(0o666)
  os.chown(self.root,0,uid);self.root.chmod(0o750)
  (self.root/'data').mkdir(exist_ok=True);(self.root/'data').chmod(0o755)
  if managed:
   (self.root/'memory').mkdir(exist_ok=True);os.chown(self.root/'memory',uid,uid);(self.root/'memory').chmod(0o700)
 def prepare(self,db,readme):
  w=self.root/'work'
  if w.exists():shutil.rmtree(w)
  w.mkdir();os.chown(w,self.uid,self.uid);w.chmod(0o700)
  for folder in ['tmp','var/tmp','dev/shm']:
   x=self.root/folder
   if x.exists():shutil.rmtree(x)
   x.mkdir();os.chown(x,self.uid,self.uid);x.chmod(0o700)
  shutil.copyfile(db,self.root/'data/current.db');(self.root/'data/current.db').chmod(0o444)
  shutil.copyfile(readme,w/'README.md');(w/'README.md').chmod(0o444)
 def memory(self):
  p=self.root/'memory';return {str(x.relative_to(p)):x.read_text(errors='replace') for x in p.rglob('*') if x.is_file() and not x.is_symlink()} if p.exists() else {}
 def _enter(self):
  os.chroot(self.root);os.chdir('/work');lockdown(self.uid)
 def run(self,command,timeout=60,max_output=60000):
  start=time.perf_counter();env={'PATH':'/opt/sql-study-bin:/usr/local/bin:/usr/bin:/bin','HOME':'/work','TMPDIR':'/tmp','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PROOT_NO_SECCOMP':'1'}
  proc=subprocess.Popen(['/bin/bash','--noprofile','--norc','-c',command],cwd=self.root/'work',env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,preexec_fn=self._enter)
  timed=False
  try:out,err=proc.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
   timed=True;os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate()
  text=out.decode(errors='replace')+('\nSTDERR:\n'+err.decode(errors='replace') if err else '')
  sql=[]
  for ln in err.decode(errors='replace').splitlines():
   if ln.startswith('__SQL_CLI_TIMING__'):
    try:sql.append(json.loads(ln[len('__SQL_CLI_TIMING__'):]))
    except:pass
  truncated=len(text)>max_output
  if truncated:text=text[:max_output]+f'\n[OUTPUT TRUNCATED: original {len(text)} characters; use shell filtering or output file.]'
  return {'output':text,'exit_code':proc.returncode,'wall_seconds':time.perf_counter()-start,'timeout':timed,'truncated':truncated,'sql_cli_calls':sql,'command':command}
