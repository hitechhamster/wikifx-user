import {z} from 'zod';
import {regions} from './regions';
const chars=(n:number)=>z.string().refine(s=>Array.from(s).length<=n,'too_long');
const nonempty=z.string().trim().min(1);
const time=z.string().datetime({offset:true});
const url=chars(3000).refine(s=>{try{const u=new URL(s);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password&&!['localhost','127.0.0.1','::1'].includes(u.hostname)&&u.pathname!=='/';}catch{return false;}},'public_article_url_required');
const source=z.object({source_name:chars(200),title:chars(500),url,summary:chars(2000).nullable()});
export const itemSchema=z.object({
 topic_id:nonempty.max(500),title:chars(500).refine(s=>!!s.trim()),content:chars(60000).nullable(),
 content_format:z.literal('text/plain'),content_status:z.enum(['full','partial','unavailable']),
 content_error:z.object({code:nonempty.max(100),message:nonempty.max(1000)}).nullable(),content_fetched_at:time.nullable(),
 summary:chars(2000).nullable(),summary_origin:z.enum(['source','excerpt','unavailable']),url,source_name:chars(200).refine(s=>!!s.trim()),
 ranking:z.record(z.string(),z.unknown()).optional(),article_type:chars(200).nullable().optional(),language:nonempty.max(30),published_at:time.nullable(),discovered_at:time,category:chars(200).nullable().optional(),original_url:url.optional(),sources:z.array(source).max(100).optional()
}).superRefine((x,c)=>{
 if(x.content_status==='full'&&(!x.content?.trim()||x.content_error!==null||!x.content_fetched_at))c.addIssue({code:'custom',message:'full requires body, timestamp and null error',path:['content_status']});
 if(x.content_status==='partial'&&(!x.content?.trim()||!x.content_error||!x.content_fetched_at))c.addIssue({code:'custom',message:'partial requires body, timestamp and error',path:['content_status']});
 if(x.content_status==='unavailable'&&(x.content!==null||!x.content_error||x.content_fetched_at!==null))c.addIssue({code:'custom',message:'unavailable requires null body/time and error',path:['content_status']});
 if((x.summary_origin==='unavailable')!==(x.summary===null)||x.summary!==null&&!x.summary.trim())c.addIssue({code:'custom',message:'summary origin mismatch',path:['summary_origin']});
});
export const batchSchema=z.object({schema_version:z.literal('1.0'),source_system:z.enum(['wikifx-hotspot-radar','wikifx-signal']),batch_id:z.uuid(),snapshot_id:nonempty.max(200).refine(s=>!s.includes('\\')&&!s.startsWith('/')),data_date:z.iso.date(),timezone:z.literal('Asia/Shanghai'),region_code:z.string().refine(s=>regions.some(r=>r.code===s),'INVALID_REGION'),region_name:nonempty,selection_scope:z.enum(['candidate_topics','ai_top_topics','ai_topic_groups']),revision:z.number().int().min(1),collection_status:z.enum(['completed','partial','not_ready','not_scheduled','failed']),report_origin:z.enum(['scheduled','same_day_reused']).nullable(),report_generated_at:time.nullable(),window_hours:z.literal(24),page_no:z.number().int().min(1),page_count:z.number().int().min(1).max(10000),total_items:z.number().int().min(0).nullable(),items:z.array(itemSchema).max(50),warnings:z.array(chars(2000)).max(100)}).superRefine((b,c)=>{
 const bad=(message:string)=>c.addIssue({code:'custom',message});
 if(b.region_name!==regions.find(r=>r.code===b.region_code)?.name)bad('region_name mismatch');
 if(b.page_no>b.page_count)bad('page_no exceeds page_count');
 if(new Set(b.items.map(i=>i.topic_id)).size!==b.items.length)bad('duplicate topic_id');
 if(['not_ready','not_scheduled','failed'].includes(b.collection_status)){
   if(b.items.length||b.total_items!==null||b.page_no!==1||b.page_count!==1||b.report_origin!==null||b.report_generated_at!==null)bad('status notification must have no report/items');
 }else if(b.total_items===null||!b.report_origin||!b.report_generated_at||b.total_items<b.items.length||b.total_items===0&&(b.page_count!==1||b.items.length))bad('invalid report totals or metadata');
});
export type Batch=z.infer<typeof batchSchema>;
export function canonical(v:unknown):string {if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,x])=>JSON.stringify(k)+':'+canonical(x)).join(',')+'}';return JSON.stringify(v);}
export async function hash(s:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))).map(x=>x.toString(16).padStart(2,'0')).join('');}
export class HttpError extends Error{constructor(public status:number,public code:string,message:string){super(message);}}
export const fail=(s:number,c:string,m:string):never=>{throw new HttpError(s,c,m);};
export const json=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
