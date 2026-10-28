import os, tempfile, unittest
from fleet_db import connect,seed,rows,record_check,record_bunkering,record_sample,update_alert,tank,reset_demo,delete_sample,delete_review,delete_bunkering
from core import mcda_weights,ILLUSTRATIVE_LIMITS

class IntegratedTests(unittest.TestCase):
    def setUp(self):
        self.f=tempfile.TemporaryDirectory()
        self.cn=connect(os.path.join(self.f.name,'test.db'));seed(self.cn)
        self.t=rows(self.cn,"SELECT * FROM tanks WHERE vessel_id='TG02' AND name='Port'")[0]
    def tearDown(self): self.cn.close();self.f.cleanup()
    def review(self,**updates):
        kw=dict(vessel='TG02',tank_id=self.t['id'],incoming_blend=50,planned_l=800,coq_ref='COQ-TEST',approved=True,compatible=True,approval_ref='EVIDENCE-TEST',reviewer='Engineer',notes='Synthetic')
        kw.update(updates)
        return record_check(self.cn,**kw)
    def test_first_cycle_starts_empty(self):
        first=rows(self.cn,"SELECT * FROM tanks WHERE vessel_id='TG01' AND name='Port'")[0]
        self.assertEqual(first['volume_l'],0)
        self.assertEqual(first['age_days'],0)

    def test_delete_unused_review(self):
        review_id,_=self.review()
        delete_review(self.cn,review_id=review_id,tank_id=self.t['id'])
        self.assertEqual(len(rows(self.cn,'SELECT * FROM checks')),0)

    def test_cannot_delete_used_review(self):
        review_id,_=self.review()
        record_bunkering(self.cn,check_id=review_id,actual_rob=1000,actual_delivered=800,elapsed_days=3,bdn_ref='BDN',sample_ref='S',supplier='X',notes='')
        with self.assertRaises(ValueError):
            delete_review(self.cn,review_id=review_id,tank_id=self.t['id'])

    def test_reverse_latest_bunkering_restores_tank(self):
        original=tank(self.cn,self.t['id'])
        review_id,_=self.review()
        bunkering_id,_,_=record_bunkering(self.cn,check_id=review_id,actual_rob=1000,actual_delivered=800,elapsed_days=3,bdn_ref='BDN',sample_ref='S',supplier='X',notes='')
        delete_bunkering(self.cn,bunkering_id=bunkering_id,tank_id=self.t['id'])
        restored=tank(self.cn,self.t['id'])
        for col in ('volume_l','age_days','blend_pct'):
            self.assertEqual(original[col],restored[col])
        self.assertEqual(len(rows(self.cn,'SELECT * FROM bunkerings')),0)
        self.assertEqual(len(rows(self.cn,'SELECT * FROM alerts')),0)

    def test_reverse_bunkering_with_sample_blocked(self):
        review_id,_=self.review()
        bunkering_id,_,_=record_bunkering(self.cn,check_id=review_id,actual_rob=1000,actual_delivered=800,elapsed_days=3,bdn_ref='BDN',sample_ref='S',supplier='X',notes='')
        record_sample(self.cn,vessel='TG02',tank_id=self.t['id'],taken_at='2026-10-28',ref='S',laboratory='Lab',method_ref='M',water=100,tan=.1,oxidation=12,limits=ILLUSTRATIVE_LIMITS,weights=mcda_weights(),notes='')
        with self.assertRaises(ValueError):
            delete_bunkering(self.cn,bunkering_id=bunkering_id,tank_id=self.t['id'])

    def test_reset_restores_demo_state(self):
        self.review()
        self.assertEqual(len(rows(self.cn,'SELECT * FROM checks')),1)
        result=reset_demo(self.cn)
        self.assertEqual(result,{'vessels':5,'tanks':10})
        self.assertEqual(len(rows(self.cn,'SELECT * FROM checks')),0)
        first=rows(self.cn,"SELECT * FROM tanks WHERE vessel_id='TG01' AND name='Port'")[0]
        self.assertEqual(first['volume_l'],0)
        other=rows(self.cn,"SELECT * FROM tanks WHERE vessel_id='TG05' AND name='Port'")[0]
        self.assertEqual(other['age_days'],35)

    def test_seed(self):self.assertEqual(len(rows(self.cn,'SELECT * FROM vessels')),5)
    def test_check(self):self.assertEqual(self.review()[1],'Reviewed')
    def test_incomplete_check(self):self.assertEqual(self.review(coq_ref='')[1],'Pending')
    def test_exceeds_approval(self):self.assertEqual(self.review(incoming_blend=100,approved=False)[1],'Pending')
    def test_exceeds_capacity(self):
        with self.assertRaises(ValueError):self.review(planned_l=5001)
    def test_unreviewed_block(self):
        i,_=self.review(compatible=False)
        with self.assertRaises(ValueError):self.cn.execute('BEGIN') if False else record_bunkering(self.cn,check_id=i,actual_rob=1000,actual_delivered=800,elapsed_days=0,bdn_ref='BDN1',sample_ref='S1',supplier='S',notes='')
    def test_bunkering_update(self):
        i,_=self.review()
        _,b,a=record_bunkering(self.cn,check_id=i,actual_rob=1000,actual_delivered=800,elapsed_days=10,bdn_ref='BDN1',sample_ref='S1',supplier='S',notes='')
        self.assertAlmostEqual(b,(1000*20+800*50)/1800)
        self.assertAlmostEqual(a,1000*20/1800)
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
        _,res=record_sample(self.cn,vessel='TG02',tank_id=self.t['id'],taken_at='2026-10-27',ref='S',laboratory='Demo lab',method_ref='Demo methods',water=300,tan=.3,oxidation=10,limits=ILLUSTRATIVE_LIMITS,weights=mcda_weights(),notes='')
        self.assertAlmostEqual(res['score'],65.8,delta=1.0)
    def test_limit_breach_alert(self):
        _,res=record_sample(self.cn,vessel='TG02',tank_id=self.t['id'],taken_at='2026-10-27',ref='S',laboratory='Demo lab',method_ref='Demo methods',water=600,tan=.3,oxidation=10,limits=ILLUSTRATIVE_LIMITS,weights=mcda_weights(),notes='')
        self.assertIn('Water',res['breaches']);self.assertEqual(len(rows(self.cn,'SELECT * FROM alerts')),1)
    def test_delete_only_selected_duplicate_reference(self):
        args=dict(vessel='TG02', tank_id=self.t['id'], taken_at='2026-10-28',
                  ref='TG01-01', laboratory='Demo lab', method_ref='TEST',
                  water=250, tan=0.2, limits=ILLUSTRATIVE_LIMITS,
                  weights=mcda_weights(), notes='synthetic')
        first,_=record_sample(self.cn,oxidation=9,**args)
        second,_=record_sample(self.cn,oxidation=5,**args)
        self.assertEqual(len(rows(self.cn,'SELECT * FROM samples')),2)
        self.assertEqual(len(rows(self.cn,'SELECT * FROM alerts')),1)
        self.assertEqual(delete_sample(self.cn,sample_id=second,tank_id=self.t['id']),1)
        existing=rows(self.cn,'SELECT * FROM samples')
        self.assertEqual(len(existing),1)
        self.assertEqual(existing[0]['id'],first)
        self.assertEqual(len(rows(self.cn,'SELECT * FROM alerts')),0)

    def test_delete_wrong_tank_rejected(self):
        sample_id,_=record_sample(self.cn,vessel='TG02',tank_id=self.t['id'],
          taken_at='2026-10-28',ref='S1',laboratory='L',method_ref='M',
          water=100,tan=.1,oxidation=11,limits=ILLUSTRATIVE_LIMITS,
          weights=mcda_weights(),notes='')
        other=rows(self.cn,"SELECT * FROM tanks WHERE vessel_id='TG03' LIMIT 1")[0]
        with self.assertRaises(ValueError):
            delete_sample(self.cn,sample_id=sample_id,tank_id=other['id'])
        self.assertEqual(len(rows(self.cn,'SELECT * FROM samples')),1)

    def test_existing_db_migration(self):
        import sqlite3
        path=os.path.join(self.f.name,'legacy.db')
        c=sqlite3.connect(path)
        c.execute("CREATE TABLE alerts(id INTEGER PRIMARY KEY, vessel_id TEXT, tank_id INTEGER, created_at TEXT, category TEXT, severity TEXT, details TEXT, status TEXT, owner TEXT, action TEXT, closed_at TEXT)")
        c.commit(); c.close()
        upgraded=connect(path)
        self.assertIn('sample_id',[x[1] for x in upgraded.execute('PRAGMA table_info(alerts)')])
        upgraded.close()

    def test_alert_close_requires_action(self):
        self.cn.execute("INSERT INTO alerts(vessel_id,created_at,category,severity,details,status) VALUES('TG01','x','Demo','Review','x','Open')")
        aid=rows(self.cn,'SELECT * FROM alerts')[0]['id']
        with self.assertRaises(ValueError):update_alert(self.cn,aid,'Closed','','')
        update_alert(self.cn,aid,'Closed','Engineer','Investigated')
        self.assertEqual(rows(self.cn,'SELECT * FROM alerts')[0]['status'],'Closed')

if __name__=='__main__': unittest.main(verbosity=2)
