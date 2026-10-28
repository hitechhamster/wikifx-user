"""Cloudflare-only writer. No collection, searches, source fetches or CMS requests."""
import ast
import html
import json
import os
import re
import threading
from pathlib import Path
from flask import Flask, request, jsonify
from waitress import serve
import requests
import markdown
import bleach
from lingua import LanguageDetectorBuilder
from legacy.polish import tidy
from material_policy import writing_material
from fact_check import check_article
from editorial_checks import editorial_checks
from ai_audit import review_article
from news_policy import messages,validate,count_units,limits

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
detector = LanguageDetectorBuilder.from_all_languages().with_low_accuracy_mode().build()
jobs = {}
lock = threading.Lock()
ALLOWED = ['p','h2','h3','strong','em','ul','ol','li','a','blockquote']

def language_ok(text, target):
    clean = bleach.clean(text, tags=[], strip=True)
    language = detector.detect_language_of(clean)
    actual = language.iso_code_639_1.name.lower() if language else ''
    if actual and actual != target.split('-')[0]:
        from lingua import Language
        expected = next((x for x in Language.all() if x.iso_code_639_1.name.lower() == target.split('-')[0]), None)
        if expected:
            precise = LanguageDetectorBuilder.from_languages(language, expected).build().detect_language_of(clean)
            actual = precise.iso_code_639_1.name.lower() if precise else actual
    return actual == target.split('-')[0], actual

