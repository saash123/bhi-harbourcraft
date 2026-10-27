import math
import unittest
from core import *

class BHITests(unittest.TestCase):
    def test_volume_and_age(self):
        x=refuel(advance(Tank(1000,20),10,800),800)
        self.assertEqual(x.volume_l,1000)
        self.assertAlmostEqual(x.age_days,6)
    def test_fresh_tank(self): self.assertEqual(refuel(Tank(0,20),500).age_days,0)
    def test_no_reset_5pct(self): self.assertAlmostEqual(refuel(Tank(50,30),950).age_days,1.5)
    def test_overconsume(self):
        with self.assertRaises(ValueError): advance(Tank(500,0),1,501)
    def test_zero_volume(self):
        with self.assertRaises(ValueError):refuel(Tank(0,0),0)
    def test_mcda_weights_sum(self): self.assertAlmostEqual(sum(mcda_weights().values()),100)
    def test_mcda_bad_rating(self):
        bad=DEFAULT_MCDA.copy();bad['TAN']=(0,3,4,4)
        with self.assertRaises(ValueError):mcda_weights(bad)
    def test_mcda_changes(self):
        a=mcda_weights(); b=DEFAULT_MCDA.copy(); b['TAN']=(5,5,5,5)
        self.assertNotAlmostEqual(a['TAN'],mcda_weights(b)['TAN'])
    def test_bhi_monotonic_water(self):
        w=mcda_weights();a=calculate_bhi(200,.3,10,ILLUSTRATIVE_LIMITS,w)['score'];b=calculate_bhi(400,.3,10,ILLUSTRATIVE_LIMITS,w)['score'];self.assertGreaterEqual(a,b)
    def test_bhi_monotonic_tan(self):
        w=mcda_weights();self.assertGreaterEqual(calculate_bhi(200,.2,10,ILLUSTRATIVE_LIMITS,w)['score'],calculate_bhi(200,.4,10,ILLUSTRATIVE_LIMITS,w)['score'])
    def test_bhi_monotonic_oxidation(self):
        w=mcda_weights();self.assertGreaterEqual(calculate_bhi(200,.2,12,ILLUSTRATIVE_LIMITS,w)['score'],calculate_bhi(200,.2,8,ILLUSTRATIVE_LIMITS,w)['score'])
    def test_breach_override(self):self.assertEqual(calculate_bhi(501,.1,20,ILLUSTRATIVE_LIMITS,mcda_weights())['status'],'REFERENCE LIMIT BREACH')
    def test_exact_limit_allowed(self): self.assertNotEqual(calculate_bhi(500,.5,8,ILLUSTRATIVE_LIMITS,mcda_weights())['status'],'REFERENCE LIMIT BREACH')
    def test_negative_rejected(self):
        with self.assertRaises(ValueError):calculate_bhi(-1,.2,8,ILLUSTRATIVE_LIMITS,mcda_weights())
    def test_mixed_repeated_topup(self):
        x=refuel(advance(Tank(1000,20),10,800),800)
        x=refuel(advance(x,7,500),500)
        self.assertAlmostEqual(x.age_days,6.5)
    def test_all_good_score(self):self.assertAlmostEqual(calculate_bhi(100,.1,20,ILLUSTRATIVE_LIMITS,mcda_weights())['score'],100)

if __name__=='__main__': unittest.main(verbosity=2)
