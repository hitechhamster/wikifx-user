import sqlite3,json,hashlib,pathlib
root=pathlib.Path('artifacts/migration');c=sqlite3.connect(root/'signal.sqlite3');c.row_factory=sqlite3.Row
def q(v):
 if v is None:return 'NULL'
 if isinstance(v,(int,float)):return str(v)
 return "'"+str(v).replace("'","''")+"'"
def insert(table,obj):return 'INSERT OR IGNORE INTO '+table+'('+','.join(obj)+') VALUES('+','.join(q(v) for v in obj.values())+');'
sql=[];manifest=[];mapping={'global':'MY','india':'SA','pakistan':'SA','indonesia':'ID'}
for table in ['content_items','review_ai_runs','review_ai_calls','review_schedule']:
 for record in c.execute('SELECT * FROM '+table):
  row=dict(record);key=str(row.get('id',row.get('run_date')));data=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(data.encode()).hexdigest()
  sql.append(insert('historical_records',{'source_table':table,'source_id':key,'row_json':data,'sha256':digest}));manifest.append({'table':table,'id':key,'sha256':digest})
  if table=='content_items':
   obj={k:v for k,v in row.items() if k not in ['dedup_key','provenance_json']};obj.update(region_code=mapping[row['market']],source_system='wikifx-signal',selection_scope='historical_archive',revision=1,payload_json=data,available=0);obj['topic_key']=obj.get('topic_key') or key;obj['source']=obj.get('source') or 'historical';sql.append(insert(table,obj))
  elif table=='review_ai_runs':sql.append(insert(table,{'id':'hangzhou-'+key,'run_date':row['run_date'],'region_code':'ALL','status':row['status'],'started_at':row['started_at'],'finished_at':row['finished_at'],'result_json':row['result_json']}))
  elif table=='review_ai_calls':
   obj={k:v for k,v in row.items() if k in ['model','created_at','prompt_tokens','completion_tokens','cache_hit_tokens','estimated_cost_usd','pricing_json','error_code']};obj.update(id='hangzhou-'+key,run_id='hangzhou-'+str(row['run_id']),kind='historical_preselect',region_code=mapping.get(row['market']),usage_json=data);sql.append(insert(table,obj))
(root/'history-import.sql').write_text('\n'.join(sql),encoding='utf8');(root/'row-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True),encoding='utf8')
print(json.dumps({'rows':len(manifest),'statements':len(sql)}))
