"""Fleet BHI integrated research demonstration — synthetic data only."""
import os
import io
import zipfile
from datetime import date
import pandas as pd
import streamlit as st
from core import (mcda_weights, DEFAULT_MCDA, CRITERIA, PARAMETERS, FMEA,
                  calculate_bhi, ILLUSTRATIVE_LIMITS)
from fleet_db import connect, seed, rows, tank, record_check, record_bunkering, record_sample, update_alert

st.set_page_config(page_title='Harbour Craft | BHI Fleet Monitor',layout='wide',page_icon='⚓')
st.title('Biofuel Health Index · Fleet Management')
st.caption('Integrated bunkering, commingling and condition-monitoring research prototype | SYNTHETIC DATA ONLY')
st.warning('NOT an operational approval or fuel certificate. COQ and compatibility confirmation are documented evidence checks, not replaced by BHI. Default limits and scores are illustrative; actual grade limits, test methods and procedures must be verified. SQLite on free cloud hosting may reset: export your demo records.')
DB_PATH=os.environ.get('BHI_DB_PATH','fleet_demo.db')
cn=connect(DB_PATH)
seed(cn)
weights=mcda_weights()
limits=ILLUSTRATIVE_LIMITS.copy()

with st.sidebar:
    page=st.radio('Navigation',['Fleet Overview','1–2 · Pre-bunkering & COQ','3 · Compatibility & review','4 · Bunkering record','5 · Fuel quality & BHI','6 · Alerts & Power BI exports','Scientific validation'],label_visibility='visible')
    st.divider()
    st.caption('Research screening reference profile (NOT certified ISO/EN limits)')
    limits['Water']=st.number_input('Water max · mg/kg',min_value=0.01,value=500.0,step=10.0)
    limits['TAN']=st.number_input('TAN max · mg KOH/g',min_value=0.001,value=0.50,step=0.05)
    limits['Oxidation']=st.number_input('Oxidation min · h',min_value=0.01,value=8.0,step=0.5)
    st.caption('Keep actual fuel grades and applicable ISO 8217 specifications under qualified review.')

vessels=rows(cn,'SELECT * FROM vessels ORDER BY id')

def pick_vessel(key):
    v=st.selectbox('Vessel', [x['id'] for x in vessels],key=f'{key}v')
    ts=rows(cn,'SELECT * FROM tanks WHERE vessel_id=? ORDER BY name',(v,))
    tid=st.selectbox('Receiving tank', [x['id'] for x in ts], format_func=lambda k: next(x['name'] for x in ts if x['id']==k),key=f'{key}t')
    return v,tank(cn,tid)

if page=='Fleet Overview':
    st.subheader('Fleet overview')
    ss=rows(cn,'''SELECT t.*, (SELECT s.bhi FROM samples s WHERE s.tank_id=t.id ORDER BY s.id DESC LIMIT 1) last_bhi, (SELECT s.status FROM samples s WHERE s.tank_id=t.id ORDER BY s.id DESC LIMIT 1) last_status FROM tanks t ORDER BY t.vessel_id,t.name''')
    pending=cn.execute("SELECT COUNT(*) FROM alerts WHERE status!='Closed'").fetchone()[0]
    a,b,c=st.columns(3)
    a.metric('Vessels',len(vessels)); b.metric('Tanks monitored',len(ss)); c.metric('Open / under-review alerts',pending)
    frame=pd.DataFrame(ss)
    frame['Condition status']=frame['last_status'].fillna('UNVERIFIED — NO TANK SAMPLE')
    st.dataframe(frame[['vessel_id','name','volume_l','capacity_l','blend_pct','age_days','last_bhi','Condition status']].rename(columns={'vessel_id':'Vessel','name':'Tank','volume_l':'ROB (L)','capacity_l':'Capacity (L)','blend_pct':'Est. FAME %','age_days':'Recorded effective age (days)','last_bhi':'Last measured BHI'}),hide_index=True,use_container_width=True)
    st.info('BHI is reported only against a recorded sample. An old sample does not automatically represent the current tank mixture.')
    st.subheader('Latest bunkering transactions')
    st.dataframe(pd.DataFrame(rows(cn,'SELECT vessel_id,created_at,bdn_ref,delivered_l,resulting_blend,resulting_age FROM bunkerings ORDER BY id DESC LIMIT 15')),hide_index=True,use_container_width=True)

