"""Package the positive RF template result; make no localization claim."""

import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/2026_10_19_fractional_frame_pilot_refinement'


def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    if (OUT/'evidence.json').exists():
        raise FileExistsError('preserve report numerical package')
    OUT.mkdir(exist_ok=True);rows=[]
    original=ROOT/'reports/2026_10_19_algo03_fractional_pilot_benchmark'
    source=read(original/'results.json');protocol=read(original/'protocol.json')
    panel_rates={}
    for name in {r['entry']['panel'] for r in source['rows']}:
        with np.load(ROOT/name,allow_pickle=False) as panel:
            panel_rates[name]=json.loads(str(panel['metadata_json']))['sample_rate_hz']
    for row in source['rows']:
        e=row['entry'];p=e['point']
        rows.append(dict(case=e['case'],receiver=e['receiver'],channel=p['channel'],edge=p['edge'],
            sample_rate_hz=panel_rates[e['panel']],observation_id=p['observation_id'],
            source='sealed_96_probe_benchmark',legacy=row['legacy_fit'],fractional=row['fractional_fit'],
            legacy_replay_difference=row['legacy_likelihood_replay_difference']))
    qualification=ROOT/'reports/2026_10_19_algo03_fractional_qualification'
    for case in ('DS23-0007','DS23-0257','DS23-0217'):
        document=read(qualification/(case+'.json'))
        assert document['all_sealed_requests_measured'] and document['qualification_only']
        for row in document['rows']:
            p=row['point']
            rows.append(dict(case=case,receiver=p['receiver_id']+1,channel=p['channel'],edge=p['edge'],
                sample_rate_hz=document['panel_metadata']['sample_rate_hz'],observation_id=p['observation_id'],
                source='additional_scan_sealed_qualification',legacy=row['legacy_fit'],fractional=row['fractional_fit'],
                legacy_replay_difference=row['legacy_likelihood_replay_difference']))
    if len(rows)!=126 or len({r['observation_id'] for r in rows})!=len(rows):
        raise ValueError('126 unique physical receiver probes required')
    ablation=read(ROOT/'reports/2026_10_19_algo03_fractional_padding_ablation/results.json')
    # Keep numerical evidence compact without discarding a measurement or a
    # fit outcome. Optimizer histories remain bound in local source receipts.
    for row in rows:
        for name in ('legacy','fractional'):
            row[name]={k:v for k,v in row[name].items() if k!='selected_history'}
    write(OUT/'evidence.json',dict(rows=rows,padding_ablation=ablation['rows'],
        measurements_modified=False,position_or_satellite_inference_performed=False,
        same_three_parameters_complete_frame_gains_DC_and_sample_support=True,
        RF_score_is_explained_pilot_energy_fraction_not_a_probability=True))
    authority_files=[original/'protocol.json',original/'results.json',qualification/'protocol.json',
        qualification/'execution.json',ROOT/'reports/2026_10_19_algo03_fractional_padding_ablation/protocol.json',
        ROOT/'reports/2026_10_19_algo03_fractional_padding_ablation/results.json']
    authority_files += [qualification/(c+'.json') for c in ('DS23-0007','DS23-0257','DS23-0217')]
    write(OUT/'input_authorities.json',dict(
        source_result_sha256={str(p.relative_to(ROOT)):digest(p) for p in authority_files},
        private_saved_panel_sha256=protocol['sample_panel_sha256'],
        raw_qualification_plan_sha256=read(qualification/'protocol.json')['original_qualification_plan_sha256'],
        raw_IQ_not_republished=True,private_authorities_required_for_independent_RF_refit=True))
    snapshot=OUT/'source_snapshot';snapshot.mkdir(exist_ok=True)
    for name in ('local_pilot_refinement.py','fast_local_pilot_refinement.py','decoupled_pilot_clocks.py'):
        shutil.copyfile(ROOT/'tools'/name,snapshot/name)
    historical=ROOT/'reports/2026_10_19_algo03_pilot_clock_model/source_snapshot/decoupled_pilot_clocks.py'
    shutil.copyfile(historical,snapshot/'decoupled_pilot_clocks_pre_padding_control.py')
    # Extract only the exact two numerical interpolation functions. The
    # original exploratory script also imports unrelated native orchestrators;
    # the replay bundle deliberately has no hardware or storage dependency.
    path=ROOT/'tools/probe_native_code_carrier.py';text=path.read_text();tree=ast.parse(text)
    functions=[ast.get_source_segment(text,node) for node in tree.body
        if isinstance(node,ast.FunctionDef) and node.name in ('periodic_upsample','interpolate_periodic')]
    if len(functions)!=2:raise ValueError('interpolation source extraction changed')
    shim='"""Exact pure interpolation functions extracted from the recorded source authority."""\nimport numpy as np\n\n'+'\n\n'.join(functions)+'\n'
    (snapshot/'probe_native_code_carrier.py').write_text(shim)
    tests=OUT/'tests';tests.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'tests/analysis/test_decoupled_pilot_clocks.py',tests/'test_decoupled_pilot_clocks.py')
    write(OUT/'source_manifest.json',dict(
        snapshot_sha256={str(p.relative_to(OUT)):digest(p) for p in sorted(snapshot.glob('*.py'))},
        interpolation_extracted_from=dict(path=str(path.relative_to(ROOT)),sha256=digest(path),
            functions=['periodic_upsample','interpolate_periodic']),
        numerical_template=dict(path='src/leo/analysis/starlink/templates.py',
            sha256=digest(ROOT/'src/leo/analysis/starlink/templates.py')),
        historical_helper_source= dict(path='source_snapshot/decoupled_pilot_clocks_pre_padding_control.py',
            sha256=digest(historical)),
        later_snapshot_only_adds_the_isolated_rounded_padding_control_class=True,
        published_ALGO02_frozen_sources_unmodified=True,
        python=sys.version,numpy=np.__version__,builder_sha256=digest(Path(__file__))))
    shutil.copyfile(Path(__file__),OUT/'build_evidence.py')


if __name__=='__main__':main()
