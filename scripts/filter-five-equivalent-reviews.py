import json,sys
from pathlib import Path
sys.path.insert(0,'container');from ai_audit import equivalent_date_issue,normal_attribution_issue
D=Path('artifacts/facts-images-final');targets=json.loads(Path('artifacts/facts-images/rewrite-scope.json').read_text(encoding='utf-8'));materials={x['job_id']:x for x in json.loads((D/'materials.json').read_text(encoding='utf-8'))};out=[]
from material_policy import writing_material
for t in targets:
 p=D/'after'/(t['job_id']+'.json');a=json.loads(p.read_text(encoding='utf-8'));r=materials[t['job_id']];item=json.loads(r['verified'] or (r['enriched'] if r['source_system']!='wikifx-signal' and r['enriched'] else r['payload_json']));m,_=writing_material(item);v=a['ai_review'];ignored=[i for i in v['issues'] if equivalent_date_issue(i,m) or normal_attribution_issue(i)]
 if ignored:
  a['ai_review_history']=[*a.get('ai_review_history',[]),v];a['ai_review']={**v,'issues':[i for i in v['issues'] if i not in ignored],'count':v['count']-len(ignored),'equivalent_issues_ignored':v.get('equivalent_issues_ignored',0)+len(ignored)}
 p.write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8');out.append({'job_id':t['job_id'],'region':t['region_code'],'removed':ignored,'count':a['ai_review']['count']})
Path('artifacts/facts-images/equivalent-review-adjustments.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print([(x['region'],len(x['removed']),x['count']) for x in out])
