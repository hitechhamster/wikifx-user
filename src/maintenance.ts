import type {Env} from './types';
import {now} from './regions';
import fixture from '../tests/example.json';
// Invoked only through the authenticated Cloudflare Workflow API, never a public route.
export async function acceptance(env:Env,run:string){
 if(!env.RADAR_INGEST_TOKEN)throw new Error('RADAR_TOKEN_NOT_CONFIGURED');
 const results:any[]=[];
 const b:any={...structuredClone(fixture),batch_id:crypto.randomUUID(),snapshot_id:run,revision:Date.now()};
 const send=async(payload:any,expected:number,label:string,token=env.RADAR_INGEST_TOKEN)=>{
  const r=await fetch('https://hotspots-test.wikifxusers.com/api/v1/hotspots/daily-batches',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json','Idempotency-Key':`${payload.batch_id}:${payload.page_no}`},body:JSON.stringify(payload)});
  const result=await r.json<any>();results.push({label,expected,status:r.status,response:result});return result;
 };
 const first=await send(b,201,'首次提交'),repeat=await send(b,200,'相同报文重复提交');
 results.push({label:'重复请求复用回执',passed:first.data?.receipt_id===repeat.data?.receipt_id&&repeat.data?.duplicate_request===true});
 await send({...b,warnings:['changed payload']},409,'相同幂等键不同报文');
 const multi={...b,batch_id:crypto.randomUUID(),snapshot_id:run+'-pages',revision:b.revision+1,page_count:2,items:[b.items[0]]};
 await send(multi,201,'分页第1页');await send({...multi,page_no:2,items:[b.items[0]]},409,'跨页重复拒绝');await send({...multi,page_no:2,items:[b.items[1]]},201,'分页第2页');
 await send({...b,batch_id:crypto.randomUUID(),snapshot_id:run+'-not-ready',revision:b.revision+2,collection_status:'not_ready',items:[],total_items:null,report_origin:null,report_generated_at:null},201,'not_ready');
 await send(b,401,'错误Token','invalid-test-credential');
 const output={at:now(),isolated_database:'wikifx-signal-acceptance',results,passed:results.every(r=>r.passed??r.status===r.expected)};
 await env.ARCHIVE.put(`acceptance/${run}.json`,JSON.stringify(output));return output;
}
export async function importOnce(env:Env,key:string){
 if(!/^manual-import\/\d{4}-\d{2}-\d{2}\.json$/.test(key))throw new Error('INVALID_MANIFEST_PATH');
 if(!env.SIGNAL_INGEST_TOKEN)throw new Error('SIGNAL_TOKEN_NOT_CONFIGURED');
 const object=await env.ARCHIVE.get(key);if(!object)throw new Error('MANIFEST_MISSING');const manifest=await object.json<any>();const results=[];
 for(const page of manifest.pages){
  const r=await fetch('https://hotspots.wikifxusers.com/api/v1/hotspots/daily-batches',{method:'POST',headers:{Authorization:`Bearer ${env.SIGNAL_INGEST_TOKEN}`,'Content-Type':'application/json','Idempotency-Key':`${page.batch_id}:${page.page_no}`},body:JSON.stringify(page)});
  const body=await r.json<any>();results.push({region:page.region_code,page:page.page_no,status:r.status,receipt:body});
  if(![200,201].includes(r.status))throw new Error('IMPORT_HTTP_'+r.status);
 }
 // Collector-only metadata stays a sidecar, not an undocumented protocol extension.
 for(const meta of manifest.metadata){await env.DB.prepare('UPDATE content_items SET market=?,heat=?,opportunity_score=?,engagement_total=? WHERE source_system=\'wikifx-signal\' AND run_date=? AND region_code=? AND topic_key=?').bind(meta.market,meta.heat,meta.opportunity_score,JSON.stringify(meta.engagement_total),manifest.date,meta.region,meta.topic_id).run();}
 const result={date:manifest.date,results};await env.ARCHIVE.put(`manual-import/${manifest.date}-receipts.json`,JSON.stringify(result));return result;
}
export async function radarManifest(env:Env){
 const key='manual-import/radar-2026-10-26.json',file=await env.ARCHIVE.get(key);if(!file)throw Error('RADAR_MANIFEST_MISSING');
 const m=await file.json<any>();if(m.date!=='2026-10-26'||m.pages.reduce((n:number,p:any)=>n+p.items.length,0)!==227)throw Error('RADAR_MANIFEST_INVALID');return m;
}
export async function radarPage(env:Env,page:any){
 if(!env.RADAR_INGEST_TOKEN)throw Error('RADAR_TOKEN_MISSING');
 const r=await fetch('https://hotspots.wikifxusers.com/api/v1/hotspots/daily-batches',{method:'POST',headers:{Authorization:`Bearer ${env.RADAR_INGEST_TOKEN}`,'Content-Type':'application/json','Idempotency-Key':`${page.batch_id}:${page.page_no}`},body:JSON.stringify(page)});const receipt=await r.json<any>();
 await env.ARCHIVE.put(`manual-import/radar-receipts/${page.region_code}-${page.page_no}.json`,JSON.stringify({status:r.status,receipt}));if(![200,201].includes(r.status))throw Error('RADAR_IMPORT_'+r.status+'_'+JSON.stringify(receipt));return {region:page.region_code,page:page.page_no,status:r.status,count:page.items.length};
}
