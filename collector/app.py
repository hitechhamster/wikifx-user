import os,sys,json,time,threading,datetime,hashlib,contextlib,io,traceback
from pathlib import Path
import requests
from flask import Flask,request,jsonify
from waitress import serve
from convert import pages
sys.path.insert(0,str(Path('legacy').resolve()))
app=Flask(__name__);jobs={};lock=threading.Lock();usage=[];runs=[];market='';serper=0
ORIGIN='https://hotspots.wikifxusers.com'
def upload(date,name,data):
 r=requests.post(ORIGIN+'/api/internal/collector-artifact',headers={'Authorization':'Bearer '+os.environ['SIGNAL_INGEST_TOKEN'],'X-Artifact-Key':'cloud/'+date+'/'+name,'Content-Type':'application/octet-stream'},data=data,timeout=120);r.raise_for_status()
def instrument():
 from openai.resources.chat.completions import Completions
 original=Completions.create
 def tracked(self,*args,**kw):
  response=original(self,*args,**kw);u=response.usage.model_dump() if response.usage else {};hit=u.get('prompt_cache_hit_tokens',0);cost=(hit*.006+(u.get('prompt_tokens',0)-hit)*.3+u.get('completion_tokens',0)*1.2)/1e6
  with lock:usage.append({'market':market,'model':response.model,'usage':u,'estimated_cost_usd':cost,'pricing':'USD/M input .3 cached .006 output 1.2; estimate'})
  return response
 Completions.create=tracked
 original_request=requests.sessions.Session.request
 def tracked_request(self,method,url,**kw):
  global serper
  if url.startswith('https://api.apify.com/'):
   params=kw.get('params')
   if isinstance(params,dict) and 'token' in params:
    params=dict(params);token=params.pop('token');kw['params']=params;kw['headers']={**kw.get('headers',{}),'Authorization':'Bearer '+token}
  if 'google.serper.dev/' in url:
   with lock:serper+=1
  response=original_request(self,method,url,**kw)
  if url.startswith('https://api.apify.com/v2/acts/') and url.endswith('/runs') and method.upper()=='POST' and response.ok:
   with lock:runs.append({'market':market,'id':response.json()['data']['id']})
  return response
 requests.sessions.Session.request=tracked_request
 from src.apify import Apify
 def settle(self):
  total=0
  for run in runs:
   try:
    r=requests.get('https://api.apify.com/v2/actor-runs/'+run['id'],headers={'Authorization':'Bearer '+self.token},timeout=30);r.raise_for_status();d=r.json()['data'];run['cost_usd']=float(d.get('usageTotalUsd') or 0);run['status']=d.get('status');total+=run['cost_usd']
   except Exception:run['cost_usd']=None
  self.cost_usd=total;return total
 Apify.settle_cost=settle
instrument()
class SafeLog(io.StringIO):
 def write(self,s):
  for key in ['APIFY_TOKEN','SERPER_API_KEYS','DEEPSEEK_API_KEY','SIGNAL_INGEST_TOKEN']:
   for secret in os.environ.get(key,'').split(','):
    if secret:s=s.replace(secret,'[redacted]')
  return super().write(s)
