import os,json,shutil,pathlib,types
os.environ['APIFY_TOKEN']='test-placeholder';os.environ['SIGNAL_INGEST_TOKEN']='test-placeholder'
import app,run_daily
from src.apify import Apify
order=[];uploads={};sent=[]
Apify.account_usage=lambda self:{}
Apify.settle_cost=lambda self:0
def fake_region(m,args,api):
 order.append(m);directory=pathlib.Path('/tmp/smoke')/m;directory.mkdir(parents=True,exist_ok=True)
 report=json.loads(pathlib.Path('/fixtures/'+m+'.json').read_text());jp=directory/'2026-10-26.json';jp.write_text(json.dumps(report));mp=directory/'2026-10-26.md';mp.write_text('fixture')
 return dict(region=m,topics=report['topics'],cfg=run_daily.load_config(m),meta=report['meta'],paths={'json':jp,'md':mp},date='2026-10-26',daily_dir=directory)
run_daily.run_region=fake_region
app.upload=lambda date,name,data:uploads.__setitem__(name,data)
def post(url,**kw):sent.append(kw['json']);return types.SimpleNamespace(status_code=201)
app.requests.post=post
app.requests.get=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Unexpected network'))
app.run('2026-10-26')
assert app.jobs['2026-10-26']['state']=='complete',app.jobs
assert order==['global','india','pakistan','indonesia'],order
assert len(sent)==4
assert all(x['source_system']=='wikifx-signal' for x in sent)
assert 'result.json' in uploads and 'daily/_board.md' in uploads
print(json.dumps({'state':'passed','sequential_markets':order,'intake_pages':len(sent),'real_external_calls':0,'archived_files':sorted(uploads)}))
