import {now,today} from './regions';import type {Env} from './types';
export async function prepareTest(env:Env,jobId:string){
 const previous=await env.DB.prepare("SELECT value FROM settings WHERE key='content_hub_test_delivery'").first<any>();if(previous)return previous.value;
 if(!env.CONTENT_INGEST_TOKEN)throw Error('CONTENT_TOKEN_MISSING');
 const job=await env.DB.prepare("SELECT j.*,c.region_code FROM submission_jobs j JOIN content_items c ON c.id=j.item_id WHERE j.id=? AND j.state IN ('ready','dry_run') AND c.available=1").bind(jobId).first<any>();if(!job)throw Error('TEST_DRAFT_NOT_READY');
 const file=await env.ARCHIVE.get(job.payload_key);if(!file)throw Error('TEST_DRAFT_MISSING');const payload=await file.json<any>(),id=crypto.randomUUID(),key=`deliveries/${id}/payload.json`;payload.externalId=job.external_id.startsWith('test-')?job.external_id:'test-'+job.external_id;payload.title='【联调测试】'+String(payload.title).replace(/^【联调测试】/,'');await env.ARCHIVE.put(key,JSON.stringify(payload));
 await env.DB.batch([
  env.DB.prepare("INSERT INTO settings VALUES('content_hub_test_delivery',?)").bind(id),
  env.DB.prepare("INSERT INTO delivery_jobs(id,job_id,item_id,mode,external_id,run_date,reviewed_by,state,payload_key,created_at,updated_at) VALUES(?,?,?,'test',?,?,?,'queued',?,?,?)").bind(id,job.id,job.item_id,payload.externalId,today(),'wikifx',key,now(),now()),
  env.DB.prepare('INSERT OR IGNORE INTO review_picks VALUES(?,?,?,?,?)').bind(job.item_id,job.run_date,job.region_code,'wikifx',now())
 ]);return id;
}
export async function deliver(env:Env,id:string,step:any){
 const d=await step.do('load-delivery',()=>env.DB.prepare('SELECT * FROM delivery_jobs WHERE id=?').bind(id).first<any>());if(!d||d.state==='sent'||d.state==='cancelled')return {skipped:true};
 const correction=await env.DB.prepare('SELECT release_confirmed FROM article_corrections WHERE item_id=?').bind(d.item_id).first<any>();if(correction&&!correction.release_confirmed)throw Error('CORRECTION_ON_HOLD');
 if(!env.CONTENT_INGEST_TOKEN||(d.mode==='live'&&env.SUBMISSION_MODE!=='live'))throw Error('DELIVERY_DISABLED');
 if(d.mode==='test'){const gate=await env.DB.prepare("SELECT value FROM settings WHERE key='content_hub_test_delivery'").first<any>();if(gate?.value!==id)throw Error('TEST_NOT_AUTHORIZED');}
 const file=await env.ARCHIVE.get(d.payload_key);if(!file)throw Error('PAYLOAD_MISSING');const payload=await file.json<any>();
 for(let attempt=d.attempts;attempt<4;attempt++){
  if(attempt>d.attempts)await step.sleep(`delivery-retry-${attempt}`,`${30*attempt} seconds`);
  const result=await step.do(`delivery-http-${attempt}`,{retries:{limit:0,delay:'1 second'}},async()=>{
   const paused=await env.DB.prepare("SELECT value FROM settings WHERE key='ingest_paused'").first<any>();if(paused?.value==='1')return {permanent:true,error:'TOKEN_CHECK_REQUIRED'};
   const claim=await env.COORDINATOR.get(env.COORDINATOR.idFromName('hub')).fetch('https://internal/claim-delivery',{method:'POST',body:JSON.stringify({id,attempt})});const allowed=await claim.json<any>();if(!allowed.ok)return {cancelled:true};
   try{
    const r=await fetch('https://editor.chouai.cc.cd/api/articles/ingest',{method:'POST',redirect:'manual',headers:{'Content-Type':'application/json','X-Ingest-Token':env.CONTENT_INGEST_TOKEN!},body:JSON.stringify(payload),signal:AbortSignal.timeout(90000)});const b=await r.json<any>().catch(()=>({}));
    if([200,201].includes(r.status)&&b.data?.id)return {success:true,status:r.status,id:String(b.data.id)};
    if(r.status===401)await env.DB.prepare("INSERT INTO settings VALUES('ingest_paused','1') ON CONFLICT(key) DO UPDATE SET value='1'").run();
    let error=typeof b.error==='string'?b.error:JSON.stringify(b.error||`CONTENT_HUB_HTTP_${r.status}`);for(const secret of [env.CONTENT_INGEST_TOKEN,env.DEEPSEEK_API_KEY])if(secret)error=error.split(secret).join('[redacted]');return {status:r.status,permanent:r.status<500,error:error.slice(0,500)};
   }catch{return {permanent:false,error:'CONTENT_HUB_TIMEOUT_OR_NETWORK'};}
  });
  if(result.cancelled)return {cancelled:true};
  if(result.success){await step.do('delivery-success',async()=>{
   const sql=[env.DB.prepare("UPDATE delivery_jobs SET state='sent',http_status=?,hub_id=?,updated_at=? WHERE id=?").bind(result.status,result.id,now(),id)];
   if(d.mode==='live'){sql.push(env.DB.prepare("UPDATE submission_jobs SET state='sent',hub_id=?,updated_at=? WHERE id=?").bind(result.id,now(),d.job_id));sql.push(env.DB.prepare("UPDATE content_items SET status='published',review_state='sent',published_at=?,publish_result=? WHERE id=?").bind(now(),JSON.stringify({id:result.id,http_status:result.status}),d.item_id));sql.push(env.DB.prepare('DELETE FROM review_picks WHERE item_id=?').bind(d.item_id));}
   await env.DB.batch(sql);await env.ARCHIVE.put(`deliveries/${id}/receipt.json`,JSON.stringify({http_status:result.status,id:result.id,externalId:d.external_id,mode:d.mode,at:now()}));return true;
  });return {http_status:result.status,id:result.id,url:`https://editor.chouai.cc.cd/?articleId=${result.id}`};}
  if(result.permanent||attempt===3){await step.do('delivery-failure',()=>env.DB.batch([env.DB.prepare("UPDATE delivery_jobs SET state='failed',http_status=?,error=?,updated_at=? WHERE id=?").bind(result.status||null,result.error,now(),id),env.DB.prepare("UPDATE content_items SET publish_result=?,review_state=CASE WHEN ?='live' THEN 'failed' ELSE review_state END WHERE id=?").bind(result.error,d.mode,d.item_id)]).then(()=>true));return {failed:true,http_status:result.status,error:result.error};}
 }
 return {failed:true,error:'RETRIES_EXHAUSTED'};
}
