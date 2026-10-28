import unittest,datetime,json
from convert import pages
class ConverterTest(unittest.TestCase):
 def report(self,n):return {'generated_at':'2026-10-26T09:30:00+08:00','topics':[{'label':'FX','lead':{'url':f'https://example.com/a/{i}','text':'currency news','platform':'news'},'evidence':{'sources':[]}} for i in range(n)]}
 def test_merge_paging_and_idempotency(self):
  source={'india':self.report(50),'pakistan':self.report(20),'indonesia':self.report(5),'global':self.report(8)};a=pages(source,'2026-10-26');b=pages(source,'2026-10-26');self.assertEqual(a,b);sa=[p for p in a['pages'] if p['region_code']=='SA'];self.assertEqual([len(p['items']) for p in sa],[50,20]);self.assertEqual(len({x['topic_id'] for p in sa for x in p['items']}),70)
 def test_missing_markets_are_failed_not_empty_success(self):
  a=pages({},'2026-10-26');self.assertEqual(len(a['pages']),3);self.assertTrue(all(p['collection_status']=='failed' and p['total_items'] is None for p in a['pages']))
 def test_partial_sa(self):self.assertEqual(next(p for p in pages({'india':self.report(3)},'2026-10-26')['pages'] if p['region_code']=='SA')['collection_status'],'partial')
if __name__=='__main__':unittest.main()
