"""Two-satellite family proposals with one shared calibration posterior."""

import copy
import numpy as np

from build_dsx01_orbit_modes import build_modes
from ds23_conditioned_relative_nomination import gaussian_prediction
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def side(track,partition):
    kind=partition['kind']
    if kind=='receiver':first=track['receiver']==partition['receiver']
    elif kind=='band':first=int(track['channel']>4)==partition['band']
    elif kind=='owner':first=(track['receiver'],track['channel'])==(partition['receiver'],partition['channel'])
    elif kind=='component':first=track['key']==partition['component']
    elif kind=='time':first=float(np.median(track['times']))<=partition['time_s']
    else:raise ValueError('unknown family partition')
    return 0 if first else 1


def partitions(scan,members):
    """Whole-fragment partitions; both groups must contain curved evidence."""
    tracks=[scan.tracks[m['track_index']] for m in members]
    curves=[k for k,m in enumerate(members) if m['kind']=='curved']
    if len(curves)<2:return []
    offered=[dict(kind='receiver',receiver=1),dict(kind='band',band=0)]
    offered.extend(dict(kind='owner',receiver=rx,channel=ch) for rx,ch in sorted({(tracks[k]['receiver'],tracks[k]['channel']) for k in curves}))
    offered.extend(dict(kind='component',component=tracks[k]['key']) for k in curves)
    medians=sorted({float(np.median(tracks[k]['times'])) for k in curves})
    offered.extend(dict(kind='time',time_s=(a+b)/2) for a,b in zip(medians[:-1],medians[1:],strict=True))
    result=[];seen=set()
    for p in offered:
        labels=np.array([side(t,p) for t in tracks],int)
        if len(set(labels[curves]))!=2:continue
        key=tuple(labels);canonical=min(key,tuple(1-labels))
        if canonical in seen:continue
        seen.add(canonical);result.append(dict(partition=p,member_sides=labels))
    return result


def configuration(d,offers):
    """Apply partial assignments against original labels, retaining every row."""
    node=copy.deepcopy(d['node']);entries=copy.deepcopy(d['entries']);lookup={t['key']:t for t in d['scan'].tracks};changes={}
    for family,offer in offers:
        target=family['original_index']
        if target in changes:raise ValueError('duplicate partition target')
        if len(offer['pair'])!=2:raise ValueError('two component labels required')
        expected=[offer['pair'][side(lookup[m['component']],offer['partition'])] for m in family['members']]
        if expected!=list(offer['labels_by_member']):raise ValueError('prediction and configuration partitions differ')
        aliases={m['component']:int(a) for m,a in zip(family['members'],offer['aliases'],strict=True)}
        changes[target]=(offer,aliases)
    for k,(old,new) in enumerate(zip(d['node']['seed']['rows'],node['seed']['rows'],strict=True)):
        if old['candidate_index'] not in changes:continue
        offer,aliases=changes[old['candidate_index']];j=offer['pair'][side(lookup[old['component']],offer['partition'])]
        new.update(candidate_index=int(j),candidate_norad=int(d['scan'].norads[j]))
        if old['component'] in aliases:node['aliases'][k]=aliases[old['component']]
    for old,new in zip(d['entries'],entries,strict=True):
        if old['candidate_index'] not in changes:continue
        offer,aliases=changes[old['candidate_index']];j=offer['pair'][side(lookup[old['component']],offer['partition'])]
        new.update(candidate_index=int(j),norad=int(d['scan'].norads[j]),alias=aliases[old['component']])
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    if set(e['candidate_index'] for e in entries)-set(labels):raise ValueError('predictive label lacks a curved model coordinate')
    return node,entries,d['all_means'][labels]


