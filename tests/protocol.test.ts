import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {batchSchema,canonical} from '../src/protocol';import {simpleDuplicate,localGate,rumor} from '../src/ai';
const example=JSON.parse(readFileSync(new URL('./example.json',import.meta.url),'utf8'));
test('document example validates',()=>assert.equal(batchSchema.safeParse(example).success,true));
test('invalid full body and incorrect status rejected',()=>{let b=structuredClone(example);b.items[0].content=null;assert.equal(batchSchema.safeParse(b).success,false);b=structuredClone(example);b.collection_status='not_ready';assert.equal(batchSchema.safeParse(b).success,false);});
test('status only and real zero are distinct',()=>{const b={...example,collection_status:'not_ready',items:[],total_items:null,report_origin:null,report_generated_at:null};assert.equal(batchSchema.safeParse(b).success,true);assert.equal(batchSchema.safeParse({...b,total_items:0}).success,false)});
test('canonical object ordering and changed payload',()=>{assert.equal(canonical({a:1,b:2}),canonical({b:2,a:1}));assert.notEqual(canonical({a:1}),canonical({a:2}))});
test('simple event grouping and tragedy filtering',()=>{assert.equal(simpleDuplicate({url:'a',title:'one'},{url:'a',title:'two'}),true);assert.equal(localGate('地震导致大量死亡',''),false);assert.equal(localGate('OJK 警示非法外汇平台',''),true)});
test('media corroboration clears rumor tag',()=>{assert.equal(rumor({url:'https://x.com/a/status/1',sources:[]}),true);assert.equal(rumor({url:'https://x.com/a/status/1',sources:[{url:'https://ojk.go.id/warning'}]}),false)});
