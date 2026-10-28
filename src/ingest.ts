import {batchSchema,canonical,hash,fail,json} from './protocol';
import {now} from './regions';
import type {Env} from './types';
export async function ingest(req:Request,env:Env){
 const credential=req.headers.get('Authorization')?.replace(/^Bearer /,'');
 if(!credential||!(await Promise.all([env.SIGNAL_INGEST_TOKEN,env.RADAR_INGEST_TOKEN].map(async token=>!!token&&await hash(token)===await hash(credential)))).some(Boolean))fail(401,'UNAUTHORIZED','接收凭据无效');
 const raw=await req.text();if(new TextEncoder().encode(raw).length>5*1024*1024)fail(413,'PAYLOAD_TOO_LARGE','单页不能超过 5 MiB');
 let input:unknown;try{input=JSON.parse(raw);}catch{fail(400,'INVALID_FIELD','JSON 无效');}
 const parsed=batchSchema.safeParse(input);if(!parsed.success)return json({code:'INVALID_FIELD',message:'批次校验失败',errors:parsed.error.issues.map(x=>({field:x.path.join('.'),reason:x.message}))},422);
 const b=parsed.data,key=`${b.batch_id}:${b.page_no}`;
 if(req.headers.get('Idempotency-Key')!==key)fail(400,'INVALID_FIELD','Idempotency-Key 与页号不符');
 const expected=b.source_system==='wikifx-signal'?env.SIGNAL_INGEST_TOKEN:env.RADAR_INGEST_TOKEN;
 const supplied=req.headers.get('Authorization')?.replace(/^Bearer /,'');
 if(!expected||!supplied||await hash(expected)!==await hash(supplied))fail(401,'UNAUTHORIZED','接收凭据无效');
 // Hash the complete JSON, including unknown fields: a changed payload is never silently accepted.
 const digest=await hash(canonical(input));
 const old=await env.DB.prepare('SELECT * FROM ingest_pages WHERE idempotency_key=?').bind(key).first<any>();
 if(old){if(old.payload_hash!==digest)fail(409,'IDEMPOTENCY_CONFLICT','同一幂等键的报文不同');const receipt=JSON.parse(old.receipt_json);receipt.data.duplicate_request=true;return json(receipt,200);}
 const stream=[b.source_system,b.data_date,b.region_code,b.selection_scope].join('|');
 const latest=await env.DB.prepare('SELECT * FROM ingest_batches WHERE stream_key=? ORDER BY revision DESC LIMIT 1').bind(stream).first<any>();
 if(latest&&latest.revision>b.revision)fail(409,'STALE_REVISION','旧版本不能覆盖新版本');
 if(latest&&latest.revision===b.revision&&latest.batch_id!==b.batch_id)fail(409,'REVISION_CONFLICT','该版本已属于另一个批次');
 const {items,page_no,...metadata}=b,metaHash=await hash(canonical(metadata));
 const batch=await env.DB.prepare('SELECT * FROM ingest_batches WHERE batch_id=?').bind(b.batch_id).first<any>();
 if(batch&&batch.metadata_hash!==metaHash)fail(409,'REVISION_CONFLICT','分页元数据不一致');
 const present=await env.DB.prepare('SELECT topic_id FROM batch_items WHERE batch_id=?').bind(b.batch_id).all<any>();
 const seen=new Set(present.results.map(r=>r.topic_id));
 if(b.items.some(i=>seen.has(i.topic_id)))fail(409,'REVISION_CONFLICT','topic_id 跨页重复');
 const pages=await env.DB.prepare('SELECT count(*) n FROM ingest_pages WHERE batch_id=?').bind(b.batch_id).first<any>();
 const complete=pages.n+1===b.page_count;
 if(b.total_items!==null&&(seen.size+b.items.length>b.total_items||complete&&seen.size+b.items.length!==b.total_items))fail(422,'INVALID_FIELD','total_items 与实际去重条数不一致');
 const at=now(),r2key=`intake/${b.source_system}/${b.data_date}/${b.batch_id}/${b.page_no}-${digest}.json`;
 await env.ARCHIVE.put(r2key,raw,{httpMetadata:{contentType:'application/json'}});
 const receipt={code:'OK',message:'热点批次已保存',data:{batch_id:b.batch_id,page_no:b.page_no,accepted_count:b.items.length,duplicate_request:false,receipt_id:crypto.randomUUID(),stored_at:at}};
 const sql:D1PreparedStatement[]=[];
 if(!batch)sql.push(env.DB.prepare('INSERT INTO ingest_batches(batch_id,stream_key,revision,metadata_hash,payload_json,page_count,total_items,created_at) VALUES(?,?,?,?,?,?,?,?)').bind(b.batch_id,stream,b.revision,metaHash,JSON.stringify(metadata),b.page_count,b.total_items,at));
 for(const item of b.items){
  const id=await hash(`${stream}|${item.topic_id}`);
  sql.push(env.DB.prepare('INSERT INTO batch_items VALUES(?,?,?,?)').bind(b.batch_id,item.topic_id,id,JSON.stringify(item)));
  sql.push(env.DB.prepare('INSERT INTO content_versions VALUES(?,?,?,?)').bind(id,b.revision,JSON.stringify(item),b.batch_id));
 }
 sql.push(env.DB.prepare('INSERT INTO ingest_pages VALUES(?,?,?,?,?,?)').bind(key,b.batch_id,b.page_no,digest,JSON.stringify(receipt),r2key));
 if(complete){
  // Activate the complete snapshot only; earlier pages remain durable staging rows.
  const all=[...(await env.DB.prepare('SELECT item_id,payload_json FROM batch_items WHERE batch_id=?').bind(b.batch_id).all<any>()).results,...await Promise.all(b.items.map(async i=>({item_id:await hash(`${stream}|${i.topic_id}`),payload_json:JSON.stringify(i)})))];
  for(const row of all){
   const incoming=JSON.parse(row.payload_json),prior=await env.DB.prepare('SELECT * FROM content_items WHERE id=?').bind(row.item_id).first<any>();
   let effective={...incoming};
   if(prior){const p=JSON.parse(prior.payload_json);if(p.content_status==='full'&&incoming.content_status!=='full'){for(const k of ['content','content_status','content_error','content_fetched_at'])effective[k]=p[k];}if(p.summary&&!incoming.summary){effective.summary=p.summary;effective.summary_origin=p.summary_origin;}}
   sql.push(env.DB.prepare(`INSERT INTO content_items(id,region_code,source_system,run_date,selection_scope,topic_key,title,summary,url,source,category,lead_created_at,revision,payload_json,available) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
    ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary,url=excluded.url,source=excluded.source,category=excluded.category,revision=excluded.revision,payload_json=excluded.payload_json,available=1 WHERE content_items.review_state='candidate'`)
    .bind(row.item_id,b.region_code,b.source_system,b.data_date,b.selection_scope,incoming.topic_id,effective.title,effective.summary,effective.url,effective.source_name,effective.category??null,effective.published_at,b.revision,JSON.stringify(effective)));
  }
  sql.push(env.DB.prepare("UPDATE ingest_batches SET status='delivered' WHERE batch_id=?").bind(b.batch_id));
  if(['completed','partial'].includes(b.collection_status)&&b.total_items){sql.push(env.DB.prepare('INSERT OR IGNORE INTO task_outbox VALUES(?,?,?,\'pending\',?)').bind(`preselect-${b.batch_id}`,'preselect',JSON.stringify({date:b.data_date,region:b.region_code}),at));}
  if(b.source_system==='wikifx-hotspot-radar'&&b.total_items)sql.push(env.DB.prepare("INSERT OR IGNORE INTO task_outbox VALUES(?,?,?,'pending',?)").bind('supplement-'+b.batch_id,'radar-region',JSON.stringify({date:b.data_date,region:b.region_code}),at));
 }
 await env.DB.batch(sql);
 return json(receipt,201);
}
