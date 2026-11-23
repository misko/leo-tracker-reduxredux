"""Verify the South two-packet receiver and both complete saved/raw publications."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ARMS = ('c0','fitted_c')
NAMED_SCORED_PIN = '7653b038a30e723e46bf3a5cb690ce8a52d841378f5d60964e1708e2d51cdcca'
NAMED_SCORED = Path('/dev/shm/leo-v3-named-south-transfer-01/result.json')


def score(root):
    from aperture_trial import read,write
    from empty_bootstrap import checked
    from isolated_salvage_south import decision_label
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from raw_cfo_north_score import owner_summary
    from south_cfo_route import MODES,admissible,verified_packet
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    request = read(root/'binding.json')
    for name,pin in request['source_sha256'].items():
        checked(HERE/name,pin)
    clocks = {mode:read(root/f'{label}-clock.json')['timing'] for mode,label in zip(MODES,('containing','mirror'),strict=True)}
    if any(clock['exit_code'] for clock in clocks.values()):
        raise ValueError('The candidate did not complete both original offers. The paid failure is sealed.')
    before,after = (read(root/f'cache-{state}.json') for state in ('before','after'))
    if not admissible(before,request['paging_limit_pages']) or not admissible(after,request['paging_limit_pages']):
        raise ValueError('Unexpected staged member metadata or page deficit')
    seal = read(root/'raw-packet-seal.json')
    checked(root/MODES[0]/'unified-short-bootstrap.json',seal['bootstrap_sha256'])
    packet,native,raw,comparison = verified_packet(root,request)
    if str(packet) != seal['packet'] or comparison != seal['comparison']:
        raise ValueError('The published correction differs from its immutable raw seal')
    route = raw['held_anchor_route']
    native_audit = raw['receiver_audit']['native']
    refine = native_audit['cfo_refinement']
    if (route['refinement_attempts'] != sum(lane['counts']['attempted'] for lane in refine['lanes'])
            or route['changed'] != sum(lane['counts']['changed'] for lane in refine['lanes'])
            or len(comparison['changed']) > route['changed'] or route['selected'] > route['measured']):
        raise ValueError('Counted retained CFO work differs from the original paid receiver')
    changes = {tuple(row[:2]) for row in comparison['changed']}
    labels, changed_ids = set(), set()
    for row in native['source']['probes']:
        if row['candidates']:
            label = f"{request['session']}:{row['receiver_id']}:{row['valid_start_counter']}"
            identifier = 'sha256:'+sha256(label.encode()).hexdigest()
            labels.add(identifier)
            if (row['visit_index'],row['receiver_id']) in changes:
                changed_ids.add(identifier)
    if len(labels) != route['selected'] or len(changed_ids) != len(changes):
        raise ValueError('The selected roster attempted a duplicate or unauthenticated opportunity')
    archived = json.loads(checked(NAMED_SCORED,NAMED_SCORED_PIN))
    truth = archived['truth']
    comparisons = {}
    for mode in MODES:
        folder = root/mode
        worker = raw if mode == MODES[0] else read(folder/'saved-south-cfo-route.json')
        receipt = worker['receipt']
        run = receipt['run_id']
        storage = FastStandardAnalysisStore(folder)
        detail = storage.detail(run)
        old = archived['cases'][mode]
        offer = Algo08Region.parse(read(Path(request['offers'][mode]))).document()
        checked(native_file(folder),seal['native_sha256'][7:])
        checked(folder/'fast-scan-inputs'/(request['session']+'.json'),request['inventory'][7:])
        if (detail['input_sha256'] != seal['native_sha256'] or detail['raw_authority'] != request['authority']
                or receipt['region'] != offer or offer != old['offer'] or receipt['session_id'] != request['session']
                or receipt['window_count'] != 1200 or receipt['counts'] != dict(processed=1200,invalid_capture=0,skipped_fast_score=0)
                or mode == MODES[1] and (worker['waveform_calls'] or worker['handoffs'] != 1 or not worker['staged_inventory'])):
            raise ValueError('South terminal changed original authority, offer, detector or saved handoff')
        science = evidence(folder,receipt,clocks[mode]['started_unix_ns'],read_only=True)
        media = artifacts(folder,receipt)
        research = folder/'joint-research-receipt.json'
        trial = read(research) if research.is_file() else {}
        sidecars,owners = {},{}
        if receipt['decision'] == 'complete':
            grid,path = storage.position_grid(run),storage.position_path(run)
            if (len(media['images']) != 8 or json.loads(json.dumps(media)) != trial['evidence']
                    or not grid['complete'] or not grid['matched_c_grid'] or not path['stages']
                    or not grid['planned_points'] or grid['planned_points'] != grid['evaluated_points']
                    or len(grid['points']) != grid['evaluated_points']):
                raise ValueError('Expected the complete two-arm position grid, paths and eight PNGs')
            sidecars = dict(grid_points=grid['evaluated_points'],position_sha256=media['images']['position']['sha256'])
            for label,doc in (('grid',grid),('path',path)):
                if doc['binding']['position_png_sha256'] != sidecars['position_sha256']:
                    raise ValueError('Sidecar differs from its actual published position PNG')
                sidecars[label] = canonical_digest(doc)
            for arm in ARMS:
                owners[arm] = owner_summary(trial['selected_rows'][arm],labels,changed_ids)
                if owners[arm]['bound_sha256'] != science['owners'][arm]:
                    raise ValueError('Owner list must bind the terminal digest')
        elif media != {'images':{}} or not science['reason'] or any(arm['latlon'] for arm in science['arms'].values()):
            raise ValueError('A withheld fix requires a complete terminal reason and no geography or charts')
        clearance = face_clearance_km(offer,truth)
        if abs(clearance-(.1 if mode == MODES[0] else -.1)) > .001:
            raise ValueError('Expected the original mirrored South ±100 m offers')
        arms = {a:dict(row,error_km=distance_km(truth,row['latlon']),
                       face_clearance_km=face_clearance_km(offer,row['latlon']) if row['latlon'] else None)
                for a,row in science['arms'].items()}
        detail = trial.get('route_details') or {}
        comparisons[mode] = dict(clock=clocks[mode],receipt=receipt,reason=science['reason'],
            status=decision_label(receipt['decision'],clearance),truth_face_km=clearance,arms=arms,
            named_status=old['named_status'],named=old['arms']['named'],named_historical=old['historical_named'],
            owners=owners,named_owners=old['named_owner_digests'],named_owner_count={a:266 for a in ARMS},
            media=media,sidecars=sidecars,graph_proof=worker['graph_proof'],solve=trial.get('solve'),
            early=trial.get('early_regional'),named_finish=worker['named_survivor_finish'],
            isolated=detail.get('provisional_salvage'),signed=detail.get('signed',{}).get('status'),
            signed_clock=detail.get('signed_refit_clocks'),exterior=detail.get('exterior'),fallback=trial.get('recovered_inference'))
    chosen = dict(route,changed_selected_count=len(changes),changed_selected_by_radio=dict(Counter(r[1] for r in changes)))
    write(root/'result.json',dict(verified=True,raw=raw,binding=request,cases=comparisons,truth=truth,
          chosen=chosen,retained_cfo_edits=comparison['changed'],seal=seal,cache=dict(before=before,after=after),
          original_named_scored_sha256=NAMED_SCORED_PIN,scorer_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    score(parser.parse_args().root)