elif page=='1–2 · Pre-bunkering & COQ':
    st.subheader('Pre-bunkering assessment and supplier COQ')
    v,t=pick_vessel('pre')
    st.write(f"**Recorded ROB:** {t['volume_l']:,.0f} L · **Tank capacity:** {t['capacity_l']:,.0f} L · **Estimated existing blend:** B{t['blend_pct']:.1f} · **Effective age:** {t['age_days']:.2f} days")
    st.info('First verify tank inventory, incoming grade, vessel approval, supplier COQ and outstanding abnormal-condition records. A completed electronic review does not authorise transfer.')
    st.write('Continue to the Compatibility & review tab to create the formal reviewed event. This separation is only screen navigation within one integrated record.')
    st.dataframe(pd.DataFrame(rows(cn,'SELECT id,created_at,incoming_blend,planned_l,coq_ref,review_status FROM checks WHERE tank_id=? ORDER BY id DESC LIMIT 15',(t['id'],))),hide_index=True,use_container_width=True)

elif page=='3 · Compatibility & review':
    st.subheader('Single integrated fuel-compatibility review')
    v,t=pick_vessel('compat')
    maxb=next(x['approved_max_fame'] for x in vessels if x['id']==v)
    with st.form('compat_review'):
        c1,c2=st.columns(2)
        incoming=c1.selectbox('Incoming B grade (%)',[0,20,30,50,100],index=3)
        planned=c2.number_input('Planned delivery (L)',min_value=1.0,value=1000.0,step=50.0)
        coq=st.text_input('Supplier COQ reference (mandatory)')
        oem=st.checkbox('Vessel / engine approval confirmed for incoming grade and system')
        compat=st.checkbox('Fuel-to-fuel compatibility evidence reviewed and accepted')
        approval_ref=st.text_input('Approval / compatibility evidence reference')
        reviewer=st.text_input('Authorised reviewer name / ID')
        notes=st.text_area('Evidence review and comments (including concerns)',height=80)
        predicted=(t['volume_l']*t['blend_pct']+planned*incoming)/(t['volume_l']+planned)
        st.write(f"**Predicted homogeneous blend: B{predicted:.2f}** · **Expected tank: {t['volume_l']+planned:,.0f} L** · Vessel recorded approved maximum: B{maxb:.0f}")
        st.caption('Blend % is a volume-fraction approximation, not an experimental miscibility/stability test. The incoming grade must independently satisfy equipment approval.')
        submitted=st.form_submit_button('Save review decision')
    if submitted:
        try:
            checkid,status=record_check(cn,vessel=v,tank_id=t['id'],incoming_blend=incoming,planned_l=planned,coq_ref=coq,approved=oem,compatible=compat,approval_ref=approval_ref,reviewer=reviewer,notes=notes)
            (st.success if status=='Reviewed' else st.warning)(f'Review #{checkid}: {status}. '+('Proceed to recording completed bunkering only under approved operating procedures.' if status=='Reviewed' else 'Evidence incomplete or approval not established.'))
        except ValueError as ex: st.error(str(ex))
    st.dataframe(pd.DataFrame(rows(cn,'SELECT id,created_at,coq_ref,planned_l,incoming_blend,review_status FROM checks WHERE tank_id=? ORDER BY id DESC LIMIT 8',(t['id'],))),hide_index=True,use_container_width=True)

