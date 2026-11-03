"""Supabase PostgreSQL datastore for the BHI research demonstrator.

Connects to the existing imported tables. No CREATE, DROP or automatic seed.
"""
from datetime import datetime, timezone, date
from decimal import Decimal
import psycopg
import streamlit as st


class HybridRow(dict):
    """Access fetched records by column name or positional index (SQLite-compatible)."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def hybrid_row(cursor):
    columns = [c.name for c in (cursor.description or ())]

    def make_row(values):
        normalized = []
        for v in values:
            if isinstance(v, Decimal):
                v = float(v)
            elif isinstance(v, (datetime, date)):
                v = v.isoformat()
            normalized.append(v)
        return HybridRow(zip(columns, normalized))
    return make_row


class QueryResult:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class Database:
    """Minimal adapter for existing SQLite-style calls used in app.py."""
    def __init__(self, connection):
        self.connection = connection
        self._transaction = None

    def execute(self, sql, params=()):
        # psycopg's percent placeholders require escaping literal SQL % symbols.
        statement = sql.replace('%', '%%').replace('?', '%s')
        is_insert = statement.lstrip().upper().startswith('INSERT INTO ')
        if is_insert and ' RETURNING ' not in statement.upper():
            statement = statement.rstrip().rstrip(';') + ' RETURNING id'
        cur = self.connection.execute(statement, params)
        if is_insert:
            created = cur.fetchone()
            return QueryResult(cur, created['id'] if created else None)
        return QueryResult(cur)

    def __enter__(self):
        self._transaction = self.connection.transaction()
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return self._transaction.__exit__(exc_type, exc_value, traceback)
        finally:
            self._transaction = None

    def close(self):
        self.connection.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect(path=None):
    """Connect to existing Supabase tables. `path` retained for app compatibility."""
    url = st.secrets['database']['url']
    cn = psycopg.connect(url, sslmode='require', connect_timeout=10,
                         row_factory=hybrid_row, autocommit=True)
    return Database(cn)


def seed(cn):
    """Do not reseed Supabase: existing imported data is authoritative."""
    return


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
        cur=cn.execute('''INSERT INTO bunkerings(vessel_id,tank_id,created_at,supplier,coq_ref,bdn_ref,sample_ref,incoming_blend,delivered_l,rob_l,old_blend,resulting_blend,resulting_age,approval_ref,compat_evidence,reviewer,notes,previous_age,previous_updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(check['vessel_id'],t['id'],now(),supplier,check['coq_ref'],bdn_ref,sample_ref,check['incoming_blend'],actual_delivered,actual_rob,t['blend_pct'],blend,new.age_days,check['approval_ref'],'Reviewer confirmed' if check['compatible'] else 'Pending',check['reviewer'],notes+f' [check:{check_id}]',t['age_days'],t['updated_at']))
        cn.execute('INSERT INTO alerts(vessel_id,tank_id,created_at,category,severity,details,status,bunkering_id) VALUES(?,?,?,?,?,?,?,?)',(check['vessel_id'],t['id'],now(),'Testing status','Review','New commingled tank condition not measured; representative sample required if indicated by monitoring policy.','Open',cur.lastrowid))
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


def delete_review(cn, *, review_id, tank_id):
    """Delete an unused review; never remove the approval trail of recorded bunkering."""
    with cn:
        r=cn.execute('SELECT * FROM checks WHERE id=? AND tank_id=?',(review_id,tank_id)).fetchone()
        if r is None: raise ValueError('Review not found for selected tank')
        used=cn.execute("SELECT 1 FROM bunkerings WHERE tank_id=? AND notes LIKE ?",(tank_id,f'%[check:{review_id}]%')).fetchone()
        if used: raise ValueError('This review was used for bunkering. Delete the associated bunkering first.')
        cn.execute('DELETE FROM checks WHERE id=? AND tank_id=?',(review_id,tank_id))


def delete_bunkering(cn, *, bunkering_id, tank_id):
    """Rollback only the latest bunkering when a reliable pre-event snapshot exists.

    Refuse if later samples or other transactions depend on this inventory state.
    Existing legacy records without saved snapshots are intentionally protected.
    """
    with cn:
        r=cn.execute('SELECT * FROM bunkerings WHERE id=? AND tank_id=?',(bunkering_id,tank_id)).fetchone()
        if r is None: raise ValueError('Bunkering record not found for selected tank')
        latest=cn.execute('SELECT MAX(id) FROM bunkerings WHERE tank_id=?',(tank_id,)).fetchone()[0]
        if r['id']!=latest: raise ValueError('Only the latest bunkering can be reversed, to preserve fuel history.')
        if r['previous_age'] is None or r['previous_updated_at'] is None:
            raise ValueError('This older record has no saved pre-bunkering age snapshot; safe reversal is unavailable. Reset the demo if necessary.')
        dependent=cn.execute('SELECT 1 FROM samples WHERE tank_id=? AND entered_at>=? LIMIT 1',(tank_id,r['created_at'])).fetchone()
        if dependent: raise ValueError('Tank samples were entered after this bunkering. Delete those samples first, then retry.')
        current=tank(cn,tank_id)
        expected=r['rob_l']+r['delivered_l']
        if abs(current['volume_l']-expected)>0.01 or abs(current['age_days']-r['resulting_age'])>1e-6:
            raise ValueError('Tank state has changed since the bunkering. Cannot safely reverse this record.')
        cn.execute('UPDATE tanks SET volume_l=?,blend_pct=?,age_days=?,updated_at=? WHERE id=?',
                   (r['rob_l'],r['old_blend'],r['previous_age'],r['previous_updated_at'],tank_id))
        cn.execute('DELETE FROM alerts WHERE bunkering_id=?',(bunkering_id,))
        cn.execute('DELETE FROM bunkerings WHERE id=? AND tank_id=?',(bunkering_id,tank_id))


def update_alert(cn,alert_id,status,owner,action):
    if status not in ('Open','Under review','Closed'): raise ValueError('Invalid status')
    if status=='Closed' and (not owner.strip() or not action.strip()): raise ValueError('Owner and action needed for closure')
    with cn:
        cn.execute('UPDATE alerts SET status=?,owner=?,action=?,closed_at=? WHERE id=?',(status,owner,action,now() if status=='Closed' else None,alert_id))


def reset_demo(cn):
    """Destructive reset is intentionally unavailable for the persistent database."""
    raise ValueError('Supabase reset is disabled to protect your recovered fleet data.')