def prediction(d,data,labels_by_member,aliases):
    """Joint predictive density, sharing radio, active phases and orbital covariance.

    Unseen Student phases use moment-matched Gaussian priors for nomination.
    Every held fragment has one constant; no per-fragment linear term is added.
    """
    labels=np.asarray(labels_by_member,int);aliases=np.asarray(aliases,int);members=data['members'];p=data['p'];nb=data['radio_width']
    if labels.shape!=(len(members),) or aliases.shape!=labels.shape:raise ValueError('one label and alias per complete member required')
    unique=sorted(set(labels.tolist()));active={r['candidate_index'] for r,s in zip(p.rows,p.slices,strict=True) if p.keep[s].any()}
    slots=list(range(nb));mean=data['coefficient'][:nb].tolist();models=[]
    for j in unique:
        owners={(m['receiver'],m['channel']) for k,m in enumerate(members) if m['kind']=='curved' and labels[k]==j}
        supported=j in p.supported or len(owners)>=2
        old_phase=nb+p.labels.index(j) if j in p.labels and j in active else None
        phase_index=len(mean);slots.append(old_phase);mean.append(data['coefficient'][old_phase] if old_phase is not None else d['all_means'][j]/d['widths'][j])
        orbit=[];mode_bank=None
        if supported:
            old_start=nb+len(p.labels)+3*p.supported.index(j) if j in p.supported and j in active else None
            orbit=list(range(len(mean),len(mean)+3));slots.extend([old_start+k if old_start is not None else None for k in range(3)])
            mean.extend(data['coefficient'][old_start:old_start+3] if old_start is not None else np.zeros(3))
            if j in p.supported:
                local=p.labels.index(j);mode_bank=dict(time_s=p.mode_bank['time_s'],**{field:p.mode_bank[field][3*local:3*local+3] for field in ['position_km','velocity_km_s']})
            else:mode_bank=build_modes(d['scan'],[j],[j],'physical')[0]
        bank=dict(time_s=d['scan'].sky['time_s'],**{field:d['scan'].sky[field][[j]] for field in ['position_km','velocity_km_s']})
        models.append(dict(candidate_index=j,phase_coordinate=phase_index,orbital_coordinates=orbit,bank=bank,mode_bank=mode_bank))
    n=len(members);constant_start=len(mean);slots.extend([None]*n);mean.extend(np.zeros(n));mean=np.asarray(mean)
    covariance=np.eye(len(mean));known=[k for k,s in enumerate(slots) if s is not None];old=[slots[k] for k in known]
    covariance[np.ix_(known,known)]=data['covariance'][np.ix_(old,old)];covariance[constant_start:,constant_start:]=np.eye(n)*300**2
    per_point=labels[data['groups']];values=data['values']+aliases[data['groups']]/4.4e-6
    reference=np.array([mean[m['phase_coordinate']]*d['widths'][m['candidate_index']] for m in models])
    def geometry(phases):
        intercept=np.zeros(len(values));features=np.zeros((len(values),len(mean)));features[:,:nb]=data['radio'];elevation=np.empty(len(values))
        features[:,constant_start:]=np.eye(n)[data['groups']]
        for m,phase in zip(models,phases,strict=True):
            j=m['candidate_index'];use=per_point==j;bank=m['bank'];times=data['times']
            f,e=phase_frequency_grid(bank,times,*latlon(d['x']),phase_seconds=phase)
            plus,_=phase_frequency_grid(bank,times,*latlon(d['x']),phase_seconds=phase+.01)
            minus,_=phase_frequency_grid(bank,times,*latlon(d['x']),phase_seconds=phase-.01)
            derivative=(plus[0]-minus[0])/.02;intercept[use]=data['q'][use]*(f[0,use]-derivative[use]*phase)
            features[use,m['phase_coordinate']]=data['q'][use]*derivative[use]*d['widths'][j]
            elevation[use]=e[0,use]
            if m['orbital_coordinates']:
                modes=paired_frequency_modes(bank,m['mode_bank'],times,np.zeros(len(times),int),np.array([phase]),*latlon(d['x']))
                features[np.ix_(use,m['orbital_coordinates'])]=data['q'][use,None]*modes[use]
        return intercept,features,elevation
    history=[]
    for _ in range(5):
        intercept,features,e=geometry(reference);result=gaussian_prediction(values-intercept-features@mean,features,covariance,data['noise'])
        coefficient=mean+result['parameter_update'];phase=np.array([coefficient[m['phase_coordinate']]*d['widths'][m['candidate_index']] for m in models])
        change=float(np.max(abs(phase-reference)));history.append(change);reference=np.clip(phase,-15,15)
    if np.max(abs(phase))<=15:
        intercept,features,e=geometry(phase);residual=values-intercept-features@coefficient
    else:e=np.full(len(values),-90.);residual=result['native_residual']
    return dict(labels_by_member=labels,unique_labels=unique,aliases=aliases,score=result['objective'],phase_s=phase,
        phase_change_s=change,qualified=bool(np.max(abs(phase))<=15 and e.min()>=0 and change<=.01),
        minimum_elevation_deg=float(e.min()),residual_hz=residual,conditional_RMS_hz=float(np.sqrt(np.mean(residual**2))),
        coefficient=coefficient,prior_mean=mean,prior_covariance=covariance,calibration_slots=slots,
        satellite_parameters=[{k:v for k,v in m.items() if k not in ['bank','mode_bank']} for m in models],
        constant_start=constant_start,all_held_points_predictive_only=True,shared_radio_posterior_once=True)
