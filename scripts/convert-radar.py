"""One-time offline conversion. Never reads tokens or calls collection APIs."""
import argparse,json,html,re,uuid,hashlib,difflib
from pathlib import Path
from html.parser import HTMLParser
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[]
 def handle_data(self,data):self.parts.append(data)
def clean(value,title):
 if not value:return None
 parser=Text();parser.feed(value);text=' '.join(html.unescape(' '.join(parser.parts)).split())
 norm=lambda x:re.sub(r'[^\w]','',x.lower())
 a,b=norm(text),norm(title)
 return None if not a or a in b or b in a or difflib.SequenceMatcher(None,a,b).ratio()>=.86 else text[:2000]
def convert(data):
 assert data['export_format']=='wikifx-daily-candidates-export/v1'
 names={'KR':'韩国','VN':'越南','TH':'泰国','ID':'印度尼西亚','BR':'巴西','AR':'中东／阿拉伯语区','LA':'拉美／西班牙语区','JP':'日本','TW':'台湾','SA':'南亚','MY':'马来西亚','AF':'非洲','CN':'中国／简体中文市场'}
 pages=[];counts={};cleared=0
 for region in data['regions']:
  code=region['region_code'];items=[]
  for original in region['items']:
   x={k:original.get(k) for k in ['topic_id','title','content','content_format','content_status','content_error','content_fetched_at','url','source_name','language','published_at','discovered_at','category','article_type','ranking']}
   x['summary']=clean(original.get('summary'),x['title']);x['summary_origin']='source' if x['summary'] else 'unavailable'
   if x['published_at'] and re.fullmatch(r'\d{2} Agt \d{4}',x['published_at']):
    day,_,year=x['published_at'].split();x['published_at']=f'{year}-08-{day}T00:00:00+07:00'
   cleared+=bool(original.get('summary') and not x['summary'])
   x['sources']=[{k:(clean(s.get('summary'),s['title']) if k=='summary' else s[k]) for k in ['source_name','title','url','summary']} for s in original.get('sources',[])[:100]]
   items.append(x)
  counts[code]=len(items);batch=str(uuid.uuid5(uuid.NAMESPACE_URL,f"wikifx-radar-export:{data['data_date']}:{code}:revision1"));n=max(1,(len(items)+49)//50)
  for i in range(n):pages.append(dict(schema_version='1.0',source_system='wikifx-hotspot-radar',batch_id=batch,snapshot_id=f"radar-export/{data['data_date']}/{code}",data_date=data['data_date'],timezone='Asia/Shanghai',region_code=code,region_name=names[code],selection_scope='candidate_topics',revision=1,collection_status='completed',report_origin=region['daily_collection']['origin'],report_generated_at=region['report_generated_at'],window_hours=24,page_no=i+1,page_count=n,total_items=len(items),items=items[i*50:(i+1)*50],warnings=[]))
 assert sum(counts.values())==data['statistics']['total_candidates']==227
 return dict(date=data['data_date'],pages=pages,counts=counts,summary_cleared=cleared)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('input');parser.add_argument('output');args=parser.parse_args();raw=Path(args.input).read_bytes();result=convert(json.loads(raw));result['source_sha256']=hashlib.sha256(raw).hexdigest();Path(args.output).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='pages'},ensure_ascii=False))
