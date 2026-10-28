import json,sys,re
from pathlib import Path
sys.path.insert(0,'container');from fact_check import check_article,plain
mats=json.loads(Path('artifacts/claude-facts/old-audit.json').read_text(encoding='utf-8'))
results=[]
for hub,region in [('214','VN'),('217','ID'),('219','BR')]:
 a=json.loads(Path('artifacts/sent-corrections/bases/'+hub+'.json').read_text(encoding='utf-8'))
 m=next(x['material'] for x in mats if x['region']==region and (hub!='217' or x['job_id']=='973d7134-6c01-4296-a32f-147abf134d2c'))
 body=re.split(r'<p><strong>(?:Sources|Sumber|出典|출처|信息来源)</strong></p>',a['content'])[0];c=check_article(a['title'],a['summary'],body,m);results.append({'original_hub_id':hub,'article':a,'material':m,'check':c})
 print(hub,'flags',[(f['text'],f['kind']) for f in c['findings']], 'derived',[(f['text'],f['formula']) for f in c['derived']])
Path('artifacts/rerun-v6/historical-case-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
