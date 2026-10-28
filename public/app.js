let data=null,filter='all',busy=false;const expanded=new Set();
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const who=$('who');try{who.value=localStorage.getItem('reviewer')??'wikifx'}catch{who.value='wikifx'}
who.oninput=()=>{try{localStorage.setItem('reviewer',who.value)}catch{}render()};
async function load(){try{const r=await fetch('/api/review');if(!r.ok)throw Error('数据加载失败');data=await r.json();render();}catch(e){$('sum').textContent=e.message;}}
async function action(path,body){if(busy)return;busy=true;render();try{const r=await fetch('/api/review/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,reviewed_by:who.value.trim()})});const b=await r.json();if(!r.ok)throw Error(b.message||'操作失败');await load();}catch(e){alert(e.message);}finally{busy=false;render();}}
const hasRecommendations=r=>r.items.some(x=>x.ai_rank!=null);
function relativeTime(value){if(!value)return '';const d=new Date(value),ms=Date.now()-d.getTime();if(!Number.isFinite(ms))return '';const day=x=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(x);const time=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);if(ms<0)return time;if(day(d)===day(new Date()))return ms<60000?'刚刚':ms<3600000?Math.floor(ms/60000)+' 分钟前':Math.floor(ms/3600000)+' 小时前';if(day(d)===day(new Date(Date.now()-86400000)))return '昨天 '+time;return day(d)+' '+time;}
function recommendation(x){let facts=[];try{facts=JSON.parse(x.reason_facts_json||'[]')}catch{}return facts.length?(String(x.ai_reason||'').startsWith('【传闻】')?'【传闻】':'')+facts.map(f=>f.text).join(' · ')+(String(x.ai_reason||'').includes('官方来源')?' · 官方来源':''):(x.ai_rank?'待更新结构化推荐理由':'尚未推荐');}
const done=r=>r.state==='skipped'||r.items.some(x=>x.progress==='sent');
const progress={queued:'排队中',writing:'写稿中',sending:'送稿中',sent:'已送稿',failed:'失败',dry_run:'试运行完成 · 未送稿'};
function card(x){
 const locked=x.status!=='candidate',picked=!!x.picked;let status='';
 if(x.progress)status=`<span class="tag ${x.progress==='failed'?'rumor':'ok'}">${esc(progress[x.progress]||x.progress)}${x.error?' · '+esc(x.error):''}${x.hub_id?' · <a target="_blank" rel="noopener" href="https://editor.chouai.cc.cd/?articleId='+encodeURIComponent(x.hub_id)+'">Content Hub 查看</a>':''}</span>`;
 if(x.progress==="dry_run"&&x.job_id)status+=" <a class=tag target=_blank rel=noopener href=/api/articles/"+encodeURIComponent(x.job_id)+">查看试运行稿件 JSON</a>";
 return `<div class="row ${picked?'sel':''} ${x.progress==='sent'?'sent':''}"><label><input type="checkbox" data-pick="${esc(x.id)}" ${picked||locked?'checked':''} ${locked||busy?'disabled':''}><div><div class="t"><span class="rk">${x.ai_rank?'#'+x.ai_rank:'候选'}</span><span class="tt">${esc(x.title)}</span></div><div class="rs">${esc(recommendation(x))}</div><div class="tags"><span class="tag ${x.source_system==='wikifx-signal'?'S':'R'}">${x.source_system==='wikifx-signal'?'WikiFX Signal':'主站雷达'}</span><span class="tag">${esc(x.source)}</span>${x.relevance?'<span class="tag">相关度：'+esc(x.relevance)+'</span>':''}${x.lead_created_at?'<span class="tag">'+esc(relativeTime(x.lead_created_at))+'</span>':''}${status}</div></div></label><a class="orig" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">原文</a></div>`;
}
function render(){if(!data)return;
 const recommended=data.regions.filter(hasRecommendations),n=recommended.filter(done).length;$('total').textContent=recommended.length;$('done').textContent=n;$('pc').textContent=recommended.length-n;$('date').textContent=`${data.date} · 主站雷达 + WikiFX Signal · ${!data.writer_ready?'写稿服务待启用；送稿任务将排队等待':data.dry_run?'试运行：只写稿，不发送':'正式送稿'}`;
 $('fAll').classList.toggle('on',filter==='all');$('fPending').classList.toggle('on',filter==='pending');
 const unavailable=data.regions.filter(r=>['等待数据','未安排采集','采集失败'].includes(r.data_status)&&!hasRecommendations(r));
 $('list').innerHTML=data.regions.filter(r=>!unavailable.includes(r)&&(filter!=='pending'||hasRecommendations(r)&&!done(r))).sort((a,b)=>Number(hasRecommendations(b))-Number(hasRecommendations(a))).map(r=>{
  const skipped=r.state==='skipped',picked=r.items.filter(x=>x.picked||x.status==='selected').length;
  const txt=skipped?'今天不发':r.items.some(x=>x.progress==='sent')?'已送稿':picked?'已选 '+picked+' 条':'';
  const top=r.items.filter(x=>x.ai_rank!=null),rest=r.items.filter(x=>x.ai_rank==null);
  return `<section class="${skipped?'skipped':''}"><div class="rh"><span class="code">${r.code}</span><h2>${esc(r.name)}</h2><span class="st ${skipped?'skip':picked?'picked':r.data_status==='正常'?'pending':'none'}">${esc(txt)}</span><button class="skipbtn" data-skip="${r.code}" ${busy||r.items.some(x=>x.progress)?'disabled':''}>${skipped?'撤销今天不发':'今天不发'}</button></div>${skipped?'':r.data_status!=='正常'?'<div class="nodata">'+esc(r.data_status)+'</div>':(top.length?top.map(card).join(''):'<div class="nodata">正在等待 AI 推荐；也可以展开候选。</div>')+(rest.length?`<button class="more" data-more="${r.code}">${expanded.has(r.code)?'收起':'查看其余'} ${rest.length} 条候选</button>${expanded.has(r.code)?rest.map(card).join(''):''}`:'')}${r.warnings.length?'<div class="nodata">'+r.warnings.map(esc).join('；')+'</div>':''}</section>`;
 }).join('')||'<section><div class="nodata">暂无待处理推荐</div></section>';
 if(unavailable.length)$('list').innerHTML+='<div class="summary-row">'+['等待数据','未安排采集','采集失败'].map(status=>{const list=unavailable.filter(r=>r.data_status===status);return list.length?esc(status)+'：'+list.map(r=>esc(r.code)).join('、'):''}).filter(Boolean).join('　｜　')+'</div>';
 const picks=data.regions.flatMap(r=>r.items.filter(x=>x.picked)),remaining=Math.max(0,data.limit-data.used);
 const reason=!who.value.trim()?'请先填写审核人':picks.length>remaining?`每日上限 ${data.limit} 篇，今日剩余 ${remaining} 篇`:!remaining?'已达到今日送稿上限':picks.length?`已选 ${picks.length} 条，今日剩余 ${remaining} 篇`:`勾选要送稿的热点，今日剩余 ${remaining} 篇`;
 $('sum').textContent=reason;$('send').textContent=busy?'处理中…':`送稿${picks.length?' '+picks.length+' 条':''}`;$('send').disabled=busy||!who.value.trim()||!picks.length||picks.length>remaining;
}
$('list').onchange=e=>{if(e.target.dataset.pick)action('pick',{id:e.target.dataset.pick,picked:e.target.checked})};
$('list').onclick=e=>{if(e.target.dataset.more){const c=e.target.dataset.more;expanded.has(c)?expanded.delete(c):expanded.add(c);render();}if(e.target.dataset.skip){const r=data.regions.find(r=>r.code===e.target.dataset.skip);action('skip',{region:r.code,skipped:r.state!=='skipped'});}};
$('fAll').onclick=()=>{filter='all';render()};$('fPending').onclick=()=>{filter='pending';render()};
$('send').onclick=()=>action('submit',{ids:data.regions.flatMap(r=>r.items.filter(x=>x.picked).map(x=>x.id))});
load();setInterval(()=>{if(!busy)load()},10000);
