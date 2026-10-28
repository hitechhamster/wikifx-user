// Manual invocation only; no scheduler or credentials on this machine.
import {execFile} from 'node:child_process';import {promisify} from 'node:util';import fs from 'node:fs';
const exec=promisify(execFile),kind=process.argv[2],prefix=process.argv[3];if(!['radar-repair-region','preselect'].includes(kind)||!prefix)throw Error('Usage: node scripts/run-radar-round.mjs <kind> <unique-prefix>');
const regions=['KR','VN','TH','ID','BR','AR','LA','JP','TW','SA','MY','AF','CN'],results=[];
for(let i=0;i<regions.length;i+=3){await Promise.all(regions.slice(i,i+3).map(async region=>{const id=prefix+'-'+region.toLowerCase();try{await exec(process.execPath,['node_modules/wrangler/bin/wrangler.js','workflows','trigger','wikifx-signal-pipeline',JSON.stringify({kind,date:'2026-10-26',region,...(process.argv[4]?{cachedRun:process.argv[4]+'-'+region.toLowerCase()}: {})}),'--id',id]);results.push({region,id,queued:true});console.log(region+' queued');}catch{results.push({region,id,queued:false});console.log(region+' failed to queue');}}));}
fs.writeFileSync('artifacts/'+prefix+'-workflows.json',JSON.stringify(results,null,2));