elif page=='4 · Bunkering record':
    st.subheader('Record completed bunkering and commingling')
    v,t=pick_vessel('bunk')
    checks=rows(cn,"SELECT * FROM checks WHERE tank_id=? AND review_status='Reviewed' AND NOT EXISTS (SELECT 1 FROM bunkerings b WHERE b.notes LIKE '%[check:' || checks.id || ']%') ORDER BY id DESC",(t['id'],))
    if not checks:
        st.warning('No unused reviewed pre-bunkering records for this tank. Complete the compatibility review first.')
    else:
        cid=st.selectbox('Reviewed pre-bunkering event',[x['id'] for x in checks],format_func=lambda i:next(f"Review #{x['id']} · {x['coq_ref']} · {x['planned_l']:,.0f} L planned" for x in checks if x['id']==i))
        chosen=next(x for x in checks if x['id']==cid)
        with st.form('bunk_form'):
            rob=st.number_input('Verified ROB before transfer (L)',min_value=0.0,value=float(t['volume_l']))
            qty=st.number_input('Actual delivered volume (L)',min_value=0.01,value=float(chosen['planned_l']))
            elapsed=st.number_input('Elapsed days since inventory age timestamp (days)',min_value=0.0,value=0.0,help='Use 0 if ages were already updated to the current bunkering date. Avoid double-counting elapsed time.')
            supplier=st.text_input('Supplier')
            bdn=st.text_input('Bunker delivery note reference')
            sample=st.text_input('Representative sample / seal reference')
            notes=st.text_area('Observations (do not enter confidential real fleet data)')
            posted=st.form_submit_button('Reconcile and save bunkering')
        if posted:
            try:
                rid,blend,age=record_bunkering(cn,check_id=cid,actual_rob=rob,actual_delivered=qty,elapsed_days=elapsed,bdn_ref=bdn,sample_ref=sample,supplier=supplier,notes=notes)
                st.success(f'Saved BDN transaction #{rid}. Estimated blend B{blend:.2f}; effective age {age:.3f} days. Chemical condition UNVERIFIED pending representative measurements.')
                st.rerun()
            except ValueError as ex: st.error(str(ex))
    st.caption('Transfer and sampling take place under the operator’s existing safety procedures. This app is only a recordkeeping and decision-support tool.')
    st.dataframe(pd.DataFrame(rows(cn,'SELECT id,created_at,bdn_ref,delivered_l,resulting_blend,resulting_age FROM bunkerings WHERE tank_id=? ORDER BY id DESC LIMIT 15',(t['id'],))),hide_index=True,use_container_width=True)

elif page=='5 · Fuel quality & BHI':
    st.subheader('Representative sample assessment')
    v,t=pick_vessel('sample')
    st.warning('Do not copy incoming COQ values into the commingled tank sample. The new tank condition must be supported by a relevant, representative sample result.')
    with st.form('sample_form'):
        x,y=st.columns(2)
        ref=x.text_input('Tank sample reference')
        lab=y.text_input('Testing laboratory / authorised measurement provider')
        taken=st.date_input('Sample collection date',value=date.today())
        method=st.text_input('Test methods / report reference')
        cols=st.columns(3)
        water=cols[0].number_input('Water (mg/kg)',min_value=0.0,value=300.0)
        tan=cols[1].number_input('TAN (mg KOH/g)',min_value=0.0,value=0.30,format='%.3f')
        oxidation=cols[2].number_input('Oxidation stability (h)',min_value=0.01,value=10.0)
        notes=st.text_area('Additional sample limitations / remarks')
        submitted=st.form_submit_button('Record measured sample and calculate provisional BHI')
    if submitted:
        try:
            rid,res=record_sample(cn,vessel=v,tank_id=t['id'],taken_at=taken.isoformat(),ref=ref,laboratory=lab,method_ref=method,water=water,tan=tan,oxidation=oxidation,limits=limits,weights=weights,notes=notes)
            st.metric('Recorded provisional BHI',f"{res['score']:.1f} / 100")
            if res['breaches']: st.error('REFERENCE LIMIT BREACH — '+', '.join(res['breaches'])+'; escalate for qualified review.')
            else: st.info('Screening status: '+res['status']+' (not a fuel suitability certificate).')
            st.success(f'Sample result #{rid} saved.')
        except ValueError as ex: st.error(str(ex))
    st.subheader('Recorded sample history')
    history=pd.DataFrame(rows(cn,'SELECT taken_at,sample_ref,laboratory,water,tan,oxidation,bhi,status FROM samples WHERE tank_id=? ORDER BY id DESC',(t['id'],)))
    st.dataframe(history,use_container_width=True,hide_index=True)
    if len(history)>1:
        st.line_chart(history.iloc[::-1].set_index('taken_at')['bhi'])

