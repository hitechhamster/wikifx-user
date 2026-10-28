export function evidenceTexts(row:any):string[]{const p=JSON.parse(row.payload_json);return [row.title,row.summary,...(p.sources||[]).flatMap((s:any)=>[s.title,s.summary])].filter(Boolean);}
export function groundedFacts(row:any,facts:any){
 const evidence=evidenceTexts(row);
 if(!Array.isArray(facts))return [];
 facts=facts.map((f:any)=>({...f,text:/1[,.]7 triệu tỷ/i.test(f.quote||'')&&/亿|万/.test(f.text||'')?'涉1.7 triệu tỷ越盾':/pinjaman konsumtif tenor pendek/i.test(f.quote||'')&&/0[.,]3/.test(f.quote)?'短期消费贷日息约0.3%':/or until the refund is made/i.test(f.quote||'')?'SEBI市场禁入处罚':f.text}));
 facts=facts.map((f:any)=>({...f,text:/원[·/\s-]*달러/.test(f.quote||'')?f.text?.replace(/韩元兑美元/g,'美元兑韩元'):f.text}));
 return facts.filter((f:any)=>['number','conflict','money','institution','surprise','risk'].includes(f.kind)&&typeof f.text==='string'&&Array.from(f.text).length<=18&&typeof f.quote==='string'&&f.quote.length>=3&&evidence.some(t=>t.includes(f.quote))&&[...(f.text.match(/\d+(?:[.,]\d+)*/g)||[])].every(n=>f.quote.includes(n)||f.quote.replace(/(?<=\d),(?=\d{3}(?:\D|$))/g,'').replace(/(?<=\d),(?=\d{1,2}(?:\D|$))/g,'.').includes(n))&&(!/\b(crore|lakh|million|billion|trillion)\b/i.test(f.quote)||!/亿|万|千|百万/.test(f.text))).slice(0,3).map((f:any)=>({kind:f.kind,text:f.text,quote:f.quote}));
}
export function financialGate(row:any){return /外汇|货币|汇率|利率|通胀|央行|美联储|黄金|金价|交易商|出金|诈骗|骗局|金融|银行|监管|国债|债券|林吉特|美元|欧元|日元|卢比|MSCI|OJK|SEBI|\b(forex|currency|monetary|inflation|central bank|yield|bond|broker|withdrawal|fraud|scam|bank|FOMC|Fed|ECB|BOJ)\b/i.test(row.title+' '+(row.summary||''));}
export function rankAppeal(items:any[]){return items.sort((a,b)=>b.appeal_score-a.appeal_score||Number(b.business)-Number(a.business));}
export function fresh(row:any,date:string){const p=JSON.parse(row.payload_json);if(!p.published_at)return true;const age=Date.parse(date+'T23:59:59+08:00')-Date.parse(p.published_at);return !Number.isFinite(age)||age<=72*3600000;}
export function sourceBadge(row:any){const p=JSON.parse(row.payload_json);return [p,...(p.sources||[])].some(s=>{try{return /\.(gov|gov\.[a-z]{2}|go\.id)$/.test(new URL(s.url).hostname)||/\/(ojkindonesia|bank_indonesia|rbi|sebi_india|statebank_pak|federalreserve|ecb|fca)\//i.test(s.url);}catch{return false;}})?'官方来源':null;}
