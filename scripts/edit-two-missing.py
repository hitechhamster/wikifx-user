import json,sys
from pathlib import Path
sys.path.insert(0,'container');from fact_check import check_article;from material_policy import writing_material
p=Path('artifacts/two-missing-20261027');rows=json.loads((p/'status.json').read_text(encoding='utf-8'));materials=json.loads((p/'materials.json').read_text(encoding='utf-8'))
for r in rows:
 region=r['region_code'];a=json.loads((p/f'{region}-result-before.json').read_text(encoding='utf-8'));payload=json.loads((p/f'{region}-ingest-before.json').read_text(encoding='utf-8'));s=a['content']
 if region=='SA':
  a['article']['title']='Rupee nears 96 as reported FPI outflows reach ₹3.08 lakh crore'
  s=s.replace('Crude oil is under pressure from the ongoing Iran-US war, it said.','The post also links pressure on crude oil to the war involving Iran.')
  start=s.index('<p>A currency weakens');end=s.index('</p>',start)+4
  s=s[:start]+'<p>Foreign portfolio outflows can put pressure on a currency when overseas investors sell local stocks or debt and convert the proceeds into other currencies. Oil imports provide another channel: importers need foreign currency to settle their bills, linking energy costs and demand for dollars.</p>'+s[end:]
  s=s.replace('<h2>Safety reminders</h2>','')
 else:
  s=s.replace('据 Reuters 报道，随着能源价格上涨加剧通胀担忧，金价周五跌至三个月低点，并录得四个多月来最大单周跌幅。','Reuters reported that gold fell to a three-month low on Friday and was heading for its steepest weekly decline in more than four months as higher energy prices fuelled inflation concerns.')
  s=s.replace('The market reopens with the Fed in focus this week, with rate decisions and commentary likely to set the tone for dollar-denominated assets. ','')
  s=s.replace('<h2>What comes next</h2>','')
  s=s.replace('since margin requirements rise as positions move against the holder','since adverse price movements can reduce account equity and trigger margin calls')
 a['content']=s;a['manual_editorial_review']={'changes':'Corrected language contamination and unsupported oil-direction wording; removed unsupported this-week event claim and excess subheading.','by':'wikifx authorized assistant'}
 m=next(x for x in materials if x['job_id']==r['id']);item=json.loads(m['verified'] or (m['enriched'] if m['source_system']!='wikifx-signal' and m['enriched'] else m['payload_json']));material,_=writing_material(item);a['fact_check']=check_article(a['article']['title'],a['article']['meta_description'],s,material);a['fact_check']['review_alert']=a['fact_check']['needs_retry']
 payload['title']=a['article']['title'];payload['content']=s
 (p/f'{region}-result.json').write_text(json.dumps(a,ensure_ascii=False),encoding='utf-8');(p/f'{region}-ingest.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');print(region,'facts',a['fact_check']['count'])

