"""Bounded expansion of the frozen DS6 phase extraction cohort."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SEED=2026092720


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    pp=HERE/'protocol.json'
    if pp.exists():raise FileExistsError('Protocol already frozen')
    inv=ROOT/'2026_09_27_ds6_roof/approved-inventory.json';old=ROOT/'2026_09_27_latest_ten_phase/plan.json';validation=ROOT/'2026_09_27_ds6_common_rate_validation/protocol.json'
    excluded={r['session_id'] for r in json.loads(old.read_text())['scans']}|{r['session_id'] for r in json.loads(validation.read_text())['selected']};inventory=json.loads(inv.read_text())['captures'];selected=[]
    for rate in [2.5,5.,7.5,10.]:
        pool=[r for r in inventory if r['session_id'] not in excluded and r['sample_rate_msps']==rate and r['analysis']=='figures_ready' and r['tracking']=='complete']
        ranked=sorted(pool,key=lambda r:hashlib.sha256(f'{SEED}:{r["session_id"]}'.encode()).hexdigest());assert ranked;selected.append(ranked[0])
    sources=[ROOT/'2026_09_27_ds6_position_linked_phase/common_rate.py',ROOT/'2026_09_27_latest_ten_phase/phase.py',ROOT/'2026_09_27_ds6_dwell_phase/experiment.py',ROOT/'2026_09_27_ds6_common_rate_validation/plan.py']
    protocol=dict(seed=SEED,visit_partition_seed=2026092711,inventory_sha256=digest(inv),exclusion_sources={str(p.relative_to(ROOT)):digest(p) for p in [old,validation]},excluded=sorted(excluded),
        selection='One hash-selected previously excluded-from-phase-cohort scan per sample rate, using frozen inventory readiness; no replacements',selected=selected,
        source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sources},starts_ms=[0,21,42,63,84,105],width_ms=7,
        visit_selection='Unchanged prior metadata planner: two disjoint exact positioning-track pairs, two whole visits per original partition; at most eight visits per scan',
        primary='Frozen shared-rate versus independent-rate unit-phasor extraction; all original jointly qualified windows; equal-window MSE within each scan',
        decision='Require at least three evaluable scans, lower shared-rate MSE in at least three, and lower equal-scan mean MSE before promoting extraction',
        scope='Bounded four-scan extraction expansion, at most 32 existing dwells; no new RF or geographic success claim; record unavailable cases')
    pp.write_text(json.dumps(protocol,indent=2)+'\n');print(json.dumps(selected,indent=2))


def prepare():
    # Reuse the already tested report planner; only its output directory changes.
    # Its original partition/ranking seed remains unchanged and explicit above.
    spec=importlib.util.spec_from_file_location('original_phase_planner',ROOT/'2026_09_27_ds6_common_rate_validation/plan.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.HERE=HERE;mod.prepare()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['freeze','prepare']);args=ap.parse_args();freeze() if args.action=='freeze' else prepare()
