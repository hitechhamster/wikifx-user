import unittest,json,os
from unittest.mock import patch
import app
from news_policy import messages,validate,limits
from material_policy import writing_material
EN='The regulator warned investors about a fraudulent investment platform. Traders should verify the identity of the company before sending money. '
class Response:
 status_code=200
 def __init__(self,body):self.body=body
 def json(self):return {'choices':[{'message':{'content':json.dumps({'title':'Regulator Warns Traders About Fraudulent Investment Platform','meta_description':'The regulator warned investors about the platform.','body':self.body,'keywords':['risk']})}}],'usage':{'prompt_tokens':10,'completion_tokens':20},'model':'deepseek-flash'}
class Tests(unittest.TestCase):
 def setUp(self):
  patcher=patch('app.review_article',return_value={'state':'complete','issues':[],'count':0,'usage':{},'model':'deepseek-flash'});patcher.start();self.addCleanup(patcher.stop)

 def data(self):return {'item':{'title':'Platform warning','summary':'The regulator warned investors.','url':'https://example.com/news','source_name':'Example','content_status':'unavailable','sources':[]},'region':{'name':'Malaysia','language':'English','languageId':'en'}}
 def test_prompt(self):
  m,t=writing_material(self.data()['item']);p=messages(m,self.data()['region'],t);self.assertIn('120—250',p[0]['content']);self.assertIn('700—1000',p[0]['content']);self.assertEqual(json.loads(p[1]['content'])['material']['type'],'news');self.assertNotIn('最多100词',p[0]['content'])
 def test_no_investment_advice_policy(self):
  m,t=writing_material(self.data()['item']);p=messages(m,self.data()['region'],t)[0]['content']
  for term in ['影响范围','止损止盈','资产配置','开启双重验证','标明出处','不向私人账户转账']:
   self.assertIn(term,p)
  self.assertNotIn('对交易者意味着什么',p)
  self.assertNotIn('具体、可操作',p)
 def test_language(self):
  self.assertTrue(app.language_ok(EN*5,'en')[0]);self.assertTrue(app.language_ok('日本銀行は政策金利を据え置いた。市場では円相場の変動に警戒が広がっている。投資家は今後の金融政策を注視する必要がある。','ja')[0]);self.assertFalse(app.language_ok(EN*5,'ja')[0])
 def test_partial_body(self):
  m,t=writing_material({**self.data()['item'],'content_status':'partial','content':'PARTIAL_BODY'});self.assertEqual(m['content'],'PARTIAL_BODY');self.assertFalse(t)
 def test_retry_residue_and_usage(self):
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'local-test'}),patch('app.requests.post',side_effect=[Response('<p>## Broken marker</p>'),Response('<p>'+EN*20+'</p>')]) as call:
   r=app.generate(self.data());self.assertEqual(r['state'],'complete');self.assertEqual(call.call_count,2);self.assertEqual(r['usage']['prompt_tokens'],20);self.assertNotIn('##',r['content'])
 def test_http_failure_has_no_fallback(self):
  bad=Response('');bad.status_code=503
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'local-test'}),patch('app.requests.post',return_value=bad) as call:
   r=app.generate(self.data());self.assertEqual(r['state'],'failed');self.assertEqual(call.call_count,1);self.assertEqual(call.call_args.args[0],'https://api.deepseek.com/chat/completions')
 def test_json_retry_and_cost(self):
  bad=Response('');bad.json=lambda:{'choices':[{'message':{'content':'bad JSON'}}],'usage':{'prompt_tokens':10,'completion_tokens':20,'cost':.01}}
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'local-test'}),patch('app.requests.post',side_effect=[bad,Response('<p>'+EN*20+'</p>')]) as call:
   r=app.generate(self.data());self.assertEqual(r['state'],'complete');self.assertEqual(call.call_count,2);self.assertAlmostEqual(r['usage']['estimated_cost_usd'],.010027);self.assertIn('fact_check',r)
 def test_fact_retry_keeps_red_draft(self):
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'local-test'}),patch('app.requests.post',return_value=Response('<p>'+EN*20+' Unfounded Bank lost 999 million, 888 million, 777 million, and 666 million.</p>')) as call:
   r=app.generate(self.data());self.assertEqual(r['state'],'complete');self.assertEqual(call.call_count,2);self.assertTrue(r['fact_check']['review_alert']);self.assertTrue(r['fact_check']['regeneration_triggered'])
 def test_fact_retry_can_clear(self):
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'local-test'}),patch('app.requests.post',side_effect=[Response('<p>'+EN*20+' Unfounded Bank lost 999 million, 888 million, 777 million, and 666 million.</p>'),Response('<p>'+EN*20+'</p>')]) as call:
   r=app.generate(self.data());self.assertEqual(call.call_count,2);self.assertFalse(r['fact_check']['review_alert']);self.assertEqual(r['fact_check']['count'],0)
 def test_meta_retry_returns_red_review(self):
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'local-test'}),patch('app.requests.post',return_value=Response('<p>'+EN*20+' What is not established: available material is limited.</p>')) as call:
   r=app.generate(self.data());self.assertEqual(call.call_count,2);self.assertEqual(r['state'],'complete');self.assertTrue(r['editorial_check']['review_alert']);self.assertGreater(r['editorial_check']['meta_hits_total'],0);self.assertNotIn('<strong>Sources',r['content']);self.assertTrue(r['sources'])
 def test_title_language(self):
  with self.assertRaisesRegex(ValueError,'TITLE_LANGUAGE_MISMATCH'):validate('<p>'+EN+'</p>','警告有人冒充监管专员',True,'id')
 def test_meta_and_limits(self):
  for body in ['<p>Available information remains limited.</p>','<p>## leftover</p>','<p>**leftover**</p>']:
   with self.assertRaises(ValueError):validate(body,'Title',True,'en')
  self.assertEqual(limits(True,'ja'),(800,1100))
if __name__=='__main__':unittest.main()
