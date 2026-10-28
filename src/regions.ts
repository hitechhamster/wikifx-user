export const regions = [
 ['KR','韩国','韩语区 South Korea','Korean','ko'],['VN','越南','越南语 Vietnam','Vietnamese','vi'],
 ['TH','泰国','泰语组 Thailand','Thai','th'],['ID','印度尼西亚','印尼组 Indonesia','Indonesian','id'],
 ['BR','巴西','葡萄牙语组 Portuguese','Portuguese','pt'],['AR','中东／阿拉伯语区','中东组 Middle East','Arabic','ar'],
 ['LA','拉美／西班牙语区','西班牙语组 Spanish','Spanish','es'],['JP','日本','日语组 Japanese','Japanese','ja'],
 ['TW','台湾','台湾组','繁体中文','zh-HK'],['SA','南亚','南亚组 South Asia','English','en'],
 ['MY','马来西亚','马来西亚组 Malaysia','English','en'],['AF','非洲','非洲组','English','en'],
 ['CN','中国／简体中文市场','简体中文','简体中文','zh-CN'],['AU','澳洲','澳洲区 Australia','English','en'],
 ['SG','新加坡','新加坡英语区 Singapore English','English','en'],['NA','北美','北美区 North America','English','en'],
 ['EU','欧洲','欧洲区 Europe','English','en']
].map(([code,name,group,language,languageId])=>({code,name,group,language,languageId,scheduled:!['AU','SG','NA','EU'].includes(code)}));
export const marketRegions: Record<string,string> = {india:'SA',pakistan:'SA',indonesia:'ID',global:'MY'};
export const today=()=>new Date(Date.now()+8*3600000).toISOString().slice(0,10);
export const now=()=>new Date(Date.now()+8*3600000).toISOString().replace('Z','+08:00');
export const regionRule=(code:string)=>code==='MY'
 ? '马来西亚本地，或全球性外汇新闻：主要央行、主要货币、黄金、跨国诈骗。'
 : `必须与${regions.find(r=>r.code===code)?.name}本地区直接相关；仅全球性消息而没有本地关联不合格。SA包括印度、巴基斯坦等南亚地区。`;
