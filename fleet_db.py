"""SQLite demonstration datastore, synthetic entries only."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS vessels(id TEXT PRIMARY KEY, description TEXT, approved_max_fame REAL);
CREATE TABLE IF NOT EXISTS tanks(id INTEGER PRIMARY KEY AUTOINCREMENT,vessel_id TEXT NOT NULL,name TEXT NOT NULL,capacity_l REAL NOT NULL,volume_l REAL NOT NULL,blend_pct REAL NOT NULL,age_days REAL NOT NULL,updated_at TEXT NOT NULL, UNIQUE(vessel_id,name));
CREATE TABLE IF NOT EXISTS bunkerings(id INTEGER PRIMARY KEY AUTOINCREMENT, vessel_id TEXT NOT NULL,tank_id INTEGER NOT NULL,created_at TEXT NOT NULL, supplier TEXT, coq_ref TEXT, bdn_ref TEXT, sample_ref TEXT, incoming_blend REAL, delivered_l REAL, rob_l REAL, old_blend REAL, resulting_blend REAL, resulting_age REAL, approval_ref TEXT, compat_evidence TEXT, reviewer TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY AUTOINCREMENT, vessel_id TEXT NOT NULL,tank_id INTEGER NOT NULL,taken_at TEXT NOT NULL, entered_at TEXT NOT NULL, sample_ref TEXT, laboratory TEXT, method_ref TEXT, water REAL, tan REAL, oxidation REAL, bhi REAL, status TEXT, weight_model TEXT, limit_profile TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,vessel_id TEXT NOT NULL,tank_id INTEGER,created_at TEXT NOT NULL,category TEXT NOT NULL,severity TEXT NOT NULL,details TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Open',owner TEXT,action TEXT,closed_at TEXT,sample_id INTEGER);
CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY AUTOINCREMENT,vessel_id TEXT NOT NULL,tank_id INTEGER,created_at TEXT NOT NULL,incoming_blend REAL,planned_l REAL,coq_ref TEXT,approved INTEGER,compatible INTEGER,approval_ref TEXT,reviewer TEXT,notes TEXT,review_status TEXT);
'''

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect(path='fleet_demo.db'):
    cn=sqlite3.connect(str(path),check_same_thread=False)
    cn.row_factory=sqlite3.Row
    cn.execute('PRAGMA foreign_keys=ON')
    cn.executescript(SCHEMA)
    # Upgrade existing demo databases without discarding saved records.
    columns = {r[1] for r in cn.execute('PRAGMA table_info(alerts)')}
    if 'sample_id' not in columns:
        cn.execute('ALTER TABLE alerts ADD COLUMN sample_id INTEGER')
        cn.commit()
    return cn

def seed(cn):
    if cn.execute('SELECT count(*) FROM vessels').fetchone()[0]: return
    with cn:
        for v,maxb in [('TG01',50),('TG02',100),('TG03',30),('TG04',100),('TG05',50)]:
            cn.execute('INSERT INTO vessels VALUES(?,?,?)',(v,'Synthetic harbour tug',maxb))
            for t in ('Port','Starboard'):
                # TG01 starts before its first biofuel delivery (empty synthetic receiving tanks).
                # The other vessels demonstrate different pre-existing synthetic residence ages.
                starting_age = {'TG01': 0, 'TG02': 10, 'TG03': 12, 'TG04': 20, 'TG05': 35}[v]
                starting_volume = 0 if v == 'TG01' else 1000
                cn.execute('INSERT INTO tanks(vessel_id,name,capacity_l,volume_l,blend_pct,age_days,updated_at) VALUES(?,?,?,?,?,?,?)',
                           (v,t,5000,starting_volume,0 if v == 'TG01' else 20,starting_age,now()))

def rows(cn,query,args=()): return [dict(x) for x in cn.execute(query,args).fetchall()]

def tank(cn,tank_id):
    r=cn.execute('SELECT * FROM tanks WHERE id=?',(tank_id,)).fetchone()
    if not r: raise ValueError('Tank not found')
    return dict(r)

def record_check(cn,*,vessel,tank_id,incoming_blend,planned_l,coq_ref,approved,compatible,approval_ref,reviewer,notes):
    t=tank(cn,tank_id)
    if t['vessel_id']!=vessel: raise ValueError('Vessel/tank mismatch')
    if not 0<=incoming_blend<=100 or planned_l<=0 or t['volume_l']+planned_l>t['capacity_l']:
        raise ValueError('Invalid proposed delivery or tank capacity exceeded')
    maxblend=cn.execute('SELECT approved_max_fame FROM vessels WHERE id=?',(vessel,)).fetchone()[0]
    if incoming_blend>maxblend: approved=False
    status='Reviewed' if coq_ref.strip() and approved and compatible and approval_ref.strip() and reviewer.strip() else 'Pending'
    with cn:
        cur=cn.execute('INSERT INTO checks(vessel_id,tank_id,created_at,incoming_blend,planned_l,coq_ref,approved,compatible,approval_ref,reviewer,notes,review_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (vessel,tank_id,now(),incoming_blend,planned_l,coq_ref,int(approved),int(compatible),approval_ref,reviewer,notes,status))
    return cur.lastrowid,status

def record_bunkering(cn,*,check_id,actual_rob,actual_delivered,elapsed_days,bdn_ref,sample_ref,supplier,notes):
    from core import Tank, refuel
    with cn:
        check=cn.execute('SELECT * FROM checks WHERE id=?',(check_id,)).fetchone()
        if check is None or check['review_status']!='Reviewed': raise ValueError('A completed reviewed pre-bunkering record is required')
        if cn.execute('SELECT 1 FROM bunkerings WHERE notes LIKE ?',(f'%[check:{check_id}]%',)).fetchone():
            raise ValueError('This reviewed event has already been recorded')
        t=tank(cn,check['tank_id'])
        if abs(actual_rob-t['volume_l'])>0.01: raise ValueError('ROB differs from recorded tank inventory; reconcile tank first')
        if actual_delivered<=0 or elapsed_days<0 or actual_rob+actual_delivered>t['capacity_l']: raise ValueError('Invalid delivery, elapsed time, or capacity')
        if actual_delivered>check['planned_l']+0.01: raise ValueError('Actual volume exceeds approved planned quantity; new review required')
        if not bdn_ref.strip() or not sample_ref.strip(): raise ValueError('BDN and sample references are required')
        new=refuel(Tank(actual_rob,t['age_days']+elapsed_days),actual_delivered)
        blend=(actual_rob*t['blend_pct']+actual_delivered*check['incoming_blend'])/new.volume_l
        cn.execute('UPDATE tanks SET volume_l=?,blend_pct=?,age_days=?,updated_at=? WHERE id=?',(new.volume_l,blend,new.age_days,now(),t['id']))
        cur=cn.execute('''INSERT INTO bunkerings(vessel_id,tank_id,created_at,supplier,coq_ref,bdn_ref,sample_ref,incoming_blend,delivered_l,rob_l,old_blend,resulting_blend,resulting_age,approval_ref,compat_evidence,reviewer,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(check['vessel_id'],t['id'],now(),supplier,check['coq_ref'],bdn_ref,sample_ref,check['incoming_blend'],actual_delivered,actual_rob,t['blend_pct'],blend,new.age_days,check['approval_ref'],'Reviewer confirmed' if check['compatible'] else 'Pending',check['reviewer'],notes+f' [check:{check_id}]'))
        cn.execute('INSERT INTO alerts(vessel_id,tank_id,created_at,category,severity,details,status) VALUES(?,?,?,?,?,?,?)',(check['vessel_id'],t['id'],now(),'Testing status','Review','New commingled tank condition not measured; representative sample required if indicated by monitoring policy.','Open'))
        return cur.lastrowid,blend,new.age_days

def record_sample(cn,*,vessel,tank_id,taken_at,ref,laboratory,method_ref,water,tan,oxidation,limits,weights,notes):
    from core import calculate_bhi
    t=tank(cn,tank_id)
    if t['vessel_id']!=vessel: raise ValueError('Vessel/tank mismatch')
    if not ref.strip() or not laboratory.strip() or not method_ref.strip(): raise ValueError('Sample, laboratory and method references required')
    result=calculate_bhi(water,tan,oxidation,limits,weights)
    with cn:
        cur=cn.execute('''INSERT INTO samples(vessel_id,tank_id,taken_at,entered_at,sample_ref,laboratory,method_ref,water,tan,oxidation,bhi,status,weight_model,limit_profile,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(vessel,tank_id,taken_at,now(),ref,laboratory,method_ref,water,tan,oxidation,result['score'],result['status'],str(weights),str(limits),notes))
        if result['status']!='SCREENING NORMAL':
            cn.execute('INSERT INTO alerts(vessel_id,tank_id,created_at,category,severity,details,status,sample_id) VALUES(?,?,?,?,?,?,?,?)',(vessel,tank_id,now(),'Fuel quality','Priority' if result['breaches'] else 'Review',f"Sample {ref}: {result['status']}; BHI {result['score']:.1f}; breaches {', '.join(result['breaches']) or 'none'}. Requires superintendent assessment.",'Open',cur.lastrowid))
        return cur.lastrowid,result

def delete_sample(cn, *, sample_id, tank_id):
    """Delete exactly one selected tank sample and its explicitly linked alerts.

    Older alerts without a sample_id remain unchanged rather than risk deleting
    unrelated records that happen to reuse the same sample reference.
    """
    with cn:
        sample = cn.execute('SELECT id FROM samples WHERE id=? AND tank_id=?', (sample_id, tank_id)).fetchone()
        if sample is None:
            raise ValueError('Selected sample is not present in this tank')
        count = cn.execute('SELECT COUNT(*) FROM alerts WHERE sample_id=?', (sample_id,)).fetchone()[0]
        cn.execute('DELETE FROM alerts WHERE sample_id=?', (sample_id,))
        cn.execute('DELETE FROM samples WHERE id=? AND tank_id=?', (sample_id, tank_id))
    return count


def update_alert(cn,alert_id,status,owner,action):
    if status not in ('Open','Under review','Closed'): raise ValueError('Invalid status')
    if status=='Closed' and (not owner.strip() or not action.strip()): raise ValueError('Owner and action needed for closure')
    with cn:
        cn.execute('UPDATE alerts SET status=?,owner=?,action=?,closed_at=? WHERE id=?',(status,owner,action,now() if status=='Closed' else None,alert_id))


def reset_demo(cn):
    """Restore synthetic starter records in a single transaction; never delete schema."""
    with cn:
        for table in ('alerts', 'samples', 'bunkerings', 'checks', 'tanks', 'vessels'):
            cn.execute(f'DELETE FROM {table}')
    seed(cn)
    return {'vessels': cn.execute('SELECT COUNT(*) FROM vessels').fetchone()[0],
            'tanks': cn.execute('SELECT COUNT(*) FROM tanks').fetchone()[0]}
