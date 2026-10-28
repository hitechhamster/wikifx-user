import fs from 'node:fs';
let s=fs.readFileSync('src/pipeline.ts','utf8');s="import {deliver} from './delivery';\n"+s;
s=s.replace('  const p=event.payload;',`  const p=event.payload;
  if(p.kind==='deliver')return deliver(this.env,p.delivery,step);
  if(p.kind==='hub-test'){const id=await step.do('prepare-one-test',async()=>{const r=await this.env.COORDINATOR.get(this.env.COORDINATOR.idFromName('hub')).fetch('https://internal/prepare-test',{method:'POST',body:JSON.stringify({job:p.job})});const b=await r.json<any>();if(!r.ok)throw Error(b.code||'TEST_PREPARE_FAILED');return b.id;});return deliver(this.env,id,step);}`);
const a=s.indexOf("   if(job.dry_run||"),b=s.indexOf('\n  }catch(error){',a);
if(a<0||b<0)throw Error('splice not found');s=s.slice(0,a)+`   await step.do('generation-ready',()=>this.env.DB.prepare("UPDATE submission_jobs SET state='ready',error=NULL,updated_at=? WHERE id=?").bind(now(),job.id).run().then(()=>true));
   return {generated:true,sent:false};`+s.slice(b);
s=s.replace("  if(!job)return {skipped:'missing_job'};","  if(!job)return {skipped:'missing_job'};\n  if(job.generation_request_id&&job.generation_request_id!==event.instanceId)return {skipped:'superseded_generation'};");
fs.writeFileSync('src/pipeline.ts',s);
s=fs.readFileSync('src/index.ts','utf8').replace("import {dashboard,reviewAction} from './review';","import {dashboard} from './review';\nimport {reviewAction,defaults} from './actions';\nimport {prepareTest} from './delivery';");
s=s.replace("    if(path==='/dispatch')",`    if(path==='/prepare-test'){const b=await req.json<any>();return json({id:await prepareTest(this.env,b.job)});}
    if(path==='/claim-delivery'){const b=await req.json<any>();const r=await this.env.DB.prepare("UPDATE delivery_jobs SET state='sending',attempts=?,updated_at=? WHERE id=? AND state IN ('queued','sending') AND EXISTS(SELECT 1 FROM review_picks p WHERE p.item_id=delivery_jobs.item_id)").bind(b.attempt+1,now(),b.id).run();if(!r.meta.changes)await this.env.DB.prepare("UPDATE delivery_jobs SET state='cancelled' WHERE id=? AND state='queued'").bind(b.id).run();return json({ok:!!r.meta.changes});}
    if(path==='/dispatch')`);
s=s.replace("JOIN task_outbox t ON t.id=j.id", "JOIN task_outbox t ON t.id=COALESCE(j.generation_request_id,j.id)");
s=s.replace("return json(await dashboard(env));","{await defaults(env);return json(await dashboard(env));}");
s=s.replace("'/api/review/submit'].includes", "'/api/review/submit','/api/review/generate','/api/review/regenerate'].includes");
fs.writeFileSync('src/index.ts',s);
s=fs.readFileSync('src/review.ts','utf8');s=s.slice(0,s.indexOf('export async function reviewAction'));
s=s.replace('j.state progress,j.error,j.hub_id',"CASE WHEN d.state IN ('queued','sending') THEN 'sending' WHEN d.state='failed' THEN 'failed' ELSE j.state END progress,COALESCE(d.error,j.error) error,COALESCE(d.hub_id,j.hub_id) hub_id,j.payload_key");
s=s.replace('LEFT JOIN review_picks p ON',"LEFT JOIN delivery_jobs d ON d.job_id=j.id AND d.mode='live' LEFT JOIN review_picks p ON");
s=s.replace("'SELECT count(*) n FROM submission_jobs WHERE run_date=?'",'"SELECT count(*) n FROM delivery_jobs WHERE run_date=? AND state!=\'cancelled\'"');
s=s.replace(' return {date,'," const generated=await env.DB.prepare('SELECT count(*) n FROM generation_requests WHERE run_date=?').bind(date).first<any>();\n return {generation_limit:Number(env.DAILY_GENERATION_LIMIT||100),generated:generated.n,date,");
fs.writeFileSync('src/review.ts',s);
s=fs.readFileSync('src/types.ts','utf8').replace('DAILY_SUBMISSION_LIMIT:string;','DAILY_SUBMISSION_LIMIT:string; DAILY_GENERATION_LIMIT:string;');fs.writeFileSync('src/types.ts',s);
const cfg=JSON.parse(fs.readFileSync('wrangler.jsonc','utf8'));cfg.vars.DAILY_GENERATION_LIMIT='100';fs.writeFileSync('wrangler.jsonc',JSON.stringify(cfg,null,2));
