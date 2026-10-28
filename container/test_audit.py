import unittest
from ai_audit import equivalent_date_issue,normal_attribution_issue
class ReviewEquivalence(unittest.TestCase):
 def test_mid_october(self):
  issue={'quote':'The transactions took place over three days in mid-October.','reason':'日期模糊'}
  self.assertTrue(equivalent_date_issue(issue,{'summary':'Transfers occurred between October 15 and 17.'}))
  self.assertFalse(equivalent_date_issue(issue,{'summary':'October 2–4.'}))
 def test_attribution(self):
  self.assertTrue(normal_attribution_issue({'category':'meta_narration','quote':'That is the read from a macro account'}))
  self.assertFalse(normal_attribution_issue({'category':'investment_advice','quote':'According to readers, buy now'}))
if __name__=='__main__':unittest.main()
