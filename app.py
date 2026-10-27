import csv
import io
import pandas as pd
import streamlit as st
from core import (CRITERIA, PARAMETERS, CRITERION_WEIGHTS, DEFAULT_MCDA, FMEA,
                  ILLUSTRATIVE_LIMITS, Tank, advance, refuel, mcda_weights, calculate_bhi)

st.set_page_config(page_title='Biofuel Health Index | Research PoC',layout='wide',page_icon='⚙️')
st.title('Biofuel Health Index & Commingling Framework')
st.caption('Harbour craft engineering research prototype | Synthetic inputs only | Not an operational fuel release system')
st.warning('Research demonstration: BHI weights and 50%-of-limit penalty start points are provisional. Reference thresholds below are user-editable demonstrations, NOT a verified ISO 8217 fuel-grade profile. Any breach is shown separately; do not use this dashboard to authorise bunkering, dosing or sailing.')

with st.sidebar:
    st.header('Fuel quality reference profile')
    st.caption('Confirm limits against the actual fuel grade and standard before any real assessment.')
    limits={
      'Water':st.number_input('Water maximum (mg/kg)',min_value=0.001,value=500.0,step=10.0),
      'TAN':st.number_input('Acid number maximum (mg KOH/g)',min_value=0.001,value=0.50,step=0.05,format='%.3f'),
      'Oxidation':st.number_input('Oxidation induction minimum (hours)',min_value=0.001,value=8.0,step=0.5)
    }
    st.caption('Defaults are illustrative research values, not universally applicable B20–B100 specifications.')

p1,p2,p3=st.tabs(['1 | Fuel screening','2 | Commingling simulation','3 | Risk weights & validation'])
with p3:
    st.subheader('MCDA: traceable, editable researcher ratings')
    st.write('Each row is scored from 1 (low) to 5 (high). Criterion importance: consequence 35%, early warning 30%, monitoring practicality 15%, evidence relevance 20%. Both criterion importance and ratings are provisional judgements, not measured risk probabilities.')
    edited={}
    cols=st.columns(4)
    for j,c in enumerate(CRITERIA):
        cols[j].metric(c,f'{CRITERION_WEIGHTS[j]*100:.0f}%')
    for p in PARAMETERS:
        st.markdown(f'**{p}**')
        fields=st.columns(4)
        edited[p]=tuple(fields[i].slider(CRITERIA[i],1,5,int(DEFAULT_MCDA[p][i]),key=f'{p}_{i}') for i in range(4))
    weights=mcda_weights(edited)
    st.subheader('Calculated relative weights')
    for p in PARAMETERS: st.metric(p,f'{weights[p]:.2f}%')
    st.bar_chart(pd.DataFrame({'Parameter':list(weights),'Weight (%)':list(weights.values())}).set_index('Parameter'))
    st.caption('MCDA values do not establish physical deterioration rates or calibrated engine-failure risk.')
    st.subheader('FMEA hazard register (separate from weight calculation)')
    fdf=pd.DataFrame(FMEA,columns=['ID','Indicator','Failure mode','Severity (1–10)','Occurrence (1–5)','Detection difficulty (1–5)'])
    fdf['RPN']=fdf['Severity (1–10)']*fdf['Occurrence (1–5)']*fdf['Detection difficulty (1–5)']
    st.dataframe(fdf,use_container_width=True,hide_index=True)
    st.caption('All FMEA ratings illustrative; the RPN is for hazard prioritisation only, not directly converted into BHI weights.')
    st.download_button('Export FMEA register (CSV)',fdf.to_csv(index=False),'FMEA_register.csv','text/csv')

