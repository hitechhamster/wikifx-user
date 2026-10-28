import unittest,json,os
from unittest.mock import patch
from editorial_checks import editorial_checks
from ai_audit import review_article
class EditorialTests(unittest.TestCase):
 def test_ten_languages(self):
  for phrase in ['未提及','not established','スニペット','입력된 자료','belum dikonfirmasi','ยังไม่ได้รับการยืนยัน','chưa được xác nhận','não está confirmado','no se detalla','ما لا تتضمنه']:
   with self.subTest(phrase=phrase):self.assertGreater(editorial_checks('<p>'+phrase+'</p>')['meta_count'],0)
 def test_markup_and_news_attribution(self):
  self.assertEqual(editorial_checks('<p>According to Reuters, the regulator issued a warning.</p>')['count'],0)
  self.assertEqual(editorial_checks('<p>## Header **emphasis**</p>')['markdown_count'],3)
 def test_ai_review_rejects_unanchored_quote(self):
  class Response:
   status_code=200
   def json(self):return {'choices':[{'message':{'content':json.dumps({'issues':[{'field':'content','quote':'invented quote','reason':'bad','evidence_quote':''}]})}}],'usage':{'prompt_tokens':10,'completion_tokens':10}}
  with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'}),patch('ai_audit.requests.post',return_value=Response()):
   r=review_article({'title':'News','summary':'Actual','content':'Actual content'},{'summary':'Actual content'},{'language':'English'});self.assertEqual(r['state'],'needs_check');self.assertEqual(r['count'],0);self.assertEqual(r['unanchored_issues'],1)
if __name__=='__main__':unittest.main()
