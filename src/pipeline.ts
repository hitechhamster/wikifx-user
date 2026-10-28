import {runImage,enqueueImage,imageLanguageState} from './images';
import {referenceFooter} from './article-sources';
import {insufficientMaterial} from './material';
import {deliver} from './delivery';
import {editorialGate} from './editorial';
import {WorkflowEntrypoint,WorkflowEvent,WorkflowStep} from 'cloudflare:workers';
import {Container,getContainer} from '@cloudflare/containers';
import {preselect,fallback} from './ai';
import {regions,now} from './regions';
import type {Env} from './types';
import {acceptance,importOnce,radarManifest,radarPage} from './maintenance';
import {enrich} from './enrich';
import {finishCollection} from './collector';
export class ArticleContainer extends Container<Env>{
 defaultPort=8080;sleepAfter='5m';enableInternet=true;
 constructor(ctx:DurableObjectState<{}>,env:Env){super(ctx,env);this.envVars={DEEPSEEK_API_KEY:env.DEEPSEEK_API_KEY||'',WRITER_MODEL:env.WRITER_MODEL||'deepseek-flash'};}
 async fetch(req:Request){if(new URL(req.url).pathname==='/internal/release'){await this.destroy();return new Response('stopped');}return super.fetch(req);}
}
export class Pipeline extends WorkflowEntrypoint<Env,any>{
 async run(event:WorkflowEvent<any>,step:WorkflowStep){
  const p=event.payload;
  if(p.kind==='image')return runImage(this.env,p.image,step);
  if(p.kind==='article-reaudit'){
   const job=await step.do('audit-load-job',()=>this.env.DB.prepare('SELECT j.*,c.payload_json,c.region_code,c.revision,c.run_date item_date,c.source_system FROM submission_jobs j JOIN content_items c ON c.id=j.item_id WHERE j.id=?').bind(p.job).first<any>());
   if(!job||!['draft','approved'].includes(job.state))return {skipped:'not_draft'};
   const result=await step.do('audit-load-result',async()=>{const r=await this.env.ARCHIVE.get(`articles/${job.id}/result.json`);return r?.json<any>()});if(!result?.article)return {skipped:'missing_article'};
   const item=await step.do('audit-load-material',async()=>{let value=JSON.parse(job.payload_json);const enriched=await this.env.DB.prepare('SELECT result_json FROM enrichment_runs WHERE item_id=? AND revision=?').bind(job.item_id,job.revision).first<any>();if(enriched?.result_json&&job.source_system!=='wikifx-signal')value=JSON.parse(enriched.result_json);const verified=await this.env.DB.prepare('SELECT result_json FROM rumor_verifications WHERE item_id=? AND revision=? AND run_date=?').bind(job.item_id,job.revision,job.item_date).first<any>();if(verified)value=JSON.parse(verified.result_json);return value});
   const region=regions.find(r=>r.code===job.region_code)!,writer=this.env.WRITER.get(this.env.WRITER.idFromName(event.instanceId));
   try{
    await step.do('audit-start',{retries:{limit:3,delay:'30 seconds'}},async()=>{const r=await writer.fetch('http://container/jobs/'+event.instanceId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({review_only:true,item,region,article:{title:result.article.title,summary:result.article.meta_description,content:result.content}})});if(!r.ok)throw Error('AUDIT_START_FAILED');return true});
    for(let i=0;i<30;i++){await step.sleep('audit-wait-'+i,'10 seconds');const out:any=await step.do('audit-poll-'+i,async()=>{const r=await writer.fetch('http://container/jobs/'+event.instanceId);return r.json<any>()});if(out.state==='running')continue;if(!out.ai_review)throw Error('AUDIT_FAILED');
     return await step.do('audit-store',async()=>{const a=out.ai_review,u=a.usage||{},hit=u.prompt_cache_hit_tokens||0;await this.env.DB.prepare('INSERT OR IGNORE INTO review_ai_calls(id,run_id,kind,region_code,model,created_at,prompt_tokens,completion_tokens,cache_hit_tokens,estimated_cost_usd,usage_json,error_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').bind(event.instanceId,event.instanceId,'article_review',region.code,a.model||'deepseek-flash',now(),u.prompt_tokens||0,u.completion_tokens||0,hit,u.estimated_cost_usd||0,JSON.stringify(u),a.error||null).run();
      const current=await this.env.DB.prepare('SELECT state,generation_request_id FROM submission_jobs WHERE id=?').bind(job.id).first<any>();if(current.generation_request_id!==job.generation_request_id||!['draft','approved'].includes(current.state))return {skipped:'changed_generation'};
      result.ai_review_history=[...(result.ai_review_history||[]),result.ai_review].filter(Boolean);result.ai_review=a;await this.env.ARCHIVE.put(`articles/${job.id}/result.json`,JSON.stringify(result));await this.env.ARCHIVE.put(`articles/${job.id}/audits/${event.instanceId}.json`,JSON.stringify(a));return {reviewed:true,issues:a.count||0,state:a.state};});
    }throw Error('AUDIT_TIMEOUT');
   }finally{await step.do('audit-release',async()=>{await writer.fetch('http://container/internal/release',{method:'POST'});return true})}
  }
  if(p.kind==='article-preview'){
   const row=await step.do('preview-material',()=>this.env.DB.prepare('SELECT c.*,j.id job_id FROM content_items c JOIN submission_jobs j ON j.item_id=c.id WHERE c.id=?').bind(p.item).first<any>());if(!row)throw Error('ITEM_NOT_FOUND');
   const region=regions.find(r=>r.code===row.region_code)!,writer=this.env.WRITER.get(this.env.WRITER.idFromName(event.instanceId));
   await step.do('preview-start',async()=>{const date=now().slice(0,10);await this.env.DB.prepare("INSERT OR IGNORE INTO generation_requests SELECT ?,?,?,? WHERE (SELECT count(*) FROM generation_requests WHERE run_date=?)<?").bind(event.instanceId,row.job_id,date,now(),date,Number(this.env.DAILY_GENERATION_LIMIT||100)).run();if(!await this.env.DB.prepare('SELECT id FROM generation_requests WHERE id=?').bind(event.instanceId).first())throw Error('DAILY_LIMIT');const r=await writer.fetch('http://container/jobs/'+event.instanceId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:JSON.parse(row.payload_json),region})});if(!r.ok)throw Error('WRITER_START_FAILED');return true;});
   try{for(let i=0;i<40;i++){await step.sleep('preview-wait-'+i,'15 seconds');const output:any=await step.do('preview-poll-'+i,async()=>{const r=await writer.fetch('http://container/jobs/'+event.instanceId);return r.json<any>();});if(output.state==='running')continue;
    await step.do('preview-store',async()=>{await this.env.ARCHIVE.put('writer-preview/'+event.instanceId+'.json',JSON.stringify(output));const u=output.usage||{},hit=u.prompt_cache_hit_tokens||0;await this.env.DB.prepare('INSERT OR IGNORE INTO review_ai_calls(id,run_id,kind,region_code,model,created_at,prompt_tokens,completion_tokens,cache_hit_tokens,estimated_cost_usd,usage_json,error_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').bind(event.instanceId,event.instanceId,'article_preview',region.code,output.model||this.env.WRITER_MODEL||'deepseek-flash',now(),u.prompt_tokens||0,u.completion_tokens||0,hit,(u.estimated_cost_usd??u.cost??(hit*.006+((u.prompt_tokens||0)-hit)*.3+(u.completion_tokens||0)*1.2)/1e6),JSON.stringify(u),output.error||null).run();return true;});return {state:output.state,key:'writer-preview/'+event.instanceId+'.json',error:output.error||null};}throw Error('WRITER_TIMEOUT');}
   finally{await step.do('preview-release',async()=>{await writer.fetch('http://container/internal/release',{method:'POST'});return true;});}
  }
  if(p.kind==='flush-outbox'){for(let i=0;i<8;i++)await step.do('dispatch-'+i,async()=>{const r=await this.env.COORDINATOR.get(this.env.COORDINATOR.idFromName('hub')).fetch('https://internal/dispatch',{method:'POST'});return {status:r.status};});return {dispatched:true};}
  if(p.kind==='radar-repair-region'){
   const rows=await step.do('repair-scope',async()=>{const all=(await this.env.DB.prepare("SELECT * FROM content_items WHERE run_date=? AND region_code=? AND source_system='wikifx-hotspot-radar' AND available=1 ORDER BY ai_rank IS NULL,ai_rank,CAST(json_extract(payload_json,'$.ranking.export_position') AS INTEGER)").bind(p.date,p.region).all<any>()).results;return all.filter(r=>editorialGate(r,p.region)&&(r.ai_rank!=null||JSON.parse(r.payload_json).ranking?.export_position<=15)).map(r=>({id:r.id,full:JSON.parse(r.payload_json).content_status==='full'}));});
   for(const row of rows){if(row.full)continue;await step.do('retry-evidence-'+row.id,{retries:{limit:0,delay:'1 second'}},async()=>{const budget=await this.env.DB.prepare('SELECT serper_calls FROM verification_budgets WHERE run_date=? AND region_code=?').bind(p.date,p.region).first<any>();if(budget?.serper_calls>=20)return {skipped:'REGION_SERPER_LIMIT'};return enrich(this.env,row.id,'credit_recovery',true);});}
   return step.do('rank-quality',{retries:{limit:0,delay:'1 second'}},()=>preselect(this.env,p.date,p.region,event.instanceId));
  }
  if(p.kind==='serper-probe')return step.do('probe',{retries:{limit:0,delay:'1 second'}},async()=>{const keys=(this.env.SERPER_API_KEYS||'').split(/[\s,]+/).filter(Boolean);try{const r=await fetch('https://google.serper.dev/search',{method:'POST',headers:{'X-API-KEY':keys[0],'Content-Type':'application/json'},body:JSON.stringify({q:'Bank Negara Malaysia monetary policy',num:10}),signal:AbortSignal.timeout(20000)});const b=await r.json<any>().catch(()=>({}));let message=String(b.message||b.error||'');for(const key of keys)message=message.split(key).join('[redacted]');return {status:r.status,results:Array.isArray(b.organic)?b.organic.length:0,message:message.slice(0,300)};}catch{return {error:'NETWORK_ERROR'};}});
  if(p.kind==='radar-import'){
   const m=await radarManifest(this.env);await step.do('preserve-review-state',async()=>{const state=await this.env.DB.prepare("SELECT * FROM region_reviews WHERE run_date='2026-10-26'").all();const picks=await this.env.DB.prepare("SELECT * FROM review_picks WHERE run_date='2026-10-26'").all();await this.env.ARCHIVE.put('manual-import/before-radar-review-state.json',JSON.stringify({state,picks}));await this.env.DB.prepare("UPDATE region_reviews SET locked=0 WHERE run_date='2026-10-26' AND region_code IN ('SA','ID','MY') AND status!='skipped'").run();return true;});
   const receipts=[];for(const page of m.pages)receipts.push(await step.do(`import-${page.region_code}-${page.page_no}`,{retries:{limit:0,delay:'1 second'}},()=>radarPage(this.env,page)));return receipts;
  }
  if(p.kind==='radar-region'){
   const rows=await step.do('load-enrichment-scope',async()=>{const all=(await this.env.DB.prepare("SELECT id,payload_json FROM content_items WHERE run_date=? AND region_code=? AND source_system='wikifx-hotspot-radar' AND available=1 ORDER BY CAST(json_extract(payload_json,'$.ranking.export_position') AS INTEGER)").bind(p.date,p.region).all<any>()).results;return all.slice(0,15).map(x=>x.id);});
   for(const id of rows)await step.do('supplement-'+id,{retries:{limit:0,delay:'1 second'}},()=>enrich(this.env,id,'original_top15'));
   return step.do('rank-merged',{retries:{limit:0,delay:'1 second'}},()=>preselect(this.env,p.date,p.region,event.instanceId));
  }
  if(p.kind==='hub-diagnostic')return step.do('check-transport',{retries:{limit:0,delay:'1 second'}},async()=>{
   let headerValid=false;try{new Headers({'X-Ingest-Token':this.env.CONTENT_INGEST_TOKEN||''});headerValid=true;}catch{}
   try{const r=await fetch('https://editor.chouai.cc.cd/api/articles/ingest',{method:'GET',redirect:'manual',signal:AbortSignal.timeout(15000)});return {tokenPresent:!!this.env.CONTENT_INGEST_TOKEN,headerValid,status:r.status};}
   catch(e){let message=e instanceof Error?e.message:'UNKNOWN';for(const secret of [this.env.CONTENT_INGEST_TOKEN,this.env.DEEPSEEK_API_KEY])if(secret)message=message.split(secret).join('[redacted]');return {headerValid,error:message.slice(0,300)};}
  });
  if(p.kind==='deliver')return deliver(this.env,p.delivery,step);
  if(p.kind==='hub-test'){const id=await step.do('prepare-one-test',async()=>{const r=await this.env.COORDINATOR.get(this.env.COORDINATOR.idFromName('hub')).fetch('https://internal/prepare-test',{method:'POST',body:JSON.stringify({job:p.job})});const b=await r.json<any>();if(!r.ok)throw Error(b.code||'TEST_PREPARE_FAILED');return b.id;});return deliver(this.env,id,step);}
  if(p.kind==='collector-health')return step.do('health',async()=>{const c=this.env.COLLECTOR.get(this.env.COLLECTOR.idFromName('daily'));try{const r=await c.fetch('http://container/health');return await r.json<any>();}finally{await c.fetch('http://container/internal/release',{method:'POST'});}});
  if(p.kind==='collect'){
   const c=this.env.COLLECTOR.get(this.env.COLLECTOR.idFromName('daily'));
   await step.do('start-collection',{retries:{limit:0,delay:'1 second'}},async()=>{
    if(!this.env.APIFY_TOKEN||!this.env.SERPER_API_KEYS||!this.env.DEEPSEEK_API_KEY||!this.env.SIGNAL_INGEST_TOKEN)throw Error('COLLECTOR_SECRET_MISSING');
    const claim=await this.env.DB.prepare("INSERT OR IGNORE INTO collection_runs(run_date,state,started_at) VALUES(?,'running',?)").bind(p.date,now()).run();if(!claim.meta.changes)throw Error('COLLECTION_ALREADY_STARTED');
    const r=await c.fetch(`http://container/jobs/${p.date}`,{method:'POST'});if(!r.ok)throw Error('COLLECTOR_START_FAILED');return true;
   });
   try{for(let i=0;i<180;i++){await step.sleep(`collect-wait-${i}`,'1 minute');const status:any=await step.do(`collect-poll-${i}`,async()=>{const r=await c.fetch(`http://container/jobs/${p.date}`);return r.json<any>();});if(status.state==='missing')throw Error('COLLECTOR_RESTARTED_NO_AUTOMATIC_RECHARGE');if(status.state!=='running'){const done=await step.do('record-costs',()=>finishCollection(this.env,p.date));await step.do('release-collector',async()=>{await c.fetch('http://container/internal/release',{method:'POST'});return true;});return done;}}throw Error('COLLECTOR_TIMEOUT');}
   catch{await step.do('collection-failed',async()=>{await this.env.DB.prepare("UPDATE collection_runs SET state='failed',finished_at=?,error='COLLECTION_INTERRUPTED' WHERE run_date=?").bind(now(),p.date).run();await c.fetch('http://container/internal/release',{method:'POST'});return true;});return {state:'failed'};}
  }
  if(p.kind==='enrich')return step.do('enrich',{retries:{limit:3,delay:'30 seconds'}},()=>enrich(this.env,p.item,'recommended'));
  if(p.kind==='writer-probe')return step.do('probe',async()=>{const writer=this.env.WRITER.get(this.env.WRITER.idFromName(event.instanceId));try{const r=await writer.fetch('http://container/health');return {status:r.status,ok:r.ok};}finally{await writer.fetch('http://container/internal/release',{method:'POST'});}});
  if(p.kind==='release-writer')return step.do('release',async()=>{await this.env.WRITER.get(this.env.WRITER.idFromName(p.instanceName)).fetch('http://container/internal/release',{method:'POST'});return true;});
  if(p.kind==='acceptance')return step.do('acceptance',{retries:{limit:0,delay:'1 second'}},()=>acceptance(this.env,event.instanceId));
  if(p.kind==='import-once')return step.do('import-once',{retries:{limit:0,delay:'1 second'}},()=>importOnce(this.env,p.key));
  if(p.kind==='preselect')return step.do('preselect',{retries:{limit:0,delay:'1 second'}},async()=>{
   try{return await preselect(this.env,p.date,p.region,event.instanceId,p.cachedRun,p.preview);}
   catch(error){const code=error instanceof Error&&/^[A-Z_0-9]+$/.test(error.message)?error.message:'AI_REQUEST_FAILED';return fallback(this.env,p.date,p.region,event.instanceId,code);}
  });
  const job=await step.do('load-job',()=>this.env.DB.prepare('SELECT * FROM submission_jobs WHERE id=?').bind(p.job).first<any>());
  if(!job)return {skipped:'missing_job'};
  if(job.generation_request_id&&job.generation_request_id!==event.instanceId)return {skipped:'superseded_generation'};
  const row=JSON.parse(job.snapshot_json),region=regions.find(r=>r.code===row.region_code)!;
  let item=row.source_system==='wikifx-signal'?JSON.parse(row.payload_json):await step.do('enrich-selected',{retries:{limit:3,delay:'30 seconds'}},()=>enrich(this.env,row.id,'selected'));
  const verified=await this.env.DB.prepare('SELECT result_json FROM rumor_verifications WHERE item_id=? AND revision=? AND run_date=?').bind(row.id,row.revision,row.run_date).first<any>();if(verified)item=JSON.parse(verified.result_json);
  item.insufficient_material=insufficientMaterial(item,row.source_system);
  const stillSelected=await this.env.DB.prepare('SELECT status FROM content_items WHERE id=?').bind(job.item_id).first<any>();
  if(stillSelected?.status!=='selected')return {skipped:'not_selected'};
  try{
   const writer=this.env.WRITER.get(this.env.WRITER.idFromName(event.instanceId));
   await step.do('start-writing',{retries:{limit:3,delay:'30 seconds',backoff:'exponential'}},async()=>{
    await this.env.DB.prepare("UPDATE submission_jobs SET state='writing',updated_at=? WHERE id=?").bind(now(),job.id).run();
    const r=await writer.fetch(new Request(`http://container/jobs/${event.instanceId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item,region})}));if(!r.ok)throw new Error('WRITER_START_HTTP_'+r.status);
   });
   let output:any;
   for(let i=0;i<40;i++){
    await step.sleep(`writing-wait-${i}`,'15 seconds');
    const result=await step.do(`writing-poll-${i}`,async()=>{const r=await writer.fetch(`http://container/jobs/${event.instanceId}`);if(!r.ok)throw new Error('WRITER_POLL_FAILED');return r.json<any>();});
    if(result.state==='missing')throw new Error('WRITER_RESTARTED');
    if(result.state!=='running'){output=result;break;}
   }
   if(!output)throw new Error('WRITER_TIMEOUT');
   await step.do('store-generation',async()=>{
    const u=output.usage||{},hit=u.prompt_cache_hit_tokens||0,cost=(u.estimated_cost_usd??u.cost??(hit*.006+((u.prompt_tokens||0)-hit)*.3+(u.completion_tokens||0)*1.2)/1e6);
    await this.env.DB.prepare('INSERT OR IGNORE INTO review_ai_calls(id,run_id,kind,region_code,model,created_at,prompt_tokens,completion_tokens,cache_hit_tokens,estimated_cost_usd,usage_json,error_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').bind(event.instanceId,event.instanceId,'article',region.code,output.model||this.env.WRITER_MODEL||'deepseek-flash',now(),u.prompt_tokens||0,u.completion_tokens||0,hit,cost,JSON.stringify(u),output.error||null).run();
    if(output.ai_review){const a=output.ai_review,u=a.usage||{},hit=u.prompt_cache_hit_tokens||0;await this.env.DB.prepare('INSERT OR IGNORE INTO review_ai_calls(id,run_id,kind,region_code,model,created_at,prompt_tokens,completion_tokens,cache_hit_tokens,estimated_cost_usd,usage_json,error_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').bind(event.instanceId+'-review',event.instanceId,'article_review',region.code,a.model||'deepseek-flash',now(),u.prompt_tokens||0,u.completion_tokens||0,hit,u.estimated_cost_usd||0,JSON.stringify(u),a.error||null).run();}
    await this.env.ARCHIVE.put(`articles/${job.id}/attempts/${event.instanceId}.json`,JSON.stringify(output));
    await this.env.ARCHIVE.put(`articles/${job.id}/result.json`,JSON.stringify(output));
   });
   await step.do('release-writer',async()=>{await writer.fetch('http://container/internal/release',{method:'POST'});return true;});
   if(output.state!=='complete')throw new Error(output.error||'ARTICLE_VALIDATION_FAILED');
   const payload={externalId:job.external_id,title:output.article.title,summary:output.article.meta_description,content:output.content+referenceFooter(output.sources||[],region.languageId),contentFormat:'html',language:region.language,languageId:region.languageId,region:region.group,category:'新闻',source:'wikifx-signal',author:'WikiFX Signal Generator',keywords:(output.article.keywords||[]).join(',')};
   await step.do('freeze-payload',async()=>{
    await this.env.ARCHIVE.put(`articles/${job.id}/ingest.json`,JSON.stringify(payload));
    await this.env.DB.prepare('UPDATE submission_jobs SET article_key=?,payload_key=?,updated_at=? WHERE id=?').bind(`articles/${job.id}/result.json`,`articles/${job.id}/ingest.json`,now(),job.id).run();
    await this.env.DB.prepare('UPDATE content_items SET article_path=? WHERE id=?').bind(`articles/${job.id}/result.json`,job.item_id).run();
   });
   await step.do('generation-ready',()=>this.env.DB.batch([this.env.DB.prepare("UPDATE submission_jobs SET state='draft',error=NULL,updated_at=? WHERE id=?").bind(now(),job.id),this.env.DB.prepare("UPDATE content_items SET review_state='draft' WHERE id=?").bind(job.item_id)]).then(()=>true));
   await step.do('queue-head-image',async()=>{const enabled=await imageLanguageState(this.env,region.code);if(enabled.state==='supported'){try{await enqueueImage(this.env,job.id)}catch{return false;}}return true;});
   return {generated:true,sent:false};
  }catch(error){
   let message=error instanceof Error?error.message:'PIPELINE_FAILED';
   for(const value of [this.env.CONTENT_INGEST_TOKEN,this.env.DEEPSEEK_API_KEY])if(value)message=message.split(value).join('[redacted]');
   await step.do('mark-failed',()=>this.env.DB.batch([
    this.env.DB.prepare("UPDATE submission_jobs SET state='failed',error=?,updated_at=? WHERE id=?").bind(message.slice(0,500),now(),job.id),
    this.env.DB.prepare("UPDATE content_items SET status='failed',review_state='failed',publish_result=? WHERE id=? AND status='selected'").bind(message.slice(0,500),job.item_id)
   ]).then(()=>true));return {failed:true};
  }
 }
}


