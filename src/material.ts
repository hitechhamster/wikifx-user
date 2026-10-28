export function insufficientMaterial(p:any,sourceSystem:string){
 const corroboration=(p.sources||[]).some((s:any)=>s.evidence_status==='search_snippet'||sourceSystem==='wikifx-signal'&&s.url!==p.url&&!!s.summary?.trim());
 return p.content_status==='unavailable'&&!corroboration;
}
export function within48Hours(p:any,reference=Date.now()){
 const published=Date.parse(p.published_at||'');return !Number.isFinite(published)||reference-published<=48*3600000;
}
export function selectThree(items:any[]){
 const sorted=[...items].sort((a,b)=>Number(a.scope==='major_cross')-Number(b.scope==='major_cross')||Number(!!a.insufficient||!!a.unverified)-Number(!!b.insufficient||!!b.unverified)||b.appeal_score-a.appeal_score||Number(b.business)-Number(a.business));
 const keys=new Set<string>(),urls=new Set<string>(),selected:any[]=[];
 for(const x of sorted){if(x.scope==='major_cross'&&selected.some(y=>y.scope==='major_cross')||keys.has(x.event_key)||urls.has(x.url)||selected.some(y=>sameTranslatedHeadline(x,y)))continue;keys.add(x.event_key);urls.add(x.url);selected.push(x);if(selected.length===3)break;}return selected;
}

export function sameTranslatedHeadline(a:any,b:any){
 const clean=(x:any)=>String(x.title_zh||'').replace(/[^\p{L}\p{N}]/gu,'');let x=clean(a),y=clean(b);if(!x||!y)return false;if(x===y)return true;if(x.length>y.length)[x,y]=[y,x];if(x.length<12||x.length/y.length<.7)return false;
 if(JSON.stringify(x.match(/\d+/g)||[])!==JSON.stringify(y.match(/\d+/g)||[]))return false;
 let i=0;for(const c of y)if(c===x[i])i++;return i===x.length;
}