def run(date):
 global market,serper
 runs.clear();usage.clear();serper=0
 from types import SimpleNamespace
 import run_daily
 from src.apify import Apify
 log=SafeLog();result={'date':date,'markets':{},'state':'running'}
 try:
  reports={};completed={};api=Apify();args=SimpleNamespace(hours=None,top=None,dry_run=False,no_search=False)
  limits=api.account_usage()
  if limits and limits['limit']-limits['used']<sum(run_daily.load_config(m)['run'].get('max_cost_usd',.5) for m in ['global','india','pakistan','indonesia']):raise ValueError('APIFY_BUDGET_INSUFFICIENT')
  with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
   # The original run_region pipeline and market configs are reused unchanged.
   for market in ['global','india','pakistan','indonesia']:
    try:
     r=run_daily.run_region(market,args,api)
     if r:
      completed[market]=r;report=json.loads(r['paths']['json'].read_text(encoding='utf8'));reports[market]=report;result['markets'][market]={'state':'complete','count':len(report['topics'])}
      upload(date,'daily/'+market+'.json',r['paths']['json'].read_bytes());upload(date,'daily/'+market+'.md',r['paths']['md'].read_bytes())
      for raw in (Path('legacy/data/raw')/market).glob(date+'*.json'):upload(date,'raw/'+market+'/'+raw.name,raw.read_bytes())
     else:result['markets'][market]={'state':'failed','reason':'NO_REPORT'}
    except Exception as exc:result['markets'][market]={'state':'failed','reason':type(exc).__name__}
   api.settle_cost()
   for m,r in completed.items():
    r['meta']['cost_usd']=round(sum(x.get('cost_usd') or 0 for x in runs if x['market']==m),4)
    run_daily.write_reports(r['topics'],r['meta'],r['daily_dir'],date)
    reports[m]=json.loads(r['paths']['json'].read_text(encoding='utf8'))
    upload(date,'daily/'+m+'.json',r['paths']['json'].read_bytes());upload(date,'daily/'+m+'.md',r['paths']['md'].read_bytes())
   if completed:
    cfg=next(iter(completed.values()))['cfg'];board=run_daily.pick_top_board({m:r['topics'] for m,r in completed.items()},cfg)
    run_daily.write_top_board(board,date,Path('legacy/data/daily/_board'),cfg)
    for f in Path('legacy/data/daily/_board').glob(date+'.*'):upload(date,'daily/_board.'+f.suffix.lstrip('.'),f.read_bytes())
  result.update(apify_runs=runs,ai_calls=usage,serper_calls=serper)
  for m,v in result['markets'].items():v['apify_cost_usd']=sum(r.get('cost_usd') or 0 for r in runs if r['market']==m);v['ai_cost_usd']=sum(r['estimated_cost_usd'] for r in usage if r['market']==m)
  manifest=pages(reports,date);upload(date,'manifest.json',json.dumps(manifest,ensure_ascii=False).encode())
  for page in manifest['pages']:
   r=requests.post(ORIGIN+'/api/v1/hotspots/daily-batches',headers={'Authorization':'Bearer '+os.environ['SIGNAL_INGEST_TOKEN'],'Idempotency-Key':page['batch_id']+':'+str(page['page_no'])},json=page,timeout=120)
   if r.status_code not in [200,201]:raise ValueError('INGEST_HTTP_'+str(r.status_code))
  result['state']='complete' if len(reports)==4 else 'partial'
 except Exception as exc:result.update(state='failed',error=type(exc).__name__)
 finally:
  result.update(apify_runs=runs,ai_calls=usage,serper_calls=serper)
  try:upload(date,'collection-log.txt',log.getvalue().encode());upload(date,'result.json',json.dumps(result,ensure_ascii=False).encode())
  except Exception:result['archive_error']=True
  jobs[date]=result
@app.get('/health')
def health():return jsonify(ok=True,configured=all(os.environ.get(k) for k in ['APIFY_TOKEN','SERPER_API_KEYS','DEEPSEEK_API_KEY','SIGNAL_INGEST_TOKEN']))
@app.post('/jobs/<date>')
def start(date):
 if date!=datetime.datetime.now().strftime('%Y-%m-%d'):return jsonify(error='DATE_MISMATCH'),400
 with lock:
  if date not in jobs:
   if any(v['state']=='running' for v in jobs.values()):return jsonify(error='BUSY'),429
   jobs[date]={'state':'running'};threading.Thread(target=run,args=(date,),daemon=True).start()
 return jsonify(state=jobs[date]['state']),202
@app.get('/jobs/<date>')
def status(date):return jsonify({'state':jobs.get(date,{}).get('state','missing')})
if __name__=='__main__':serve(app,host='0.0.0.0',port=8080,threads=4)
