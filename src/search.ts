import type {Env} from './types';import {now} from './regions';import {reserveSearch} from './verification';import {hash} from './protocol';
export async function searchEvidence(env:Env,row:any){
 const paused=await env.DB.prepare("SELECT value FROM settings WHERE key='serper_paused'").first<any>();if(paused?.value==='1')return {calls:0,error:'SERPER_CREDITS_EXHAUSTED'};
 const keys=(env.SERPER_API_KEYS||'').split(/[\s,]+/).filter(Boolean);let calls=0,error='SERPER_NOT_CONFIGURED';
 const cursor=await env.DB.prepare("SELECT value FROM settings WHERE key='serper_key_cursor'").first<any>();const start=Number(cursor?.value||0)%Math.max(1,keys.length);
 for(let offset=0;offset<keys.length;offset++){const index=(start+offset)%keys.length,key=keys[index],fingerprint=await hash(key);if(await env.DB.prepare('SELECT value FROM settings WHERE key=?').bind('serper_exhausted_'+fingerprint).first())continue;
  if(!await reserveSearch(env,row.run_date,row.region_code))return {calls,error:'REGION_SERPER_LIMIT'};calls++;let status=null,credits:number|null=null;
  try{const r=await fetch('https://google.serper.dev/search',{method:'POST',headers:{'X-API-KEY':key,'Content-Type':'application/json'},body:JSON.stringify({q:row.title,num:10}),signal:AbortSignal.timeout(20000)});status=r.status;const body=await r.json<any>().catch(()=>({}));if(r.ok){credits=typeof body.credits==='number'?body.credits:1;await record(env,row,status,null,credits);await env.DB.prepare("INSERT INTO settings VALUES('serper_key_cursor',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(String((index+1)%keys.length)).run();return {calls,body};}error=/not enough credits/i.test(String(body.message||body.error||''))?'SERPER_CREDITS_EXHAUSTED':r.status===401?'SERPER_UNAUTHORIZED':'SERPER_HTTP_'+r.status;credits=r.status<500?0:null;
  }catch{error='SERPER_NETWORK_ERROR';}
  await record(env,row,status,error,credits);if(['SERPER_CREDITS_EXHAUSTED','SERPER_UNAUTHORIZED'].includes(error))await env.DB.prepare("INSERT OR REPLACE INTO settings VALUES(?,'1')").bind('serper_exhausted_'+fingerprint).run();
 }
 if(error==='SERPER_CREDITS_EXHAUSTED')await env.DB.prepare("INSERT INTO settings VALUES('serper_paused','1') ON CONFLICT(key) DO UPDATE SET value='1'").run();return {calls,error};
}
async function record(env:Env,row:any,status:number|null,error:string|null,credits:number|null){await env.DB.prepare('INSERT INTO search_calls VALUES(?,?,?,?,?,?,?,?)').bind(crypto.randomUUID(),row.id,row.region_code,row.run_date,now(),status,error,credits).run();}
