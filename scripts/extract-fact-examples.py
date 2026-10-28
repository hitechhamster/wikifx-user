import json,re,sys
from pathlib import Path
sys.path.insert(0,'container');from fact_check import plain
rows=json.loads(Path('artifacts/claude-facts/old-audit.json').read_text(encoding='utf-8'));old=json.loads(Path('artifacts/claude-facts/before.json').read_text(encoding='utf-8'));out=[]
for r in rows:
 a=next(x['article'] for x in old if x['job_id']==r['job_id']);evidence=json.dumps(r['material'],ensure_ascii=False)
 for f in r['check']['findings']:
  if f['text'] in ('Bank Negara Malaysia','Ministerio de Economía','Finance Minister Nirmala Sitharaman','金融庁','12','二七〇萬'):
   body=plain(a['content']) if f['field']=='content' else a['summary'] if f['field']=='summary' else a['title'];start=max(0,f['start']-150);end=min(len(body),f['end']+180)
   out.append({'region':r['region'],'job_id':r['job_id'],'term':f['text'],'quote':body[start:end],'material':r['material']})
Path('artifacts/flash-facts/old-examples.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
for x in out:print(x['region'],x['term'],x['quote'])
