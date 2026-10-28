const esc=(s:unknown)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export function referenceFooter(sources:any[],language:string){
 const labels:Record<string,string>={en:'Reference links',id:'Tautan rujukan',ja:'参考リンク',ko:'참고 링크',zh:'参考链接',vi:'Liên kết tham khảo',th:'ลิงก์อ้างอิง',pt:'Links de referência',es:'Enlaces de referencia',ar:'روابط مرجعية'};
 const links=(sources||[]).filter(s=>{try{return ['http:','https:'].includes(new URL(s.url).protocol)}catch{return false}});
 if(!links.length)return '';
 return '<blockquote><p><strong>'+esc(labels[language.split('-')[0]]||labels.en)+'</strong></p><ul>'+links.map((s,i)=>'<li><a href="'+esc(s.url)+'">'+esc(s.title||(!/^(?:https?:\/\/)?[\w.-]+\.[a-z]{2,}(?:\/|$)/i.test(s.source_name||'')&&s.source_name)||'Reference '+(i+1))+'</a></li>').join('')+'</ul></blockquote>';
}
