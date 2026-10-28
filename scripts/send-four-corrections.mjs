import fs from 'node:fs';import {wrangler} from './wrangler-bounded.mjs';import {chromium} from 'playwright';
const root='artifacts/send-four-corrections';fs.mkdirSync(root,{recursive:true});
async function sql(s){return JSON.parse(await wrangler(['d1','execute','wikifx-signal-hub','--remote','--command',s,'--json']));}
const rows=(await sql("SELECT k.*,j.id job_id,j.state,c.region_code FROM article_corrections k JOIN submission_jobs j ON j.item_id=k.item_id JOIN content_items c ON c.id=k.item_id WHERE k.original_hub_id IN ('215','217','221','222')"))[0].results;
if(rows.length!==4||rows.some(x=>!['draft','approved'].includes(x.state)))throw Error('Unexpected scope/state');fs.writeFileSync(root+'/before.json',JSON.stringify(rows,null,2));
const browser=await chromium.launch({headless:true,channel:'chrome'});try{const page=await browser.newPage();await page.goto('https://review.wikifxusers.com');
for(const r of rows){const data=await page.evaluate(async job=>{const r=await fetch('/api/articles/'+job);return r.json()},r.job_id);if(data.image?.state!=='succeeded'&&data.image?.status!=='succeeded')throw Error('Cover not ready '+r.region_code+' '+JSON.stringify(data.image));}
await sql("UPDATE article_corrections SET release_confirmed=1 WHERE original_hub_id IN ('215','217','221','222')");
async function post(action,body){const result=await page.evaluate(async({action,body})=>{const r=await fetch('/api/review/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,reviewed_by:'wikifx'})});return {status:r.status,body:await r.json()}},{action,body});if(result.status>=300)throw Error(JSON.stringify(result));return result;}
for(const r of rows)await post('approve',{id:r.item_id,approved:true});const sent=await post('submit',{ids:rows.map(r=>r.item_id)});fs.writeFileSync(root+'/submitted.json',JSON.stringify(sent,null,2));console.log(JSON.stringify(sent));
}finally{await browser.close()}

