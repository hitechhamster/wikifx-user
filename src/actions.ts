import {attachImage,currentImage} from './images';
import {fail,json,hash} from './protocol';import {today,now,regions} from './regions';import type {Env} from './types';
export async function defaults(env:Env){}

async function rate(req:Request,env:Env){const ip=await hash(req.headers.get('CF-Connecting-IP')||'local'),second=Math.floor(Date.now()/1000);await env.DB.prepare('INSERT INTO rate_limits VALUES(?,?,1) ON CONFLICT(ip_hash,minute) DO UPDATE SET count=count+1').bind(ip,second).run();const n=await env.DB.prepare('SELECT sum(count) n FROM rate_limits WHERE ip_hash=? AND minute>?').bind(ip,second-60).first<any>();if(n.n>10)fail(429,'RATE_LIMITED','同一IP每分钟最多10次送稿操作');}
export async function reviewAction(req:Request,env:Env){
 const action=new URL(req.url).pathname.split('/').pop(),b=await req.json<any>(),date=today(),at=now(),who=typeof b.reviewed_by==='string'?b.reviewed_by.trim():'';
 if(!who||who.length>80)fail(422,'REVIEWER_REQUIRED','请填写审核人');
 if(action==='pick'){
  const changes=Array.isArray(b.changes)?b.changes:[{id:b.id,picked:b.picked}];
  if(!changes.length||changes.length>100||changes.some((x:any)=>typeof x.id!=='string'||typeof x.picked!=='boolean')||new Set(changes.map((x:any)=>x.id)).size!==changes.length)fail(422,'INVALID_PICKS','勾选数据无效');
  const sql:D1PreparedStatement[]=[];
  for(const x of changes){const row=await env.DB.prepare("SELECT region_code FROM content_items WHERE id=? AND run_date=? AND available=1 AND review_state='candidate' AND status!='legacy_hot'").bind(x.id,date).first<any>();if(!row)fail(409,'NOT_CANDIDATE','条目状态已变更，无法保存勾选');
   sql.push(env.DB.prepare('INSERT INTO review_pick_preferences VALUES(?,?,?) ON CONFLICT(item_id) DO UPDATE SET picked=excluded.picked,updated_at=excluded.updated_at').bind(x.id,x.picked?1:0,at),x.picked?env.DB.prepare('INSERT INTO review_picks VALUES(?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET reviewed_by=excluded.reviewed_by,created_at=excluded.created_at').bind(x.id,date,row.region_code,who,at):env.DB.prepare('DELETE FROM review_picks WHERE item_id=?').bind(x.id));
  }await env.DB.batch(sql);return json({ok:true});
 }
 if(['approve','back'].includes(action||'')){
  const row=await env.DB.prepare('SELECT c.review_state,j.* FROM content_items c JOIN submission_jobs j ON j.item_id=c.id WHERE c.id=?').bind(b.id).first<any>();if(!row)fail(404,'NOT_FOUND','稿件不存在');
  if(!['draft','approved'].includes(row.review_state))fail(409,'INVALID_STATE','只有待审或已通过稿件可以操作');
  if(action==='back'&&await env.DB.prepare('SELECT item_id FROM article_corrections WHERE item_id=?').bind(b.id).first())fail(409,'CORRECTION_REVIEW_ONLY','修正版保留在审稿页，不能放回选题');
  if(action==='approve'){
   if(!row.payload_key||!['draft','approved'].includes(row.state))fail(409,'DRAFT_NOT_READY','稿件尚未生成完成');const approved=b.approved!==false;
   await env.DB.batch([env.DB.prepare('UPDATE content_items SET review_state=?,reviewed_by=?,reviewed_at=? WHERE id=?').bind(approved?'approved':'draft',who,at,b.id),env.DB.prepare('UPDATE submission_jobs SET state=?,approved_generation_id=?,approved_by=?,approved_at=?,updated_at=? WHERE id=?').bind(approved?'approved':'draft',approved?(row.generation_request_id||row.id):null,approved?who:null,approved?at:null,at,row.id),env.DB.prepare('INSERT INTO audit_events VALUES(?,?,?,?,?)').bind(crypto.randomUUID(),approved?'approve':'unapprove',who,JSON.stringify({item_id:b.id,generation_id:row.generation_request_id||row.id}),at)]);
  }else await env.DB.batch([env.DB.prepare("UPDATE content_items SET review_state='candidate',status='candidate',article_path=NULL WHERE id=?").bind(b.id),env.DB.prepare("UPDATE submission_jobs SET state='returned',payload_key=NULL,article_key=NULL,approved_generation_id=NULL,approved_by=NULL,approved_at=NULL,error=NULL WHERE id=?").bind(row.id),env.DB.prepare('DELETE FROM review_picks WHERE item_id=?').bind(b.id),env.DB.prepare('INSERT INTO review_pick_preferences VALUES(?,0,?) ON CONFLICT(item_id) DO UPDATE SET picked=0,updated_at=excluded.updated_at').bind(b.id,at)]);return json({ok:true});
 }
 if(!['generate','regenerate','submit','retry'].includes(action||''))fail(404,'NOT_FOUND','接口不存在');
 const ids=action==='retry'?[b.id]:b.ids;if(!Array.isArray(ids)||!ids.length||ids.length>100||ids.some((x:any)=>typeof x!=='string'))fail(422,'INVALID_IDS','请选择条目');
 let retryDelivery:any=null;if(action==='retry'){retryDelivery=await env.DB.prepare("SELECT * FROM delivery_jobs WHERE item_id=? AND mode='live' AND state='failed'").bind(b.id).first<any>();}
 const sending=action==='submit'||!!retryDelivery,regenerate=action==='regenerate'||action==='retry';
 if(sending){if(env.SUBMISSION_MODE!=='live'||!env.CONTENT_INGEST_TOKEN)fail(409,'LIVE_NOT_ENABLED','正式送稿未开启');const paused=await env.DB.prepare("SELECT value FROM settings WHERE key='ingest_paused'").first<any>();if(paused?.value==='1')fail(409,'TOKEN_CHECK_REQUIRED','请检查Content Hub Token后再重试');await rate(req,env);}
 const rows:any[]=[];
 for(const id of [...new Set(ids)]){
  const row=await env.DB.prepare('SELECT c.*,j.id job_id,j.state job_state,j.payload_key,j.generation_request_id,j.approved_generation_id,k.external_id correction_external_id,k.release_confirmed correction_released FROM content_items c LEFT JOIN submission_jobs j ON j.item_id=c.id LEFT JOIN article_corrections k ON k.item_id=c.id WHERE c.id=? AND (c.run_date=? OR ?=\'regenerate\' OR c.review_state=\'approved\') AND c.available=1 AND c.status!=\'legacy_hot\'').bind(id,date,action).first<any>();if(!row)fail(409,'UNAVAILABLE','条目不可用');
  const d=await env.DB.prepare("SELECT * FROM delivery_jobs WHERE item_id=? AND mode='live'").bind(id).first<any>();
  if(sending){
   if(row.correction_external_id&&!row.correction_released)fail(409,'CORRECTION_ON_HOLD','修正版暂不送出，请先确认原稿已由编辑删除');
   if(retryDelivery){if(row.review_state!=='failed'||row.job_state!=='approved'||!row.approved_generation_id)fail(409,'NOT_APPROVED','失败稿件没有有效的审批记录');row.delivery=retryDelivery;}
   else if(row.review_state!=='approved'||row.job_state!=='approved'||row.approved_generation_id!==(row.generation_request_id||row.job_id))fail(409,'NOT_APPROVED','只有已通过的当前版本稿件可以送出');
   const cover=await currentImage(env,row.job_id);if(cover&&['queued','creating','running'].includes(cover.state))fail(409,'IMAGE_PENDING','头图生成中，请完成或失败后再送稿');
    if(!row.payload_key)fail(409,'NO_DRAFT','稿件文件不可用');if(d&&!retryDelivery)fail(409,'ALREADY_SUBMITTED','稿件已有送稿记录，请使用重试');
  }else{
   if(d)fail(409,'DELIVERY_EXISTS','稿件已有送稿记录');
   if(regenerate){if(!['draft','approved','failed'].includes(row.review_state))fail(409,'INVALID_STATE','当前状态不能重新生成');}
   else if(row.review_state!=='candidate'||!await env.DB.prepare('SELECT item_id FROM review_picks WHERE item_id=?').bind(id).first())fail(409,'NOT_PICKED','请在选题页勾选未生成的条目');
  }rows.push(row);
 }
 const used=await env.DB.prepare(sending?"SELECT count(*) n FROM delivery_jobs WHERE run_date=? AND state!='cancelled'":'SELECT count(*) n FROM generation_requests WHERE run_date=?').bind(date).first<any>();const limit=Number(sending?env.DAILY_SUBMISSION_LIMIT:env.DAILY_GENERATION_LIMIT||100);if(used.n+(retryDelivery?0:rows.length)>limit)fail(409,'DAILY_LIMIT',`${sending?'送稿':'生成'}每日上限${limit}篇`);
 const sql:D1PreparedStatement[]=[],jobs=[];
 for(const row of rows){
  if(sending){
   const id=row.delivery?.id||crypto.randomUUID(),external=row.delivery?.external_id||row.correction_external_id||`signal-${row.region_code}-${date}-${row.id.slice(0,12)}`,key=row.delivery?.payload_key||`deliveries/${id}/payload.json`;
   if(!retryDelivery){const file=await env.ARCHIVE.get(row.payload_key);if(!file)fail(409,'DRAFT_MISSING','稿件文件不可用');const payload=await attachImage(env,row.job_id,await file!.json<any>());payload.externalId=external;payload.title=String(payload.title).replace(/^【联调测试】/,'');await env.ARCHIVE.put(key,JSON.stringify(payload));}
   sql.push(env.DB.prepare("INSERT INTO delivery_jobs(id,job_id,item_id,mode,external_id,run_date,reviewed_by,state,payload_key,created_at,updated_at) VALUES(?,?,?,'live',?,?,?,'queued',?,?,?) ON CONFLICT(id) DO UPDATE SET state='queued',attempts=0,error=NULL,http_status=NULL,updated_at=excluded.updated_at").bind(id,row.job_id,row.id,external,date,who,key,at,at));
   sql.push(env.DB.prepare("INSERT INTO task_outbox VALUES(?,'deliver',?,'pending',?)").bind(crypto.randomUUID(),JSON.stringify({delivery:id}),at));
   sql.push(env.DB.prepare("UPDATE content_items SET review_state='sending',reviewed_by=?,queued_at=? WHERE id=?").bind(who,at,row.id));jobs.push(id);
   if(retryDelivery)sql.push(env.DB.prepare('INSERT INTO audit_events VALUES(?,?,?,?,?)').bind(crypto.randomUUID(),'manual_delivery_retry',who,JSON.stringify({id,previous_attempts:retryDelivery.attempts,previous_error:retryDelivery.error,externalId:external}),at));
  }else{
   const id=row.job_id||crypto.randomUUID(),requestId=crypto.randomUUID();jobs.push(id);
   sql.push(env.DB.prepare("INSERT INTO submission_jobs(id,item_id,external_id,run_date,reviewed_by,state,snapshot_json,dry_run,created_at,updated_at) VALUES(?,?,?,?,?,'queued',?,1,?,?) ON CONFLICT(id) DO UPDATE SET state='queued',error=NULL,snapshot_json=excluded.snapshot_json,payload_key=NULL,approved_generation_id=NULL,approved_by=NULL,approved_at=NULL,updated_at=excluded.updated_at").bind(id,row.id,row.correction_external_id||`signal-${row.region_code}-${date}-${row.id.slice(0,12)}`,date,who,JSON.stringify(row),at,at));
   sql.push(env.DB.prepare('INSERT INTO generation_requests VALUES(?,?,?,?)').bind(requestId,id,date,at),env.DB.prepare("INSERT INTO task_outbox VALUES(?,'article',?,'pending',?)").bind(requestId,JSON.stringify({job:id}),at),env.DB.prepare('UPDATE submission_jobs SET generation_request_id=? WHERE id=?').bind(requestId,id),env.DB.prepare("UPDATE content_items SET review_state='generating',status='selected',reviewed_by=?,reviewed_at=? WHERE id=?").bind(who,at,row.id),env.DB.prepare('DELETE FROM review_picks WHERE item_id=?').bind(row.id));
  }
 }
 if(sql.length)await env.DB.batch(sql);return json({ok:true,jobs},202);
}
