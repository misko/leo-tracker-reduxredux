"""Verify and score the two saved North receiver interventions."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ARMS = ('c0','fitted_c')


def score(root):
    from aperture_trial import read,write
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from north_cfo_contrasts import ORDER,PREVIOUS,SOURCE_PIN
    from prospective_0316_solver import owner_delta
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.scoring import distance_km

    binding = read(root/'binding.json')
    checked(HERE/'north_cfo_contrasts.py',binding['source_sha256'])
    clocks = {mode:read(root/f'{mode}-clock.json')['timing'] for mode in ORDER}
    if any(clock['exit_code'] for clock in clocks.values()):
        raise ValueError('A saved child failed. Its original sealed clock is retained.')
    reference = json.loads(checked(PREVIOUS/'result.json',SOURCE_PIN))
    before = reference['cases']['containing']
    base = read(PREVIOUS/'containing/joint-research-receipt.json')
    parent_owners = base['selected_rows']
    if any(canonical_digest(parent_owners[arm]) != before['owners'][arm]['ordered_sha256'] for arm in ARMS):
        raise ValueError('The refined reference owners differ from its sealed raw result')
    truth,request = reference['truth'],binding['request']
    offer = Algo08Region.parse(read(Path(binding['offer']))).document()
    changes = {row['owner_id'] for row in reference['factors']['changes']}
    results = {}
    for mode in ORDER:
        folder = root/mode
        worker = read(folder/'north-cfo-contrast.json')
        receipt, source = worker['receipt'],binding['mode_inputs'][mode]
        checked(native_file(folder),source['native_sha256'][7:])
        checked(folder/'fast-scan-inputs'/(request['session']+'.json'),request['inventory'][7:])
        run = receipt['run_id']
        store = FastStandardAnalysisStore(folder)
        detail = store.detail(run)
        science = evidence(folder,receipt,clocks[mode]['started_unix_ns'],read_only=True)
        media = artifacts(folder,receipt)
        trial_file = folder/'joint-research-receipt.json'
        trial = read(trial_file) if trial_file.is_file() else {}
        if (source != worker['input'] or worker['waveform_calls'] or worker['handoffs'] != 1
                or detail['input_sha256'] != source['native_sha256']
                or detail['raw_authority'] != request['authority'] or receipt['session_id'] != request['session']
                or receipt['region'] != offer or offer != before['receipt']['region']
                or receipt['counts'] != before['receipt']['counts'] or receipt['window_count'] != 1200):
            raise ValueError('The saved contrast changed an unrelated scientific or recording input')
        owners,sidecars = {},{}
        rows = trial.get('selected_rows',{})
        if receipt['decision'] == 'complete':
            grid,path = store.position_grid(run),store.position_path(run)
            if (len(media['images']) != 8 or json.loads(json.dumps(media)) != trial['evidence']
                    or not worker['graph']['enabled'] or not worker['named_finish']['requested']
                    or not grid['complete'] or not grid['matched_c_grid'] or grid['planned_points'] != grid['evaluated_points']
                    or len(grid['points']) != grid['evaluated_points'] or not path['stages']):
                raise ValueError('A completed saved contrast must publish both arms and their media')
            sidecars = dict(points=grid['evaluated_points'],position_png=media['images']['position']['sha256'])
            for name,doc in (('grid',grid),('path',path)):
                if doc['binding']['position_png_sha256'] != sidecars['position_png']:
                    raise ValueError('The numeric evidence must bind the current position figure')
                sidecars[name] = canonical_digest(doc)
            for arm in ARMS:
                owned = rows[arm]
                pin = canonical_digest({oid:sat for oid,sat,_ in owned})
                if pin != science['owners'][arm]:
                    raise ValueError('The original owner digest must point to the published roster')
                delta = owner_delta(parent_owners[arm],owned)
                owners[arm] = dict(full_refined=delta, current_sha256=pin,ordered_sha256=canonical_digest(owned),
                                   on_refined_changed_opportunities=sum(oid in changes for oid,_,_ in owned))
        elif rows or media != {'images':{}} or not science['reason'] or any(arm['latlon'] for arm in science['arms'].values()):
            raise ValueError('Incomplete withholding evidence')
        public = {arm:dict(value,error_km=distance_km(truth,value['latlon'])) for arm,value in science['arms'].items()}
        if set(public) != set(ARMS):
            raise ValueError('Expected both fixed and fitted calibration branches')
        route = trial.get('route_details') or {}
        results[mode] = dict(clock=clocks[mode],worker=worker,arms=public,owners=owners,sidecars=sidecars,media=media,
            receipt=receipt,reason=science['reason'],signed_status=route.get('signed',{}).get('status'),
            signed_cpu_s=route.get('signed_refit_clocks',{}).get('cpu_s'),fallback=trial.get('recovered_inference'),
            solve=trial.get('solve'),scientific_digests=science['scientific_digests'])
    write(root/'result.json',dict(verified=True,binding=binding,reference=before,cases=results,truth=truth,
          scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    score(parser.parse_args().root)
