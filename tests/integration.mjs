import assert from 'node:assert/strict';import {readFile,writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:8787',results=[];
const example=JSON.parse(await readFile(new URL('./example.json',import.meta.url),'utf8'));
example.batch_id=crypto.randomUUID();example.data_date='2026-01-'+String(1+Math.floor(Math.random()*27)).padStart(2,'0');example.snapshot_id=example.batch_id;example.revision=Date.now();
async function send(b,expected,label,token='test-only-radar'){const r=await fetch(base+'/api/v1/hotspots/daily-batches',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,'Idempotency-Key':b.batch_id+':'+b.page_no},body:JSON.stringify(b)});const body=await r.json();results.push({label,status:r.status,body});assert.equal(r.status,expected,label+': '+JSON.stringify(body));return body;}
const first=await send(example,201,'first');const duplicate=await send(example,200,'duplicate');assert.equal(first.data.receipt_id,duplicate.data.receipt_id);assert.equal(duplicate.data.duplicate_request,true);
await send({...example,warnings:['changed']},409,'idempotency conflict');
await send({...example,batch_id:crypto.randomUUID(),revision:example.revision-1},409,'stale revision');
await send({...example,batch_id:crypto.randomUUID()},409,'same revision different batch');
await send(example,401,'missing token','');
let multi={...example,batch_id:crypto.randomUUID(),snapshot_id:crypto.randomUUID(),revision:example.revision+1,page_count:2,items:[example.items[0]]};
await send(multi,201,'page 1');await send({...multi,page_no:2,items:[example.items[0]]},409,'cross page duplicate');await send({...multi,page_no:2,items:[example.items[1]],total_items:3},409,'page metadata conflict');await send({...multi,page_no:2,items:[example.items[1]]},201,'page 2');
let status={...example,batch_id:crypto.randomUUID(),snapshot_id:crypto.randomUUID(),revision:example.revision+2,collection_status:'not_ready',report_origin:null,report_generated_at:null,items:[],total_items:null};
await send(status,201,'not_ready');
await send({...status,batch_id:crypto.randomUUID(),revision:example.revision+3,total_items:0},422,'false zero rejected');
await writeFile(new URL('../artifacts/local-protocol-results.json',import.meta.url),JSON.stringify(results,null,2));console.log(results.map(x=>({test:x.label,status:x.status})));
