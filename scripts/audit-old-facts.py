import json,sys,re
from pathlib import Path
sys.path.insert(0,'container')
from fact_check import check_article
from material_policy import writing_material
rows=json.loads(Path('artifacts/claude-facts/materials.json').read_text(encoding='utf-8'))[0]['results'];old=json.loads(Path('artifacts/claude-facts/before.json').read_text(encoding='utf-8'));out=[]
for x in old:
 r=next(y for y in rows if y['job_id']==x['job_id']);raw=r['verified_json'] or r['enriched_json'] or r['payload_json'];item=json.loads(raw);material,_=writing_material(item);a=x['article'];check=check_article(a['title'],a['summary'],re.split(r'<p><strong>(?:Sources|Sumber|出典|출처|信息来源)</strong></p>',a['content'])[0],material);out.append({'job_id':x['job_id'],'region':x['region_code'],'title':a['title'],'check':check,'material':material})
Path('artifacts/claude-facts/old-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps([{'region':x['region'],'flags':x['check']['count'],'examples':[f['text'] for f in x['check']['findings'][:8]]} for x in out],ensure_ascii=False))
