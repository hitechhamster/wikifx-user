import {enqueueImage,currentImage,imageView,retryImage} from './images';
import {DurableObject} from 'cloudflare:workers';
import {ingest} from './ingest';
import {dashboard,candidateDetails} from './review';
import {reviewAction,defaults} from './actions';
import {prepareTest} from './delivery';
import {HttpError,json,fail,hash} from './protocol';
import {now,today} from './regions';
import type {Env} from './types';
export {Pipeline,ArticleContainer} from './pipeline';
export {CollectorContainer} from './collector';
export class Coordinator extends DurableObject<Env>{
 async fetch(req:Request):Promise<Response>{
  return this.ctx.blockConcurrencyWhile(async()=>{
   try{
    const path=new URL(req.url).pathname;
    if(path==='/prepare-test'){const b=await req.json<any>();return json({id:await prepareTest(this.env,b.job)});}
    if(path==='/claim-delivery'){const b=await req.json<any>();const r=await this.env.DB.prepare("UPDATE delivery_jobs SET state='sending',attempts=?,updated_at=? WHERE id=? AND state IN ('queued','sending') AND (mode='test' OR EXISTS(SELECT 1 FROM content_items c JOIN submission_jobs j ON j.item_id=c.id WHERE c.id=delivery_jobs.item_id AND c.review_state='sending' AND j.state='approved' AND j.approved_generation_id=COALESCE(j.generation_request_id,j.id)))").bind(b.attempt+1,now(),b.id).run();if(!r.meta.changes)await this.env.DB.prepare("UPDATE delivery_jobs SET state='cancelled' WHERE id=? AND state='queued'").bind(b.id).run();return json({ok:!!r.meta.changes});}
    if(path==='/api/review/image') {const b=await req.json<any>();if(typeof b.job!=='string')return json({error:'JOB_REQUIRED'},400);const active=await currentImage(this.env,b.job);if(active?.state==='untested'&&!b.pilot)return json({message:'头图等待语言测试'},409);if(active?.state==='unsupported'&&!b.pilot)return json({message:'头图暂不支持该语言'},409);if(active&&['queued','creating','running'].includes(active.state))return json(imageView(active),202);if(b.retry&&active?.state==='failed')return json(imageView(await retryImage(this.env,active)),202);return json(imageView(await enqueueImage(this.env,b.job,b.pilot?'pilot:'+crypto.randomUUID():crypto.randomUUID())),202);}
    if(path==='/dispatch'){await dispatchQueue(this.env);return json({ok:true});}
    if(path==='/api/v1/hotspots/daily-batches')return await ingest(req,new URL(req.url).hostname==='hotspots-test.wikifxusers.com'?{...this.env,DB:this.env.TEST_DB}:this.env);
    if(path==='/commit-ai'){
     const b=await req.json<any>();
     const snapshot=(await this.env.DB.prepare("SELECT batch_id FROM ingest_batches WHERE status='delivered' AND json_extract(payload_json,'$.data_date')=? AND json_extract(payload_json,'$.region_code')=? ORDER BY batch_id").bind(b.date,b.region).all<any>()).results.map(x=>x.batch_id).join('|');
     if(b.result.policy!=='regional-arrival-v3'||snapshot!==b.result.snapshot){await this.env.DB.prepare("UPDATE review_ai_runs SET status='skipped',finished_at=?,result_json=? WHERE id=?").bind(now(),JSON.stringify({reason:'superseded_snapshot'}),b.run).run();return json({skipped:'superseded_snapshot'});}
     const sql=[this.env.DB.prepare("DELETE FROM review_picks WHERE item_id IN(SELECT id FROM content_items WHERE run_date=? AND region_code=? AND review_state='candidate')").bind(b.date,b.region),this.env.DB.prepare("UPDATE content_items SET ai_rank=NULL,ai_reason=NULL,topic=NULL,relevance=NULL,appeal_score=NULL,reason_facts_json=NULL WHERE run_date=? AND region_code=? AND review_state='candidate'").bind(b.date,b.region)];
     for(const t of b.result.translations||[])sql.push(this.env.DB.prepare("UPDATE content_items SET title_zh=? WHERE id=? AND review_state='candidate'").bind(t.title_zh,t.id));
     for(const [i,p] of b.result.picked.entries())sql.push(this.env.DB.prepare("UPDATE content_items SET ai_rank=?,ai_reason=?,topic=?,relevance=?,appeal_score=?,reason_facts_json=? WHERE id=? AND review_state='candidate'").bind(i+1,p.reason,p.topic,p.relevance,p.appeal_score??1,JSON.stringify(p.facts||[]),p.id));

     sql.push(this.env.DB.prepare("UPDATE review_ai_runs SET status='complete',finished_at=?,result_json=? WHERE id=?").bind(now(),JSON.stringify(b.result),b.run));
     for(const p of b.result.picked)sql.push(this.env.DB.prepare("INSERT OR IGNORE INTO task_outbox SELECT ?,'enrich',?,'pending',? FROM content_items WHERE id=? AND source_system!='wikifx-signal'").bind('enrich-'+b.run+'-'+p.id,JSON.stringify({item:p.id}),now(),p.id));
     await this.env.DB.batch(sql);return json({ok:true});
    }
    return await reviewAction(req,this.env);
   }catch(e){if(e instanceof HttpError)return json({code:e.code,message:e.message},e.status);return json({code:'SERVER_ERROR',message:'操作未完成，请稍后重试'},500);}
  });
 }
}
export async function dispatch(env:Env){
 await env.COORDINATOR.get(env.COORDINATOR.idFromName('hub')).fetch('https://internal/dispatch',{method:'POST'});
}
async function dispatchQueue(env:Env){
 const tasks=(await env.DB.prepare("SELECT * FROM task_outbox WHERE status='pending' ORDER BY CASE WHEN kind='image' AND json_extract(payload_json,'$.pilot')=1 THEN 0 ELSE 1 END,created_at LIMIT 10").all<any>()).results;
 for(const task of tasks){
  if(task.kind!=='image'&&!env.DEEPSEEK_API_KEY)continue;
  if(task.kind==='image'){const active=await env.DB.prepare("SELECT count(*) n FROM article_images WHERE state IN ('creating','running')").first<any>();if(active.n>=3)continue;await env.DB.prepare("UPDATE article_images SET state='creating',started_at=COALESCE(started_at,?) WHERE id=? AND state='queued'").bind(now(),JSON.parse(task.payload_json).image).run();}
  if(task.kind==='article'&&env.WRITER_READY!=='true')continue;
  if(task.kind==='article'){
   const active=await env.DB.prepare("SELECT count(*) n FROM submission_jobs j JOIN task_outbox t ON t.id=COALESCE(j.generation_request_id,j.id) WHERE t.status='started' AND j.state IN ('queued','writing','sending')").first<any>();
   if(active.n>=2)continue;
  }
  const workflowId=task.id.length>80?'task-'+await hash(task.id):task.id;
  try{await env.PIPELINE.create({id:workflowId,params:{kind:task.kind,...JSON.parse(task.payload_json)}});}
  catch{try{await (await env.PIPELINE.get(workflowId)).status();}catch{if(task.kind==='image')await env.DB.prepare("UPDATE article_images SET state='queued' WHERE id=? AND state='creating'").bind(JSON.parse(task.payload_json).image).run();continue;}}
  await env.DB.prepare("UPDATE task_outbox SET status='started' WHERE id=?").bind(task.id).run();
 }
}
export default {
 async fetch(req:Request,env:Env,ctx:ExecutionContext):Promise<Response>{
  const u=new URL(req.url),local=String(env.TEST_MODE)==='1';
  try{
   if(u.hostname===env.INGEST_HOST&&u.pathname==='/api/internal/collector-artifact'&&req.method==='POST'){
    if(!env.SIGNAL_INGEST_TOKEN||req.headers.get('Authorization')!==`Bearer ${env.SIGNAL_INGEST_TOKEN}`)return json({code:'UNAUTHORIZED'},401);
    const key=req.headers.get('X-Artifact-Key')||'';if(!/^cloud\/\d{4}-\d{2}-\d{2}\/(?:daily\/(global|india|pakistan|indonesia|_board)\.(json|md)|raw\/(global|india|pakistan|indonesia)\/[\w.-]+\.json|manifest\.json|result\.json|collection-log\.txt)$/.test(key))return json({code:'INVALID_KEY'},422);
    const bytes=await req.arrayBuffer();if(bytes.byteLength>32*1024*1024)return json({code:'TOO_LARGE'},413);await env.ARCHIVE.put(key,bytes);return json({ok:true});
   }
   if(u.pathname==='/api/v1/hotspots/daily-batches'&&req.method==='POST'&&([env.INGEST_HOST,'hotspots-test.wikifxusers.com'].includes(u.hostname)||local)){
    const r=await env.COORDINATOR.get(env.COORDINATOR.idFromName('hub')).fetch(req);ctx.waitUntil(dispatch(env));return r;
   }
   if(u.hostname!==env.REVIEW_HOST&&!local)return json({code:'NOT_FOUND'},404);
   if(req.method==='GET'&&u.pathname==='/api/review/candidates')return json(await candidateDetails(env,u.searchParams.get('region')||''));
   if(req.method==='GET'&&u.pathname==='/api/review'){await defaults(env);return json(await dashboard(env));}
   if(req.method==='POST'&&['/api/review/image','/api/review/pick','/api/review/submit','/api/review/generate','/api/review/regenerate','/api/review/approve','/api/review/back','/api/review/retry'].includes(u.pathname)){
    if(req.headers.get('Origin')!==u.origin&&!(local&&req.headers.get('Origin')==='http://127.0.0.1:8787'))fail(403,'ORIGIN_REQUIRED','只接受本页面提交');
    if(!req.headers.get('Content-Type')?.startsWith('application/json'))fail(415,'INVALID_CONTENT_TYPE','需要 JSON');
    const r=await env.COORDINATOR.get(env.COORDINATOR.idFromName('hub')).fetch(req);ctx.waitUntil(dispatch(env));return r;
   }
   if(req.method==='GET'&&u.pathname.startsWith('/api/images/')){const id=u.pathname.split('/').pop();const i=await env.DB.prepare("SELECT * FROM article_images WHERE id=? AND state='succeeded'").bind(id).first<any>();if(!i)return json({code:'IMAGE_NOT_READY'},404);const f=await env.ARCHIVE.get(i.thumbnail_key||i.original_key);if(!f)return json({code:'IMAGE_NOT_READY'},404);return new Response(f.body,{headers:{'Content-Type':f.httpMetadata?.contentType||i.mime_type,'Cache-Control':'public,max-age=86400','X-Content-Type-Options':'nosniff'}});}
   if(req.method==='GET'&&u.pathname.startsWith('/api/articles/')){
    const id=u.pathname.split('/').pop();const job=await env.DB.prepare('SELECT payload_key FROM submission_jobs WHERE id=?').bind(id).first<any>();
    if(!job?.payload_key)return json({code:'NOT_READY'},404);const file=await env.ARCHIVE.get(job.payload_key);if(!file)return json({code:'NOT_READY'},404);const payload=await file.json<any>();const result=await env.ARCHIVE.get(`articles/${id}/result.json`);const metadata=result?await result.json<any>():{};return json({...payload,image:imageView(await currentImage(env,id!)),article_content:metadata.content||payload.content,sources:metadata.sources||[],editorial_check:metadata.editorial_check||null,ai_review:metadata.ai_review||null,fact_check:metadata.fact_check||null,writer_model:metadata.model||null,writer_usage:metadata.usage||null});
   }
   if(req.method!=='GET'||u.pathname.startsWith('/api/'))return json({code:'NOT_FOUND'},404);
   const response=await env.ASSETS.fetch(req),h=new Headers(response.headers);h.set('X-Content-Type-Options','nosniff');h.set('Referrer-Policy','no-referrer');h.set('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'");return new Response(response.body,{status:response.status,headers:h});
  }catch(e){if(e instanceof HttpError)return json({code:e.code,message:e.message},e.status);return json({code:'SERVER_ERROR',message:'服务暂不可用'},500);}
 },
 async scheduled(event:ScheduledController,env:Env){if(event.cron==='0 1 * * *'){const date=today();await env.PIPELINE.create({id:'collector-'+date,params:{kind:'collect',date}}).catch(()=>{});}await dispatch(env);await env.DB.prepare('DELETE FROM rate_limits WHERE minute<?').bind(Math.floor(Date.now()/1000)-3600).run();}
};
