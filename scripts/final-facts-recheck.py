import json,sys,hashlib
from pathlib import Path
sys.path.insert(0,'container');from fact_check import check_article;from material_policy import writing_material
D=Path('artifacts/facts-images-final');rows=json.loads((D/'materials.json').read_text(encoding='utf-8'));summary=[]
for r in rows:
 item=json.loads(r['verified'] or (r['enriched'] if r['source_system']!='wikifx-signal' and r['enriched'] else r['payload_json']));material,_=writing_material(item)
 p=D/'before'/ (r['job_id']+'.json');a=json.loads(p.read_text(encoding='utf-8'));old=a['fact_check'];new=check_article(a['article']['title'],a['article']['meta_description'],a['content'],material);new['review_alert']=new['needs_retry'];a['fact_check_history']=[*a.get('fact_check_history',[]),old];a['fact_check']=new;(D/'after'/p.name).write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8');summary.append({'job_id':r['job_id'],'before':old['count'],'after':new['count'],'findings':new['findings'],'red':new['review_alert']})
(D/'recheck.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print('before',sum(x['before'] for x in summary),'after',sum(x['after'] for x in summary),'red',sum(x['red'] for x in summary))
