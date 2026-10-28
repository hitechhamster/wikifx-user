import test from 'node:test';import assert from 'node:assert/strict';
import {deliver} from '../src/delivery';
async function scenario(status:number){
 const queries:string[]=[],requests:any[]=[],sleeps:string[]=[];const row={id:'delivery',mode:'test',state:'queued',attempts:0,external_id:'test-stable',payload_key:'payload',job_id:'job',item_id:'item'};
 const env:any={CONTENT_INGEST_TOKEN:'test-only',SUBMISSION_MODE:'dry_run',DB:{prepare(sql:string){queries.push(sql);return {bind(){return this},async first(){if(sql.includes('delivery_jobs'))return row;if(sql.includes('content_hub_test_delivery'))return {value:'delivery'};return null},async run(){return {meta:{changes:1}}}}},async batch(){return []}},ARCHIVE:{async get(){return {async json(){return {externalId:'test-stable',title:'test'}}}},async put(){}},COORDINATOR:{idFromName(){return 'hub'},get(){return {async fetch(){return Response.json({ok:true})}}}}};
 const step={async do(_name:string,...args:any[]){return args.at(-1)()},async sleep(name:string){sleeps.push(name)}};
 const original=globalThis.fetch;globalThis.fetch=async(url,init)=>{requests.push({url,init});return Response.json(status===201?{data:{id:'hub-123'}}:{error:'fixture failure'},{status})};
 try{return {result:await deliver(env,'delivery',step),queries,requests,sleeps}}finally{globalThis.fetch=original}
}
test('test delivery accepts 201, disables redirects, and never publishes production item',async()=>{const r=await scenario(201);assert.equal(r.result.id,'hub-123');assert.equal(r.requests.length,1);assert.equal(r.requests[0].init.redirect,'manual');assert.ok(!r.queries.some(q=>q.includes("status='published'")));});
test('400 is permanent and 401 pauses delivery',async()=>{for(const status of [400,401]){const r=await scenario(status);assert.equal(r.requests.length,1);assert.equal(r.sleeps.length,0);assert.equal(r.result.failed,true);if(status===401)assert.ok(r.queries.some(q=>q.includes("INSERT INTO settings VALUES('ingest_paused'")));}});
test('500 retries at most three times with unchanged idempotency payload',async()=>{const r=await scenario(500);assert.equal(r.requests.length,4);assert.equal(r.sleeps.length,3);assert.equal(new Set(r.requests.map(q=>q.init.body)).size,1);assert.equal(r.result.failed,true);});
