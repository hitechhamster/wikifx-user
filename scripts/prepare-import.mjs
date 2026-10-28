import {readFile,writeFile} from 'node:fs/promises';import {createHash,randomUUID} from 'node:crypto';
const date=process.argv[2];if(!/^\d{4}-\d{2}-\d{2}$/.test(date||''))throw Error('Usage: node scripts/prepare-import.mjs YYYY-MM-DD');
const markets={global:'MY',india:'SA',pakistan:'SA',indonesia:'ID'},names={MY:'马来西亚',SA:'南亚',ID:'印度尼西亚'},groups={},metadata=[];
for(const [market,region] of Object.entries(markets)){
 const report=JSON.parse(await readFile(`artifacts/daily/${market}.json`,'utf8'));if(report.date!==date)throw Error('REPORT_DATE_MISMATCH '+market);
 const generated=new Date(report.generated_at).toISOString();if(!groups[region])groups[region]={items:[],generated};if(generated>groups[region].generated)groups[region].generated=generated;
 for(const t of report.topics){const l=t.lead||{},u=new URL(l.url);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)throw Error('INVALID_SOURCE_URL');
  const topic_id=market+'-'+createHash('sha256').update(l.url).digest('hex').slice(0,32);
  const source_name=l.news_source||l.author_name||l.author||l.platform;
  const summary=(l.text||'').slice(0,2000)||null;
  const lang=/[\u0600-\u06ff]/.test(l.text)?'ur':/[\u0900-\u097f]/.test(l.text)?'hi':/\b(yang|dengan|adalah|untuk|terhadap|masyarakat|penipuan)\b/i.test(l.text)?'id':'en';
  groups[region].items.push({topic_id,title:(t.label||l.text||'').slice(0,500),content:null,content_format:'text/plain',content_status:'unavailable',content_error:{code:'not_fetched',message:'日报未保存可核验的完整主来源正文'},content_fetched_at:null,summary,summary_origin:summary?'excerpt':'unavailable',url:l.url,source_name:String(source_name).slice(0,200),language:lang,published_at:l.created_at?new Date(l.created_at).toISOString():null,discovered_at:generated,category:t.category?.id||null,sources:(t.evidence?.sources||[]).filter(s=>s.relevant&&s.url).map(s=>({source_name:String(s.source||new URL(s.url).hostname).slice(0,200),title:String(s.title||'').slice(0,500),url:s.url,summary:s.snippet?String(s.snippet).slice(0,2000):null}))});
  metadata.push({market,region,topic_id,heat:t.topic_score??null,opportunity_score:t.opportunity?.score??null,engagement_total:t.stats?.engagement_total||{}});
 }
}
const pages=[];
for(const [region,g] of Object.entries(groups)){
 const batch_id=randomUUID(),page_count=Math.max(1,Math.ceil(g.items.length/50));
 for(let p=0;p<page_count;p++)pages.push({schema_version:'1.0',source_system:'wikifx-signal',batch_id,snapshot_id:`signal-${region}-${date}-manual`,data_date:date,timezone:'Asia/Shanghai',region_code:region,region_name:names[region],selection_scope:'candidate_topics',revision:1,collection_status:'completed',report_origin:'same_day_reused',report_generated_at:g.generated,window_hours:24,page_no:p+1,page_count,total_items:g.items.length,items:g.items.slice(p*50,(p+1)*50),warnings:['本次复用杭州日报；discovered_at 为该日报记录时间，原始首次抓取时间未单独保存。正文未取得，summary 为主来源文本摘录。']});
}
await writeFile(`artifacts/manual-import-${date}.json`,JSON.stringify({date,pages,metadata},null,2),{flag:'wx'});
console.log(JSON.stringify({date,counts:Object.fromEntries(Object.entries(groups).map(([r,g])=>[r,g.items.length])),pages:pages.length}));