elif page=='6 · Alerts & Power BI exports':
    st.subheader('Exceptions, review and management exports')
    alarms=rows(cn,'SELECT * FROM alerts ORDER BY id DESC')
    st.dataframe(pd.DataFrame(alarms),use_container_width=True,hide_index=True)
    openalerts=[a for a in alarms if a['status']!='Closed']
    if openalerts:
        with st.form('alert_form'):
            aid=st.selectbox('Alert to update',[x['id'] for x in openalerts],format_func=lambda x:f'#{x} · '+next(z['details'][:80] for z in openalerts if z['id']==x))
            status=st.selectbox('Workflow status',['Open','Under review','Closed'])
            owner=st.text_input('Responsible reviewer')
            action=st.text_area('Investigation and documented actions')
            submitted=st.form_submit_button('Save alert update')
        if submitted:
            try:
                update_alert(cn,aid,status,owner,action)
                st.success('Updated alert record.');st.rerun()
            except ValueError as ex: st.error(str(ex))
    st.subheader('Download datasets for Microsoft Power BI Desktop')
    st.caption('These exports are synthetic demonstration data. Power BI can import these CSV files and link them using vessel_id and tank_id.')
    for entity in ('vessels','tanks','checks','bunkerings','samples','alerts'):
        dat=pd.DataFrame(rows(cn,f'SELECT * FROM {entity}'))
        st.download_button(f'Download {entity}.csv',dat.to_csv(index=False).encode(),file_name=f'{entity}.csv',mime='text/csv',key=f'csv{entity}')
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for entity in ('vessels','tanks','checks','bunkerings','samples','alerts'):
            dat=pd.DataFrame(rows(cn,f'SELECT * FROM {entity}'))
            z.writestr(f'{entity}.csv',dat.to_csv(index=False))
    st.download_button('Download all 6 CSVs for Power BI (ZIP)',archive.getvalue(),'fleet_powerbi_exports.zip','application/zip')

elif page=='Scientific validation':
    st.subheader('FMEA–MCDA research basis')
    st.write('Criteria weighted 35% consequences, 30% early warning, 15% monitoring practicality, 20% evidence relevance. Researcher ratings are provisional, not laboratory calibrated.')
    values={}
    for param in PARAMETERS:
        cols=st.columns(4)
        st.markdown('**'+param+'**')
        values[param]=tuple(cols[j].slider(f'{CRITERIA[j]} — {param}',1,5,int(DEFAULT_MCDA[param][j]),key=f'{param}{j}') for j in range(4))
    new_weights=mcda_weights(values)
    st.dataframe(pd.DataFrame([{'Parameter':p,'Calculated relative weight (%)':round(new_weights[p],3)} for p in PARAMETERS]),use_container_width=True,hide_index=True)
    st.bar_chart(pd.DataFrame({'Parameter':list(new_weights),'Weight':list(new_weights.values())}).set_index('Parameter'))
    fmea=pd.DataFrame(FMEA,columns=['ID','Parameter','Failure mode','Severity','Occurrence','Detection difficulty'])
    fmea['RPN']=fmea.Severity*fmea.Occurrence*fmea['Detection difficulty']
    st.dataframe(fmea,use_container_width=True,hide_index=True)
    st.caption('FMEA identifies hazards; MCDA generates provisional weights. Ratings are subjective. A numerical BHI is never proof of fuel compatibility or safety.')
    st.subheader('Sample weight sensitivity')
    cols=st.columns(3)
    water=cols[0].number_input('Water measurement',value=300.0,min_value=0.0)
    tan=cols[1].number_input('TAN measurement',value=0.30,min_value=0.0)
    oxidation=cols[2].number_input('Oxidation measurement',value=10.0,min_value=0.01)
    schemes={'Editable MCDA':new_weights,'Equal thirds':{p:100/3 for p in PARAMETERS},'Former 35/35/30':dict(zip(PARAMETERS,[35,35,30])),'Exploratory FMEA':dict(zip(PARAMETERS,[31.8,25.2,43]))}
    st.dataframe(pd.DataFrame([{'Scheme':k,'Provisional BHI':round(calculate_bhi(water,tan,oxidation,limits,w)['score'],2)} for k,w in schemes.items()]),hide_index=True,use_container_width=True)
    st.info('Validation scope: deterministic formula and workflow tests only. Physical blend compatibility, fuel-grade conformity and degradation prediction require independently appropriate evidence and laboratory testing.')

st.divider()
st.caption('Academic research demonstrator — not affiliated with or deployed by PSA Marine. Only synthetic data should be entered into a public Streamlit application.')
