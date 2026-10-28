import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';import fs from 'node:fs';
const base='http://127.0.0.1:8787',date=new Date(Date.now()+8*3600000).toISOString().slice(0,10),prefix='two-step-'+crypto.randomUUID(),ids=[prefix+'-a',prefix+'-b'];
const wr=(args)=>execFileSync(process.execPath,['node_modules/wrangler/bin/wrangler.js',...args],{encoding:'utf8'});
const sql=s=>{const out=wr(['d1','execute','wikifx-signal-hub','--local','--command',s,'--json']);return JSON.parse(out)[0].results;};
for(const [i,id]of ids.entries())sql(`INSERT INTO content_items(id,region_code,source_system,run_date,topic_key,title,url,source,ai_rank,status,revision,payload_json,available) VALUES('${id}','KR','wikifx-signal','${date}','${id}','Test FX','https://example.com/${id}','Test',${i+1},'candidate',1,'{}',1)`);
async function get(){return await(await fetch(base+'/api/review')).json()}
async function action(path,body,status=200){const r=await fetch(base+'/api/review/'+path,{method:'POST',headers:{'Content-Type':'application/json',Origin:base},body:JSON.stringify({reviewed_by:'TEST',...body})});const b=await r.json();assert.equal(r.status,status,JSON.stringify(b));return b;}
let d=await get();assert.ok(d.regions.find(r=>r.code==='KR').items.find(x=>x.id===ids[0]).picked);
await action('pick',{id:ids[0],picked:false});assert.equal((await get()).regions.find(r=>r.code==='KR').items.find(x=>x.id===ids[0]).picked,null);await get();assert.equal(sql(`SELECT count(*) n FROM review_picks WHERE item_id='${ids[0]}'`)[0].n,0);
await action('pick',{id:ids[0],picked:true});await action('submit',{ids:[ids[0]]},409);
const g=await action('generate',{ids:[ids[0]]},202);assert.equal(sql(`SELECT count(*) n FROM delivery_jobs WHERE item_id='${ids[0]}'`)[0].n,0);assert.equal(sql(`SELECT count(*) n FROM generation_requests WHERE job_id='${g.jobs[0]}'`)[0].n,1);
await action('generate',{ids:[ids[0]]},202);assert.equal(sql(`SELECT count(*) n FROM generation_requests WHERE job_id='${g.jobs[0]}'`)[0].n,1);
const key='test-two-step/'+prefix+'.json',file='artifacts/'+prefix+'.json';fs.writeFileSync(file,JSON.stringify({title:'【联调测试】Test FX',summary:'Evidence summary',content:'<p>Test</p>',externalId:'test-old'}));wr(['r2','object','put','wikifx-signal-archive/'+key,'--local','--file',file]);sql(`UPDATE submission_jobs SET state='ready',payload_key='${key}' WHERE id='${g.jobs[0]}'`);
await action('submit',{ids:[ids[0]]},202);const delivery=sql(`SELECT * FROM delivery_jobs WHERE item_id='${ids[0]}'`)[0];assert.match(delivery.external_id,/^signal-/);assert.equal(delivery.state,'queued');assert.equal((await get()).used,1);
await action('pick',{id:ids[0],picked:false});assert.equal(sql(`SELECT state FROM delivery_jobs WHERE id='${delivery.id}'`)[0].state,'cancelled');assert.equal((await get()).used,0);
const used=(await get()).generated;for(let i=used;i<100;i++)sql(`INSERT INTO generation_requests VALUES('${prefix}-quota-${i}',NULL,'${date}','${date}T21:00:00+08:00')`);
await action('generate',{ids:[ids[1]]},409);assert.equal((await get()).used,0);
console.log('PASS local only: default picks; persistent deselection; generate never sends; duplicate generation; ready-only send; live externalId; queued cancellation; independent 100/60 quotas');
