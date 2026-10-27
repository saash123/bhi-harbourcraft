"""Research/proof-of-concept ONLY. Synthetic data; not fuel certification or vessel clearance."""
from dataclasses import dataclass
import math

PARAMETERS = ('Water', 'TAN', 'Oxidation')
# MCDA criteria: scores 1..5, all HIGHER means more decision-support importance.
# Values below are illustrative researcher judgements, not empirical measurements.
CRITERIA = ('Operational consequence', 'Early-warning usefulness', 'Monitoring practicality', 'Evidence relevance')
CRITERION_WEIGHTS = (0.35, 0.30, 0.15, 0.20)
DEFAULT_MCDA = {'Water': (5, 3, 5, 4), 'TAN': (4, 3, 4, 4), 'Oxidation': (4, 5, 3, 5)}
FMEA = [
 ('W01','Water','Water and microbial contamination',8,3,5),
 ('W02','Water','Water accumulation and corrosion',7,3,6),
 ('T01','TAN','Acidic constituents and corrosion',7,3,5),
 ('T02','TAN','Acid increase as deterioration indicator',6,3,5),
 ('O01','Oxidation','Gums and deposits associated with oxidation',8,4,6),
 ('O02','Oxidation','Declining oxidation reserve',7,4,5),
]

@dataclass(frozen=True)
class Tank:
    volume_l: float
    age_days: float

def advance(tank, days, consumption_l):
    if not all(math.isfinite(v) for v in (tank.volume_l,tank.age_days,days,consumption_l)):
        raise ValueError('All tank inputs must be finite')
    if min(tank.volume_l,tank.age_days,days,consumption_l)<0 or consumption_l>tank.volume_l:
        raise ValueError('Invalid time or consumption')
    return Tank(tank.volume_l-consumption_l,tank.age_days+days)

def refuel(tank, delivery_l, delivery_age_days=0):
    if not all(math.isfinite(v) for v in (tank.volume_l,tank.age_days,delivery_l,delivery_age_days)):
        raise ValueError('All tank inputs must be finite')
    if min(tank.volume_l,tank.age_days,delivery_l,delivery_age_days)<0:
        raise ValueError('Negative age/volume')
    total=tank.volume_l+delivery_l
    if total<=0: raise ValueError('Tank must contain some fuel')
    return Tank(total,(tank.volume_l*tank.age_days+delivery_l*delivery_age_days)/total)

def mcda_weights(matrix=None, criteria_weights=CRITERION_WEIGHTS):
    matrix = matrix or DEFAULT_MCDA
    if len(criteria_weights)!=len(CRITERIA) or any(not math.isfinite(x) or x<0 for x in criteria_weights) or not math.isclose(sum(criteria_weights),1,abs_tol=1e-8):
        raise ValueError('Criterion weights must sum to one')
    scores={}
    for p in PARAMETERS:
        row=matrix[p]
        if len(row)!=len(CRITERIA) or any(not (1<=x<=5) for x in row):
            raise ValueError('MCDA ratings must be in the 1–5 range')
        scores[p]=sum(c*r for c,r in zip(criteria_weights,row))
    total=sum(scores.values())
    return {p:100*scores[p]/total for p in PARAMETERS}

def fmea_rpns():
    return [(i,p,mode,s*o*d) for i,p,mode,s,o,d in FMEA]

def calculate_bhi(water, tan, oxidation, limits, weights):
    """Returns risk-screening score and INDEPENDENT limit status.
    Limits are user-specified illustrative profile values, NOT ISO 8217 grade certification.
    Penalty activates beyond 50% of limit (a provisional engineering choice).
    """
    vals=(water,tan,oxidation)
    if any(v is None for v in vals): return {'score':None,'status':'INCOMPLETE','breaches':[],'penalties':{},'ratios':{}}
    if any(not math.isfinite(v) for v in vals) or water<0 or tan<0 or oxidation<=0:
        raise ValueError('Measurements must be finite and non-negative; oxidation > 0')
    if any(not math.isfinite(v) or v<=0 for v in limits.values()):
        raise ValueError('Positive finite reference thresholds required')
    if any(weights.get(p,0)<0 for p in PARAMETERS) or not math.isclose(sum(weights.get(p,0) for p in PARAMETERS),100,abs_tol=1e-6):
        raise ValueError('Nonnegative weights must total 100')
    ratios={'Water':water/limits['Water'],'TAN':tan/limits['TAN'],'Oxidation':limits['Oxidation']/oxidation}
    penalties={p:min(1.0,max(0.0,(ratios[p]-0.5)/0.5)) for p in PARAMETERS}
    score=max(0.0,100-sum(weights[p]*penalties[p] for p in PARAMETERS))
    breaches=[p for p in PARAMETERS if ratios[p]>1]
    status='REFERENCE LIMIT BREACH' if breaches else ('REVIEW' if score<70 else 'SCREENING NORMAL')
    return {'score':score,'status':status,'breaches':breaches,'penalties':penalties,'ratios':ratios}

# Research illustration only. Not a fuel grade compliance limit.
ILLUSTRATIVE_LIMITS={'Water':500.0,'TAN':0.5,'Oxidation':8.0}
