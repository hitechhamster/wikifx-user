import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
const base='http://127.0.0.1:8787',date=new Date(Date.now()+8*3600000).toISOString().slice(0,10),b=JSON.parse(await readFile(new URL('./example.json',import.meta.url),'utf8'));
Object.assign(b,{batch_id:crypto.randomUUID(),snapshot_id:crypto.randomUUID(),data_date:date,revision:Date.now()});
// Reset only this test's local TH fixture. Production is never addressed by this script.
execFileSync(process.execPath,['node_modules/wrangler/bin/wrangler.js','d1','execute','wikifx-signal-hub','--local','--command',`DELETE FROM submission_jobs WHERE item_id IN(SELECT id FROM content_items WHERE region_code='TH' AND run_date='${date}'); DELETE FROM review_picks WHERE region_code='TH' AND run_date='${date}'; DELETE FROM region_reviews WHERE region_code='TH' AND run_date='${date}'; DELETE FROM content_items WHERE region_code='TH' AND run_date='${date}';`],{stdio:'pipe'});
async function push(page){const r=await fetch(base+'/api/v1/hotspots/daily-batches',{method:'POST',headers:{Authorization:'Bearer test-only-radar','Content-Type':'application/json','Idempotency-Key':page.batch_id+':'+page.page_no},body:JSON.stringify(page)});assert.equal(r.status,201,await r.text());}
async function state(){return (await (await fetch(base+'/api/review')).json()).regions.find(r=>r.code==='TH');}
async function action(path,body,expected){const r=await fetch(base+'/api/review/'+path,{method:'POST',headers:{'Content-Type':'application/json',Origin:base},body:JSON.stringify(body)});const j=await r.json();assert.equal(r.status,expected,JSON.stringify(j));return j;}
await push(b);let th=await state(),item=th.items[0];
await action('pick',{id:item.id,picked:true,reviewed_by:''},422);
await action('pick',{id:item.id,picked:true,reviewed_by:'TEST_REVIEWER'},200);
const later=structuredClone(b);later.batch_id=crypto.randomUUID();later.snapshot_id=crypto.randomUUID();later.revision++;later.items.forEach(x=>x.title='LATE_CHANGED_'+x.title);await push(later);
th=await state();assert.equal(th.items.find(x=>x.id===item.id).title,item.title,'picked region must freeze');
await action('skip',{region:'TH',skipped:true,reviewed_by:'TEST_REVIEWER'},200);th=await state();assert.equal(th.state,'skipped');assert.equal(th.items.filter(x=>x.picked).length,0);
await action('pick',{id:item.id,picked:true,reviewed_by:'TEST_REVIEWER'},409);
await action('skip',{region:'TH',skipped:false,reviewed_by:'TEST_REVIEWER'},200);
await action('pick',{id:item.id,picked:true,reviewed_by:'TEST_REVIEWER'},200);
await action('submit',{ids:[item.id],reviewed_by:'TEST_REVIEWER'},202);
for(let i=0;i<9;i++)await action('submit',{ids:[item.id],reviewed_by:'TEST_REVIEWER'},202);
await action('submit',{ids:[item.id],reviewed_by:'TEST_REVIEWER'},429);
console.log('PASS: reviewer required; late-data freeze; skip/undo; queued selection; duplicate submission; 10/min IP limit');
