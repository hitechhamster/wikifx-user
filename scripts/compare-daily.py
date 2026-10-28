"""Manual, local-only Hangzhou read. No SSH credentials are uploaded."""
import argparse,datetime,pathlib,subprocess,json,hashlib,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--date',default=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d'));args=p.parse_args();datetime.date.fromisoformat(args.date)
out=ROOT/'artifacts'/'comparisons'/args.date;out.mkdir(parents=True,exist_ok=True)
def command(a):subprocess.run(a,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def r2get(key,path):command(['node','node_modules/wrangler/bin/wrangler.js','r2','object','get','wikifx-signal-archive/'+key,'--remote','--file',str(path)])
def load(p):return json.loads(p.read_text(encoding='utf8'))
def canon(u):
 x=urllib.parse.urlsplit(u);return x.netloc.lower().removeprefix('www.')+x.path.rstrip('/')
r2get('cloud/'+args.date+'/result.json',out/'cloud-result.json');cloud=load(out/'cloud-result.json')
if cloud.get('state') not in ['complete','partial']:raise SystemExit('Cloudflare collection has not completed; retry later.')
results=[]
for market in ['global','india','pakistan','indonesia']:
 try:
  r2get('cloud/'+args.date+'/daily/'+market+'.json',out/(market+'-cloud.json'))
  command(['scp','-q','-o','BatchMode=yes','admin@118.178.178.211:/home/admin/wikifx-signal/data/daily/'+market+'/'+args.date+'.json',str(out/(market+'-hangzhou.json'))])
  a,b=load(out/(market+'-cloud.json')),load(out/(market+'-hangzhou.json'))
  if a['date']!=args.date or b['date']!=args.date:raise ValueError('DATE_MISMATCH')
  aa,bb=a['topics'],b['topics'];ka=[canon(t['lead']['url']) for t in aa[:10]];kb=[canon(t['lead']['url']) for t in bb[:10]];common=set(ka)&set(kb)
  detail={'market':market,'cloud_count':len(aa),'hangzhou_count':len(bb),'top10_overlap_count':len(common),'top10_overlap_ratio':len(common)/min(10,len(aa),len(bb)) if aa and bb else None,'cloud_only':[{'title':t.get('label'),'url':t['lead']['url']} for t in aa[:10] if canon(t['lead']['url']) not in common],'hangzhou_only':[{'title':t.get('label'),'url':t['lead']['url']} for t in bb[:10] if canon(t['lead']['url']) not in common],'rank_changes':[{'url':u,'cloud_rank':ka.index(u)+1,'hangzhou_rank':kb.index(u)+1} for u in common if ka.index(u)!=kb.index(u)],'costs':{'cloud':cloud.get('markets',{}).get(market,{}),'hangzhou_apify_reported_usd':b.get('meta',{}).get('cost_usd'),'hangzhou_ai_usd':None,'hangzhou_ai_note':'原采集日报未记录 token/AI费用；无法从日报准确追溯，不按0计','hangzhou_apify_note':'原程序按账户时间窗口估算，双跑时可能混入云端run；报告值非独立核算'},'possible_difference_causes':['独立采集时间差、来源返回变化和互动量变化','Serper实时结果及AI话题命名具有波动；非已证实归因'],'hashes':{side:hashlib.sha256((out/(market+'-'+side+'.json')).read_bytes()).hexdigest() for side in ['cloud','hangzhou']}}
  results.append(detail)
 except (subprocess.CalledProcessError,ValueError,KeyError) as e:results.append({'market':market,'state':'unavailable','reason':type(e).__name__})
report={'date':args.date,'generated_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'method':'top 10 normalized original URL intersection; per-market denominator=min(10,counts)','hangzhou_access':'local SSH/SCP read-only; never imported into review','markets':results}
path=out/'report.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
command(['node','node_modules/wrangler/bin/wrangler.js','r2','object','put','wikifx-signal-archive/comparisons/'+args.date+'.json','--remote','--file',str(path)])
print(json.dumps({'report':str(path),'r2':'comparisons/'+args.date+'.json','markets':[{k:v for k,v in m.items() if k in ['market','state','cloud_count','hangzhou_count','top10_overlap_count','top10_overlap_ratio']} for m in results]},ensure_ascii=False))
