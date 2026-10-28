import {Container} from '@cloudflare/containers';import {now} from './regions';import type {Env} from './types';
export class CollectorContainer extends Container<Env>{defaultPort=8080;sleepAfter='30m';enableInternet=true;
 constructor(ctx:DurableObjectState<{}>,env:Env){super(ctx,env);this.envVars={TZ:'Asia/Shanghai',APIFY_TOKEN:env.APIFY_TOKEN||'',SERPER_API_KEYS:env.SERPER_API_KEYS||'',DEEPSEEK_API_KEY:env.DEEPSEEK_API_KEY||'',DEEPSEEK_BASE_URL:'https://api.deepseek.com',DEEPSEEK_FLASH_MODEL:'deepseek-flash',SIGNAL_INGEST_TOKEN:env.SIGNAL_INGEST_TOKEN||''};}
 async fetch(req:Request){if(new URL(req.url).pathname==='/internal/release'){await this.destroy();return new Response('stopped');}return super.fetch(req);}
}
export async function finishCollection(env:Env,date:string){
 const object=await env.ARCHIVE.get(`cloud/${date}/result.json`);if(!object)throw Error('COLLECTION_RESULT_MISSING');const result=await object.json<any>();
 const manifest=await env.ARCHIVE.get(`cloud/${date}/manifest.json`);
 if(manifest){const m=await manifest.json<any>();
  // Delivery can retry from durable R2 without re-running any paid collector.
  for(const page of m.pages){const r=await fetch('https://hotspots.wikifxusers.com/api/v1/hotspots/daily-batches',{method:'POST',headers:{'Authorization':`Bearer ${env.SIGNAL_INGEST_TOKEN}`,'Content-Type':'application/json','Idempotency-Key':`${page.batch_id}:${page.page_no}`},body:JSON.stringify(page)});if(![200,201].includes(r.status))throw Error('COLLECTOR_DELIVERY_'+r.status);}
  if(result.state==='failed'&&Object.keys(result.markets||{}).length){result.state=Object.values(result.markets).every((x:any)=>x.state==='complete')?'complete':'partial';delete result.error;await env.ARCHIVE.put(`cloud/${date}/result.json`,JSON.stringify(result));}
  for(const x of m.metadata||[])await env.DB.prepare("UPDATE content_items SET market=?,heat=?,opportunity_score=?,engagement_total=? WHERE run_date=? AND region_code=? AND topic_key=? AND source_system='wikifx-signal' AND available=1").bind(x.market,x.heat,x.opportunity_score,JSON.stringify(x.engagement_total),date,x.region,x.topic_id).run();}
 for(const [i,c]of(result.ai_calls||[]).entries()){const u=c.usage||{};await env.DB.prepare('INSERT OR IGNORE INTO review_ai_calls(id,run_id,kind,region_code,model,created_at,prompt_tokens,completion_tokens,cache_hit_tokens,estimated_cost_usd,pricing_json,usage_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)').bind(`collector-${date}-${i}`,`collector-${date}`,'collection',c.market,c.model,now(),u.prompt_tokens||0,u.completion_tokens||0,u.prompt_cache_hit_tokens||0,c.estimated_cost_usd,JSON.stringify({estimate:true,pricing:c.pricing}),JSON.stringify(u)).run();}
 await env.DB.prepare('UPDATE collection_runs SET state=?,finished_at=?,result_key=?,error=? WHERE run_date=?').bind(result.state,now(),`cloud/${date}/result.json`,result.error||null,date).run();return {state:result.state,markets:result.markets};
}
