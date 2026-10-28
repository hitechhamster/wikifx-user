import sqlite3,pathlib,hashlib,json,tarfile
root=pathlib.Path('/home/admin/wikifx-signal/data')
out=pathlib.Path('/tmp/wikifx-migration-20261026');out.mkdir(exist_ok=True)
source=sqlite3.connect('file:'+str(root/'signal.sqlite3')+'?mode=ro',uri=True)
dest=sqlite3.connect(out/'signal.sqlite3');source.backup(dest);dest.close();source.close()
manifest=[]
with tarfile.open(out/'history.tgz','w:gz') as tar:
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.name.startswith('signal.sqlite3'):continue
  content=p.read_bytes();manifest.append({'path':p.relative_to(root).as_posix(),'size':len(content),'sha256':hashlib.sha256(content).hexdigest()});tar.add(p,arcname=p.relative_to(root).as_posix())
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8')
c=sqlite3.connect(out/'signal.sqlite3');tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
print(json.dumps({'tables':{t:c.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables},'files':len(manifest),'bytes':sum(x['size'] for x in manifest),'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'sqlite_sha256':hashlib.sha256((out/'signal.sqlite3').read_bytes()).hexdigest(),'archive_sha256':hashlib.sha256((out/'history.tgz').read_bytes()).hexdigest()}))
