import {insufficientMaterial} from './material';
import {fail,json,hash} from './protocol';
import {regions,today,now} from './regions';
import type {Env} from './types';
export async function dashboard(env:Env){
 const date=today();
 const items=(await env.DB.prepare(`SELECT c.id,c.region_code,c.title,c.title_zh,c.payload_json,c.summary,c.url,c.source,c.source_system,c.status,c.review_state,c.ai_rank,c.ai_reason,c.topic,c.relevance,c.appeal_score,c.reason_facts_json,c.heat,c.lead_created_at,j.id job_id,j.generation_request_id,CASE WHEN d.state IN ('queued','sending') THEN 'sending' WHEN d.state='failed' THEN 'failed' ELSE j.state END progress,COALESCE(d.error,j.error) error,COALESCE(d.hub_id,j.hub_id) hub_id,j.payload_key,k.original_hub_id,k.release_confirmed correction_released,k.external_id correction_external_id,p.item_id picked FROM content_items c LEFT JOIN submission_jobs j ON j.item_id=c.id LEFT JOIN delivery_jobs d ON d.job_id=j.id AND d.mode='live' LEFT JOIN article_corrections k ON k.item_id=c.id LEFT JOIN review_picks p ON p.item_id=c.id WHERE (c.run_date=? OR c.review_state IN ('generating','draft','approved','failed')) AND c.available=1 AND c.status!='legacy_hot' ORDER BY c.ai_rank IS NULL,c.ai_rank,c.id`).bind(date).all<any>()).results;
 for(const x of items){const p=JSON.parse(x.payload_json);x.insufficient=insufficientMaterial(p,x.source_system);x.picked=!!x.picked;for(const key of ['payload_json','summary','source','status','topic','heat','reason_facts_json','appeal_score','lead_created_at'])delete x[key];if(x.review_state==='candidate'&&!x.ai_rank)delete x.url;for(const key of Object.keys(x))if(x[key]===null)delete x[key];}
 const reviews=(await env.DB.prepare('SELECT * FROM region_reviews WHERE run_date=?').bind(date).all<any>()).results;
 const batches=(await env.DB.prepare("SELECT payload_json FROM ingest_batches WHERE status='delivered' AND json_extract(payload_json,'$.data_date')=? ORDER BY revision DESC").bind(date).all<any>()).results.map(x=>JSON.parse(x.payload_json));
 const used=await env.DB.prepare("SELECT count(*) n FROM delivery_jobs WHERE run_date=? AND state!='cancelled'").bind(date).first<any>();
 const generated=await env.DB.prepare('SELECT count(*) n FROM generation_requests WHERE run_date=?').bind(date).first<any>();
 return {generation_limit:Number(env.DAILY_GENERATION_LIMIT||100),generated:generated.n,date,default_reviewer:env.DEFAULT_REVIEWER,limit:Number(env.DAILY_SUBMISSION_LIMIT),used:used.n,writer_ready:env.WRITER_READY==='true',dry_run:env.SUBMISSION_MODE!=='live'||!env.CONTENT_INGEST_TOKEN,regions:regions.map(r=>{
  const state=reviews.find(x=>x.region_code===r.code),pool=items.filter(x=>x.region_code===r.code);
  const streams=new Map<string,any>();for(const b of batches.filter(x=>x.region_code===r.code))if(!streams.has(b.source_system))streams.set(b.source_system,b);
  const bs=[...streams.values()];const valid=bs.filter(b=>['completed','partial'].includes(b.collection_status));
  const data_status=state?.locked&&pool.length?'正常':valid.length?(pool.length?'正常':'0 条'):bs.some(b=>b.collection_status==='failed')?'采集失败':!r.scheduled||bs.length&&bs.every(b=>b.collection_status==='not_scheduled')?'未安排采集':'等待数据';
  return {...r,data_status,state:state?.status||'pending',locked:!!state?.locked,items:pool,warnings:bs.flatMap(b=>b.warnings||[])};
 })};
}

export async function candidateDetails(env:Env,region:string){
 if(!regions.some(r=>r.code===region))fail(422,'INVALID_REGION','地区无效');
 const rows=(await env.DB.prepare("SELECT id,url,summary,payload_json FROM content_items WHERE run_date=? AND region_code=? AND available=1 AND review_state='candidate' AND ai_rank IS NULL").bind(today(),region).all<any>()).results;
 return {items:rows.map(x=>({id:x.id,url:x.url,summary:x.summary,sources:JSON.parse(x.payload_json).sources||[],details_loaded:true}))};
}
