import hashlib,uuid,datetime,re
MAP={'global':'MY','india':'SA','pakistan':'SA','indonesia':'ID'}
NAMES={'MY':'马来西亚','SA':'南亚','ID':'印度尼西亚'}
def iso(value):
 if not value:return None
 d=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
 if d.tzinfo is None:d=d.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
 return d.isoformat()
def pages(reports,date):
 groups={};metadata=[]
 for market,report in reports.items():
  region=MAP[market];g=groups.setdefault(region,{'items':[],'generated':iso(report['generated_at'])})
  for t in report['topics']:
   l=t['lead'];topic=market+'-'+hashlib.sha256(l['url'].encode()).hexdigest()[:32];text=l.get('text','');summary=text[:2000] or None
   item=dict(topic_id=topic,title=(t.get('label') or text)[:500],content=None,content_format='text/plain',content_status='unavailable',content_error={'code':'not_fetched','message':'采集日报只保留主来源文本摘录和证据'},content_fetched_at=None,summary=summary,summary_origin='excerpt' if summary else 'unavailable',url=l['url'],source_name=str(l.get('news_source') or l.get('author_name') or l.get('author') or l.get('platform'))[:200],language='id' if market=='indonesia' else 'en',published_at=iso(l.get('created_at')),discovered_at=iso(report['generated_at']),category=t.get('category',{}).get('id'),sources=[dict(source_name=str(s.get('source') or 'Evidence')[:200],title=str(s.get('title',''))[:500],url=s['url'],summary=str(s.get('snippet',''))[:2000] or None) for s in t.get('evidence',{}).get('sources',[]) if s.get('relevant') and s.get('url')])
   g['items'].append(item);metadata.append(dict(market=market,region=region,topic_id=topic,heat=t.get('topic_score'),opportunity_score=t.get('opportunity',{}).get('score'),engagement_total=t.get('stats',{}).get('engagement_total',{})))
 result=[]
 for region,g in groups.items():
  count=max(1,(len(g['items'])+49)//50);batch=str(uuid.uuid5(uuid.NAMESPACE_URL,'wikifx-cloud-'+date+'-'+region))
  for page in range(count):result.append(dict(schema_version='1.0',source_system='wikifx-signal',batch_id=batch,snapshot_id='signal-'+region+'-'+date+'-cloud',data_date=date,timezone='Asia/Shanghai',region_code=region,region_name=NAMES[region],selection_scope='candidate_topics',revision=1,collection_status='completed' if region!='SA' or all(m in reports for m in ['india','pakistan']) else 'partial',report_origin='scheduled',report_generated_at=g['generated'],window_hours=24,page_no=page+1,page_count=count,total_items=len(g['items']),items=g['items'][page*50:(page+1)*50],warnings=[]))
 for region in NAMES:
  if region not in groups:result.append(dict(schema_version='1.0',source_system='wikifx-signal',batch_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'wikifx-cloud-'+date+'-'+region)),snapshot_id='signal-'+region+'-'+date+'-cloud',data_date=date,timezone='Asia/Shanghai',region_code=region,region_name=NAMES[region],selection_scope='candidate_topics',revision=1,collection_status='failed',report_origin=None,report_generated_at=None,window_hours=24,page_no=1,page_count=1,total_items=None,items=[],warnings=['COLLECTOR_NO_REPORT']))
 return {'date':date,'pages':result,'metadata':metadata}
