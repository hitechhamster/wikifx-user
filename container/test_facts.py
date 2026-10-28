import unittest
from fact_check import check_article,number
class Facts(unittest.TestCase):
 def test_units(self):
  self.assertEqual(number('2.4 million'),number('240万'))
  self.assertEqual(number('2,400,000'),number('2,4 juta'))
  self.assertEqual(number('1.234,50'),number('1,234.50'))
 def test_flags(self):
  r=check_article('OJK warns','Losses reached 3 million.','<p>Acme Bank reported 8.2% on 27/10/2026.</p>',{'summary':'OJK reported 8.2% on 26/10/2026; losses were 2 million.'})
  self.assertTrue(any(x['text']=='27/10/2026' for x in r['findings']))
  self.assertTrue(any(x['text']=='Acme Bank' for x in r['findings']))
  self.assertFalse(any(x['text']=='8.2%' for x in r['findings']))
 def test_alias_dates_and_markup(self):
  r=check_article('Fed','2 million','<p>27 October 2026</p>',{'summary':'美联储 200万 2026-10-27'})
  self.assertEqual(r['count'],0)
 def test_derivation_is_explicit(self):
  r=check_article('','', '<p>200 USD is 4 times 50 USD.</p>',{'summary':'Amounts: 200 USD and 50 USD.'})
  self.assertEqual(r['count'],0);self.assertEqual(r['derived_count'],1);self.assertIn('200',r['derived'][0]['formula'])
  r=check_article('','', '<p>The fee was 4.</p>',{'summary':'Amounts: 200 USD and 50 USD.'})
  self.assertEqual(r['count'],1);self.assertEqual(r['derived_count'],0)
 def test_weight_conversion(self):
  r=check_article('','', '<p>2 kg</p>',{'summary':'2000 grams'})
  self.assertEqual(r['count'],0);self.assertEqual(r['derived_count'],1)
 def test_words_and_percent_decimal(self):
  self.assertEqual(number('1.234%'),('percent','1.234'))
  r=check_article('','', '<p>three banks, 八万元, 10月27日</p>',{'summary':'3 banks; 80000 yuan; October 27'})
  self.assertEqual(r['count'],0)
 def test_title_retry_threshold(self):
  self.assertTrue(check_article('999 million','','',{'summary':'2 million'})['needs_retry'])
  self.assertFalse(check_article('','','999 million',{'summary':'2 million'})['needs_retry'])
 def test_vietnamese_dates_and_month(self):
  r=check_article('','', '<p>ngày 21 tháng 10; tháng 12</p>',{'summary':'October 21; December'})
  self.assertEqual(r['count'],0)
 def test_security_phrase_not_numeric_event(self):
  r=check_article('','', '<p>Aktifkan verifikasi dua langkah.</p>',{'summary':'Security reminder'})
  self.assertEqual(r['count'],0)
 def test_month_abbreviations_not_english_verbs(self):
  r=check_article('','', '<p>They set out plans.</p>',{'summary':'Plans'})
  self.assertEqual(r['count'],0)
 def test_computed_unit_price(self):
  r=check_article('','', '<p>Rp2,4 juta per gram</p>',{'summary':'Rp61,95 miliar for 25,88 kg.'})
  self.assertEqual(r['count'],0);self.assertEqual(r['derived_count'],1);self.assertEqual(r['derived'][0]['operation'],'unit_price')
 def test_low_false_positive_scope(self):
  r=check_article('Bulls Face Await Fed','One Two Three','<h2>Await Fed Bulls Face 999</h2><p>one two satu dois Fed ECB FOMC Banco Central</p>',{'summary':'Nothing numeric'})
  self.assertEqual([x['text'] for x in r['findings']],['999']);self.assertFalse(r['title_unmatched'])
 def test_explicit_title_names_still_checked(self):
  self.assertTrue(check_article('Acme Bank lost 999','','',{'summary':'No matching evidence'})['title_unmatched'])
  self.assertTrue(any(x['kind']=='name' for x in check_article('Sanae Takaichi','','',{'summary':'No name'})['findings']))
if __name__=='__main__':unittest.main()