# Tabs execute in one script run: use computed MCDA weights even if 3rd tab not opened.
with p1:
    st.subheader('Synthetic fuel screening')
    chosen=st.radio('Weight model',['MCDA calculated','Equal thirds','Former 35/35/30','FMEA exploratory 31.8/25.2/43'],horizontal=True)
    useweights={'MCDA calculated':weights,'Equal thirds':dict.fromkeys(PARAMETERS,100/3),
        'Former 35/35/30':dict(zip(PARAMETERS,[35,35,30])),
        'FMEA exploratory 31.8/25.2/43':dict(zip(PARAMETERS,[31.8,25.2,43.0]))}[chosen]
    x,y,z=st.columns(3)
    water=x.number_input('Water (mg/kg)',min_value=0.0,value=300.0,step=10.0)
    tan=y.number_input('TAN (mg KOH/g)',min_value=0.0,value=0.30,step=0.01,format='%.3f')
    oxidation=z.number_input('Oxidation induction (hours)',min_value=0.01,value=10.0,step=0.5)
    out=calculate_bhi(water,tan,oxidation,limits,useweights)
    m1,m2=st.columns(2)
    m1.metric('Provisional BHI (0–100)',f"{out['score']:.1f}")
    m2.metric('Independent reference threshold check',out['status'])
    if out['breaches']: st.error('Threshold breach: '+', '.join(out['breaches'])+'. Refer for expert assessment; BHI never overrides this flag.')
    elif out['status']=='REVIEW': st.warning('Screening review suggested; not a diagnosis or maintenance instruction.')
    else: st.success('No specified reference limit breached. This is not a certification of fuel suitability.')
    detail=pd.DataFrame([{'Parameter':p,'Reference ratio':out['ratios'][p], 'Penalty fraction':out['penalties'][p],'Weight (%)':useweights[p]} for p in PARAMETERS])
    st.dataframe(detail,use_container_width=True,hide_index=True)
    st.subheader('Same sample under alternative weights')
    variants={'MCDA':weights,'Equal thirds':dict.fromkeys(PARAMETERS,100/3), '35/35/30':dict(zip(PARAMETERS,[35,35,30])), 'FMEA exploratory':dict(zip(PARAMETERS,[31.8,25.2,43.0]))}
    comparison=pd.DataFrame([{'Weighting':k,'BHI':calculate_bhi(water,tan,oxidation,limits,v)['score']} for k,v in variants.items()])
    st.bar_chart(comparison.set_index('Weighting'))
    st.download_button('Export score sensitivity (CSV)',comparison.to_csv(index=False),'BHI_weight_comparison.csv','text/csv')

with p2:
    st.subheader('Recursive effective-age commingling calculation')
    st.write('Well-mixed approximation. Effective fuel age is a bookkeeping indicator, not predicted oxidation stability, microbial load or TAN.')
    c1,c2,c3=st.columns(3)
    initv=c1.number_input('Initial tank fuel (L)',min_value=0.0,value=1000.0,step=50.0)
    inita=c2.number_input('Initial effective age (days)',min_value=0.0,value=20.0)
    tankcap=c3.number_input('Tank capacity (L)',min_value=1.0,value=1200.0,step=50.0)
    records=[]
    vessel=Tank(initv,inita)
    st.caption('Three user-adjustable successive bunkering cycles')
    for i,defaults in enumerate(((10.,800.,800.),(7.,500.,500.),(7.,950.,950.)),1):
        cols=st.columns(3)
        days=cols[0].number_input(f'Cycle {i}: elapsed days',min_value=0.0,value=defaults[0],key=f'days{i}')
        consumed=cols[1].number_input(f'Cycle {i}: consumed (L)',min_value=0.0,value=defaults[1],key=f'cons{i}')
        delivered=cols[2].number_input(f'Cycle {i}: delivered (L)',min_value=0.0,value=defaults[2],key=f'del{i}')
        try:
            residual=advance(vessel,days,consumed)
            updated=refuel(residual,delivered)
            if updated.volume_l>tankcap: st.warning(f'Cycle {i}: exceeds stated tank capacity.')
            records.append({'Cycle':i,'Elapsed days':days,'Consumed L':consumed,'ROB before delivery L':residual.volume_l,'Bunkered L':delivered,'Final tank L':updated.volume_l,'Effective age days':round(updated.age_days,4)})
            vessel=updated
        except ValueError as exc:
            st.error(f'Cycle {i}: {exc}. Change inputs to continue.')
            break
    if records:
        df=pd.DataFrame(records)
        st.dataframe(df,use_container_width=True,hide_index=True)
        st.line_chart(df.set_index('Cycle')['Effective age days'])
        st.download_button('Export commingling history (CSV)',df.to_csv(index=False),'commingling_history.csv','text/csv')
    st.info('5% ROB is NOT treated as a safe reset. A low residual volume may still contain contaminants or sediments.')

st.divider()
st.caption('Scientific grounding: NREL Biodiesel Handling and Use Guide (2023); ISO 8217:2024 and MPA Singapore biofuel bunkering framework. Compliance requires a verified applicable grade, sampling and qualified review. No live laboratory data is used.')
