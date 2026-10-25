"""Matched position adapter for the globally RF-qualified receiver witness."""
import copy
import json
from pathlib import Path
import numpy as np
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from probe_ds23_graph_seeded_paths import build as original_build

HERE=Path(__file__).resolve().parent
METHODS=('fast_rx1_hz50','fast_rx1_rf50')

def expand(d,method):
    if method not in METHODS:raise ValueError('a frozen receiver hypothesis is required')
    changed=dict(d);scan=copy.copy(d['scan']);node=copy.deepcopy(d['node'])
    bases=[]
    for track,old in zip(d['scan'].tracks,d['scan'].rx_basis,strict=True):
        extra=projected_receiver_basis(track['times'],spacing_s=10.,width_s=5.)*.25
        if track['receiver']!=1:extra*=0.
        if method=='fast_rx1_hz50':extra/=track['rf_hz']/11.5e9
        bases.append(np.column_stack((old,extra)))
    scan.rx_basis=bases
    state=np.asarray(node['seed']['state']['smooth'])
    width=bases[0].shape[1]-state.shape[1]
    assert width==31
    node['seed']['state']['smooth']=np.column_stack((state,np.zeros((2,width))))
    changed.update(scan=scan,node=node)
    return changed

def build_method(d,arm,reference,case,method):
    selection=json.loads((HERE/'selection.json').read_text())
    if not selection['selection_uses_no_GPS']:raise ValueError('receiver hypothesis lacks RF-only selection')
    if method=='baseline':raise ValueError('receiver witness did not qualify a model')
    if not selection['methods'][method]['qualified']:raise ValueError('receiver model is not prediction qualified')
    protocol=json.loads((HERE/'protocol.json').read_text())
    if case not in protocol['cases']:raise ValueError('case is outside frozen receiver cohort')
    changed=expand(d,method)
    p=original_build(changed,'default',arm,np.asarray(reference))
    p.receiver_control_method=method
    return p

def build(d,arm,reference,case):
    method=json.loads((HERE/'selection.json').read_text())['selected_method']
    return build_method(d,arm,reference,case,method)
