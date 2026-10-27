import os, tempfile, unittest
from fleet_db import connect,seed,rows,record_check,record_bunkering,record_sample,update_alert,tank
from core import mcda_weights,ILLUSTRATIVE_LIMITS

class IntegratedTests(unittest.TestCase):
    def setUp(self):
        self.f=tempfile.TemporaryDirectory()
        self.cn=connect(os.path.join(self.f.name,'test.db'));seed(self.cn)
        self.t=rows(self.cn,"SELECT * FROM tanks WHERE vessel_id='TG01' AND name='Port'")[0]
    def tearDown(self): self.cn.close();self.f.cleanup()
    def review(self,**updates):
        kw=dict(vessel='TG01',tank_id=self.t['id'],incoming_blend=50,planned_l=800,coq_ref='COQ-TEST',approved=True,compatible=True,approval_ref='EVIDENCE-TEST',reviewer='Engineer',notes='Synthetic')
        kw.update(updates)
        return record_check(self.cn,**kw)
    def test_seed(self):self.assertEqual(len(rows(self.cn,'SELECT * FROM vessels')),5)
    def test_check(self):self.assertEqual(self.review()[1],'Reviewed')
    def test_incomplete_check(self):self.assertEqual(self.review(coq_ref='')[1],'Pending')
    def test_exceeds_approval(self):self.assertEqual(self.review(incoming_blend=100)[1],'Pending')
    def test_exceeds_capacity(self):
        with self.assertRaises(ValueError):self.review(planned_l=5000)
    def test_unreviewed_block(self):
        i,_=self.review(compatible=False)
        with self.assertRaises(ValueError):self.cn.execute('BEGIN') if False else record_bunkering(self.cn,check_id=i,actual_rob=1000,actual_delivered=800,elapsed_days=0,bdn_ref='BDN1',sample_ref='S1',supplier='S',notes='')
    def test_bunkering_update(self):
        i,_=self.review()
        _,b,a=record_bunkering(self.cn,check_id=i,actual_rob=1000,actual_delivered=800,elapsed_days=10,bdn_ref='BDN1',sample_ref='S1',supplier='S',notes='')
        self.assertAlmostEqual(b,(1000*20+800*50)/1800)
        self.assertAlmostEqual(a,1000*24/1800)
        self.assertAlmostEqual(tank(self.cn,self.t['id'])['volume_l'],1800)
    def test_double_post_block(self):
        i,_=self.review()
        kw=dict(check_id=i,actual_rob=1000,actual_delivered=800,elapsed_days=0,bdn_ref='BDN1',sample_ref='S1',supplier='S',notes='')
        record_bunkering(self.cn,**kw)
        with self.assertRaises(ValueError):record_bunkering(self.cn,**kw)
    def test_rob_mismatch(self):
        i,_=self.review()
        with self.assertRaises(ValueError):record_bunkering(self.cn,check_id=i,actual_rob=900,actual_delivered=800,elapsed_days=0,bdn_ref='BDN1',sample_ref='S1',supplier='S',notes='')
    def test_sample(self):
        _,res=record_sample(self.cn,vessel='TG01',tank_id=self.t['id'],taken_at='2026-10-27',ref='S',laboratory='Demo lab',method_ref='Demo methods',water=300,tan=.3,oxidation=10,limits=ILLUSTRATIVE_LIMITS,weights=mcda_weights(),notes='')
        self.assertAlmostEqual(res['score'],65.8,delta=1.0)
    def test_limit_breach_alert(self):
        _,res=record_sample(self.cn,vessel='TG01',tank_id=self.t['id'],taken_at='2026-10-27',ref='S',laboratory='Demo lab',method_ref='Demo methods',water=600,tan=.3,oxidation=10,limits=ILLUSTRATIVE_LIMITS,weights=mcda_weights(),notes='')
        self.assertIn('Water',res['breaches']);self.assertEqual(len(rows(self.cn,'SELECT * FROM alerts')),1)
    def test_alert_close_requires_action(self):
        self.cn.execute("INSERT INTO alerts(vessel_id,created_at,category,severity,details,status) VALUES('TG01','x','Demo','Review','x','Open')")
        aid=rows(self.cn,'SELECT * FROM alerts')[0]['id']
        with self.assertRaises(ValueError):update_alert(self.cn,aid,'Closed','','')
        update_alert(self.cn,aid,'Closed','Engineer','Investigated')
        self.assertEqual(rows(self.cn,'SELECT * FROM alerts')[0]['status'],'Closed')

if __name__=='__main__': unittest.main(verbosity=2)