def generate(data):
    item,region=data['item'],data['region'];material,thin=writing_material(item)
    if data.get('review_only'):
        return {'state':'complete','ai_review':review_article(data['article'],material,region)}
    base=messages(material,region,thin);usage={};last_error='ARTICLE_GENERATION_FAILED';fact_history=[];fact_feedback='';format_retries=0;fact_retried=False;editorial_retried=False;editorial_history=[]
    for attempt in range(3):
        prompt=base+([{'role':'user','content':'上一版未通过校验：'+last_error+fact_feedback+'。请按原始素材重新生成，尤其遵守目标语言、新闻写法和HTML格式，不要提及校验过程。'}] if attempt else [])
        payload={'model':os.environ.get('WRITER_MODEL','deepseek-flash'),'temperature':.3,'thinking':{'type':'disabled'},'max_tokens':14000,'response_format':{'type':'json_object'},'messages':prompt}
        try:
            response=requests.post('https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']},json=payload,timeout=(10,240))
        except requests.RequestException:
            return {'state':'failed','error':'DEEPSEEK_NETWORK_ERROR','usage':usage,'model':payload['model'],'attempts':attempt+1}
        if response.status_code!=200:return {'state':'failed','error':'DEEPSEEK_HTTP_'+str(response.status_code),'usage':usage,'model':payload['model'],'attempts':attempt+1}
        result=response.json()
        current_usage=result.get('usage') or {}
        call_cost=current_usage.get('cost')
        if not isinstance(call_cost,(int,float)):
            hit=current_usage.get('prompt_cache_hit_tokens',0);call_cost=(hit*.006+(current_usage.get('prompt_tokens',0)-hit)*.3+current_usage.get('completion_tokens',0)*1.2)/1e6
        usage['estimated_cost_usd']=usage.get('estimated_cost_usd',0)+call_cost
        for k,v in result.get('usage',{}).items():
            if isinstance(v,(int,float)):usage[k]=usage.get(k,0)+v
        stage='parse';article=None
        try:
            article=json.loads(result['choices'][0]['message']['content'])
            if any(not isinstance(article.get(k),str) or not article[k].strip() for k in ('title','meta_description','body')):raise ValueError('ARTICLE_FIELDS_EMPTY')
            body=article['body']
            # The lead has no heading; retain only content-section headings.
            body=re.sub(r'\A\s*#{1,3} [^\n]+\n+', '', body)
            article['body']=body
            content=bleach.clean(markdown.markdown(body),tags=ALLOWED,attributes={'a':['href','title']},protocols=['https','http'],strip=True)
            stage='policy'
            units=validate(content,article['title'],thin,region['languageId'],allow_editorial_warnings=True)
            for sample in [content,article['title']+' '+article['meta_description']+' '+content]:
                ok,actual=language_ok(sample,region['languageId'])
                if not ok:raise ValueError('LANGUAGE_MISMATCH_'+actual)
            original=item.get('content') if item['content_status']=='full' else item.get('summary')
            if original and any(len(p.strip())>180 and p.strip() in original for p in re.split(r'[\n]',bleach.clean(content,tags=[],strip=True))):raise ValueError('SOURCE_COPY_DETECTED')
            if units<25:raise ValueError('ARTICLE_TOO_SHORT')
            stage='facts'
            facts=check_article(article['title'],article['meta_description'],content,material)
            policy=editorial_checks(content,article['title'],article['meta_description'])
            editorial_history.append({'attempt':attempt+1,**policy})
            fact_history.append({'attempt':attempt+1,'count':facts['count'],'title_unmatched':facts['title_unmatched']})
            facts['regeneration_triggered']=fact_retried
            facts['history']=fact_history
            if (facts['needs_retry'] or policy['count']) and not editorial_retried:
                editorial_retried=True
                fact_retried=bool(facts['needs_retry'])
                last_error='EDITORIAL_REWRITE_REQUIRED'
                fact_feedback='。以下片段没有素材依据，请删除或改为素材明确支持的事实：'+json.dumps([{'field':f['field'],'text':f['text']} for f in facts['findings']],ensure_ascii=False)+'。禁止的元叙述或格式问题：'+json.dumps(policy['issues'],ensure_ascii=False)
                continue
            facts['review_alert']=facts['needs_retry']

            stage='sources'
            links=list({s['url']:s for s in [{'url':item['url'],'source_name':item['source_name']}]+item.get('sources',[])}.values())
            permitted={s['url'] for s in links}
            content=re.sub(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',lambda m:m.group(0) if html.unescape(m[1]) in permitted else m[2],content,flags=re.S)
            audit=review_article({'title':article['title'],'summary':article['meta_description'],'content':content},material,region)
            policy['history']=editorial_history
            policy['regeneration_triggered']=editorial_retried
            policy['meta_hits_total']=sum(x['meta_count'] for x in editorial_history)
            return {'state':'complete','article':article,'content':content,'usage':usage,'model':result.get('model'),'detected_language':actual,'word_count':units,'length_short':units<limits(thin,region['languageId'])[0],'attempts':attempt+1,'prompt_version':'news-v6-no-meta','fact_check':facts,'editorial_check':policy,'ai_review':audit,'sources':links}
        except (ValueError,KeyError,TypeError) as exc:
            format_retries+=1
            if str(exc)=='TOO_MANY_HEADINGS':fact_feedback+='。最多4个小标题，删除多余小标题但保留事实正文。'
            last_error=str(exc) if re.fullmatch(r'[A-Z_]+(?:_[a-z]+)?',str(exc)) else ('ARTICLE_JSON_INVALID' if isinstance(exc,json.JSONDecodeError) else 'ARTICLE_VALIDATION_'+stage.upper()+'_'+type(exc).__name__.upper())
            if format_retries>1:break
    return {'state':'failed','error':last_error,'usage':usage,'model':result.get('model'),'attempts':attempt+1,'diagnostic_article':article,'fact_history':fact_history,'editorial_history':editorial_history}

def run(job_id,data):
    try:result=generate(data)
    except Exception as exc:
        # Never serialize raw SDK/network exceptions: they may contain headers.
        result={'state':'failed','error':str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z_0-9]+',str(exc)) else 'ARTICLE_GENERATION_FAILED'}
    with lock:jobs[job_id]=result

@app.get('/health')
def health():return jsonify(ok=True)

@app.post('/jobs/<job_id>')
def start(job_id):
    if not os.environ.get('DEEPSEEK_API_KEY'):return jsonify(error='DEEPSEEK_NOT_CONFIGURED'),503
    with lock:
        if job_id not in jobs:
            if any(j['state']=='running' for j in jobs.values()):return jsonify(error='BUSY'),429
            jobs[job_id]={'state':'running'}
            threading.Thread(target=run,args=(job_id,request.get_json()),daemon=True).start()
    return jsonify(state=jobs[job_id]['state']),202

@app.get('/jobs/<job_id>')
def status(job_id):return jsonify(jobs.get(job_id,{'state':'missing'}))

if __name__=='__main__':serve(app,host='0.0.0.0',port=8080,threads=4)
