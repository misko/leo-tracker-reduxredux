"""Symmetric discrete prior for satellite labels on a fixed track population.

Choose a family count K with p(K) proportional to 1/(K(K+1)), then choose
uniformly among every assignment of M tracks to exactly K of N catalogue
satellites. All incumbents and challengers pay the same code. Continuous
parameter integration and its complexity cost remain in the RF bound.
"""

import math
import copy
import numpy as np


def log_stirling_second(n,k):
    if not isinstance(n,int) or not isinstance(k,int) or not 0<=k<=n:
        raise ValueError('integer partition dimensions 0 <= k <= n required')
    row=np.full(k+1,-np.inf);row[0]=0.
    for count in range(1,n+1):
        next_row=np.full(k+1,-np.inf)
        for groups in range(1,min(count,k)+1):
            next_row[groups]=np.logaddexp(row[groups-1],math.log(groups)+row[groups])
        row=next_row
    return float(row[k])


def family_code(catalogue_count,labels):
    labels=list(labels)
    n,m,k=catalogue_count,len(labels),len(set(labels))
    if (not isinstance(n,int) or n<1 or m<1 or k>n or
            any(not isinstance(j,(int,np.integer)) or not 0<=j<n for j in labels)):
        raise ValueError('nonempty catalogue-indexed fixed track labels required')
    falling=sum(math.log(n-i) for i in range(k))
    normalizer=math.log(1-1/(min(m,n)+1))
    return float(2*(math.log(k)+math.log(k+1)+normalizer+
                    falling+log_stirling_second(m,k)))


def observed_labels(node,entries,keep,slices):
    if len(node['seed']['rows'])!=len(slices):
        raise ValueError('one slice per original curved row required')
    labels=[int(r['candidate_index']) for r,sl in zip(node['seed']['rows'],slices,strict=True)
            if np.asarray(keep[sl],bool).any()]
    labels.extend(int(e['candidate_index']) for e in entries)
    return labels


def symmetric_gain(original_loss,original_code,trial_loss,trial_code):
    """Positive values favor the trial; input codes include BOTH hypotheses."""
    values=np.asarray([original_loss,original_code,trial_loss,trial_code],float)
    if not np.isfinite(values).all():raise ValueError('finite matched scores required')
    return float(original_loss+original_code-trial_loss-trial_code)


def replace_whole_family(node,entries,old_label,new_label,norad,aliases):
    """Coherently change curved and predictive labels; retain every observation.

    Alias estimates are proposal-time RF measurements, indexed by curved row
    and predictive entry. They must cover the entire changed family.
    """
    changed,predictive=copy.deepcopy(node),copy.deepcopy(entries)
    required={('curve',k) for k,r in enumerate(node['seed']['rows']) if r['candidate_index']==old_label}
    required|={('linear',k) for k,e in enumerate(entries) if e['candidate_index']==old_label}
    if not required or set(aliases)!=required:
        raise ValueError('complete aliases for every changed curved/predictive factor required')
    for kind,k in required:
        if kind=='curve':
            changed['seed']['rows'][k].update(candidate_index=int(new_label),candidate_norad=int(norad))
            changed['aliases'][k]=int(aliases[kind,k])
        else:
            predictive[k].update(candidate_index=int(new_label),norad=int(norad),alias=int(aliases[kind,k]))
    return changed,predictive
