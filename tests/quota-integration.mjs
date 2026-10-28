import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';
const base='http://127.0.0.1:8787',date=new Date(Date.now()+8*3600000).toISOString().slice(0,10);
const sql=`WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<60) INSERT OR IGNORE INTO submission_jobs(id,item_id,external_id,run_date,reviewed_by,state,snapshot_json,dry_run,created_at,updated_at) SELECT 'quota-test-'||x,'quota-item-'||x,'quota-ext-'||x,'${date}','TEST','dry_run','{}',1,'${date}','${date}' FROM n;`;
function localSQL(s){execFileSync(process.execPath,['node_modules/wrangler/bin/wrangler.js','d1','execute','wikifx-signal-hub','--local','--command',s],{stdio:'pipe'});}
localSQL(sql);
try{
 const d=await(await fetch(base+'/api/review')).json(),i=d.regions.flatMap(r=>r.items).find(i=>i.status==='candidate');assert.ok(i);
 async function action(p,b){const r=await fetch(base+'/api/review/'+p,{method:'POST',headers:{Origin:base,'Content-Type':'application/json','CF-Connecting-IP':'192.0.2.15'},body:JSON.stringify({...b,reviewed_by:'TEST'})});return {status:r.status,body:await r.json()};}
 assert.equal((await action('pick',{id:i.id,picked:true})).status,200);
 const r=await action('submit',{ids:[i.id]});assert.equal(r.status,409);assert.equal(r.body.code,'DAILY_LIMIT');console.log('PASS: daily 60 article cap enforced on server');
}finally{localSQL("DELETE FROM submission_jobs WHERE id LIKE 'quota-test-%';");}
