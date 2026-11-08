import pathlib,os,shutil,subprocess,re,stat
T=pathlib.Path('/opt/sql-jail-template');T.mkdir(exist_ok=True)
def put(src,dst=None):
 src=pathlib.Path(src);dst=T/str(dst or src).lstrip('/');dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists():return
 try:os.link(src.resolve(),dst)
 except OSError:shutil.copy2(src,dst,follow_symlinks=True)
def deps(path):
 r=subprocess.run(['ldd',str(path)],capture_output=True,text=True)
 for x in re.findall(r'(/[\w./+\-]+)',r.stdout):
  if pathlib.Path(x).is_file():put(x)
for n in ['bash','sh','sqlite3','grep','sed','cat','head','tail','sort','uniq','wc','cut','awk','find','ls','mkdir','rm','cp','mv','touch','date','printf','timeout','env','tee','xargs','basename','dirname','du','stat','file','tr','paste','column','less','more','readlink','realpath','sleep','yes','which','test']:
 src=shutil.which(n)
 if src:put(src,'/usr/bin/'+n);deps(src)
(T/'bin').symlink_to('usr/bin') if not (T/'bin').exists() else None
py='/usr/local/bin/python3.12';put(py);deps(py)
for n in ['python','python3']:
 p=T/'usr/local/bin'/n
 if not p.exists():p.symlink_to('python3.12')
src=pathlib.Path('/usr/local/lib/python3.12');dst=T/'usr/local/lib/python3.12'
if not dst.exists():shutil.copytree(src,dst,copy_function=os.link,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','tkinter','ensurepip','turtledemo'))
for p in (src/'lib-dynload').glob('*.so'):deps(p)
put('/lib/x86_64-linux-gnu/libseccomp.so.2');put('/etc/ld.so.cache');(T/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\n');(T/'etc/group').write_text('root:x:0:\n')
for f in ['null','zero','random','urandom']:
 p=T/'dev'/f;p.parent.mkdir(exist_ok=True)
 if not p.exists():os.mknod(p,stat.S_IFCHR|0o666,os.makedev(1,{'null':3,'zero':5,'random':8,'urandom':9}[f]));p.chmod(0o666)
(T/'opt/sql-study-bin').mkdir(parents=True,exist_ok=True);shutil.copy2('/opt/sql-study-bin/sqlite3',T/'opt/sql-study-bin/sqlite3')
for name in ['data','work','tmp','var/tmp','dev/shm']:(T/name).mkdir(parents=True,exist_ok=True)
print('Built template',T)
