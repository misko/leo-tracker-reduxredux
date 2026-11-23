"""Check the signed refined receiver and both North web publications offline."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ARMS = ('c0','fitted_c')
MIXED_ROOT = Path('/dev/shm/leo-eight-ms-north/12ms')
MIXED_PIN = '2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427'
STOCK_SEAL = '549a8a647ac6831635185028cd337e3834f86fc88788f783d55b1b85a504b1c3'
STOCK_BIND = '098576435c28aead2bafeb727c587c0c67ca351272d5375eb6d64ebbc07bc477'
STOCK_CLOCK = '9ab5f2ffc19d4aebe09912ac905adcea105fda9c001cb96d1351d05c629626e8'
HISTORICAL_MIXED = '871105154ab79679308cf7455ee10c236094d8735a02c17ed11bb2412283172e'


def owner_summary(rows, known_labels, cfo_updates):
    from collections import Counter
    from leo.contracts.digests import canonical_digest

    owners = {identifier:satellite for identifier,satellite,_ in rows}
    if len(owners) != len(rows) or not owners.keys() <= known_labels:
        raise ValueError('Owned observations must come from unique original receiver opportunities')
    return dict(count=len(rows), by_role=dict(Counter(role for _,_,role in rows)),
                owned_updated_cfo=len(owners.keys() & cfo_updates), ordered_sha256=canonical_digest(rows),
                bound_sha256=canonical_digest(owners))


def publications(root, request, raw, named, controls, truth, opportunities, cfo_updates):
    from aperture_trial import read
    from empty_bootstrap import checked
    from isolated_salvage_south import decision_label
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import ORDER, native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    results = {}
    for mode, suffix in zip(ORDER,('containing','mirror'),strict=True):
        folder = root/mode
        clock = read(root/f'{suffix}-clock.json')['timing']
        observed = raw if suffix == 'containing' else read(folder/'saved-refined-north.json')
        control = named if suffix == 'containing' else controls
        offer = Algo08Region.parse(read(root/f'{"inside" if suffix == "containing" else "mirror"}-offer.json')).document()
        expected = control['receipt']['region'] if suffix == 'containing' else control['offer']
        receipt = observed['receipt']
        standard = FastStandardAnalysisStore(folder)
        run = receipt['run_id']
        detail = standard.detail(run)
        workspace = FastScanStore(folder).automatic_workspace(run,create=False)
        checked(workspace/'terminal.json',receipt['terminal_sha256'][7:])
        checked(native_file(folder),raw['native_sha256'][7:])
        checked(folder/'fast-scan-inputs'/(request['session']+'.json'),request['inventory'][7:])
        if (clock['exit_code'] or receipt['region'] != offer or expected != offer or detail['input_sha256'] != raw['native_sha256']
                or detail['raw_authority'] != request['authority'] or receipt['session_id'] != request['session']
                or receipt['window_count'] != 1200 or receipt['counts'] != dict(processed=1200,invalid_capture=0,skipped_fast_score=0)
                or observed['detector_recipe_sha256'] != raw['detector_recipe_sha256']
                or (suffix == 'mirror' and (observed['waveform_calls'] or not observed['staged_inventory'] or observed['handoffs'] != 1))):
            raise ValueError('The public North result changed a bound input, staged port or offer')
        science = evidence(folder,receipt,clock['started_unix_ns'],read_only=True)
        media = artifacts(folder,receipt)
        route_file = folder/'joint-research-receipt.json'
        research = read(route_file) if route_file.is_file() else {}
        route = research.get('route_details') or {}
        sidecars, owners = {}, {}
        if receipt['decision'] == 'complete':
            if json.loads(json.dumps(media)) != research['evidence'] or len(media['images']) != 8:
                raise ValueError('The complete fix must independently verify all eight PNGs')
            grid, path = standard.position_grid(run), standard.position_path(run)
            if (not grid['complete'] or not grid['evaluated_points'] or grid['planned_points'] != grid['evaluated_points']
                    or len(grid['points']) != grid['evaluated_points'] or not grid['matched_c_grid'] or not path['stages']):
                raise ValueError('The published path and matched calibration grid must be complete')
            for key, doc in (('path',path),('grid',grid)):
                if doc['binding']['position_png_sha256'] != media['images']['position']['sha256']:
                    raise ValueError('Both position sidecars must bind their actual position PNG')
                sidecars[key] = dict(sha256=canonical_digest(doc), binding=doc['binding'])
            sidecars['grid_points'] = grid['evaluated_points']
            for arm in ARMS:
                owners[arm] = owner_summary(research['selected_rows'][arm],opportunities,cfo_updates)
                if owners[arm]['bound_sha256'] != science['owners'][arm] or not owners[arm]['count']:
                    raise ValueError('The scientific owner registry must bind the reported actual rows')
        elif media != {'images':{}} or not science['reason'] or any(row['latlon'] is not None for row in science['arms'].values()):
            raise ValueError('A legitimate withhold must publish a reason and no figures or coordinates')
        truth_clearance = face_clearance_km(offer,truth)
        if abs(truth_clearance-(0.1 if suffix == 'containing' else -0.1)) > .001:
            raise ValueError('The score must compare the original ±100 m North offers')
        sign = control['receipt']['decision'] if suffix == 'containing' else control['status']

        def arms(values):
            if set(values) != set(ARMS):
                raise ValueError('Expected both declared calibration arms')
            return {a:dict(values[a],error_km=distance_km(truth,values[a]['latlon']),
                       face_clearance_km=face_clearance_km(offer,values[a]['latlon']) if values[a]['latlon'] else None)
                    for a in ARMS}

        results[mode] = dict(clock=clock,candidate=arms(science['arms']),named=arms(control['arms']),owners=owners,
            named_owners=control['owners'],named_owner_count=control['associated'],
            decision=receipt['decision'],status=decision_label(receipt['decision'],truth_clearance),
            named_status=decision_label(sign,truth_clearance),truth_face_km=truth_clearance,receipt=receipt,reason=science['reason'],
            media=media,sidecars=sidecars,graph_proof=observed['graph_proof'],solve=research.get('solve'),
            figure_render=observed.get('one_pass_web_png',observed.get('layout')),
            named_finish=observed['named_survivor_finish'],signed_status=route.get('signed',{}).get('status'),
            signed_refit_clock=route.get('signed_refit_clocks'), isolated=route.get('provisional_salvage'),
            exterior=route.get('exterior'),fallback=research.get('recovered_inference'),
            early_regional=research.get('early_regional'))
    return results


def score(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from full_short_run import RECIPE_SHA
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from north_combined import FAR, FAR_SHA
    from north_interlaced_raw import NORTH, RECEIVER_SHA, SOURCE, SOURCE_SHA, TRUTH_SHA
    from raw_cfo_0016_score import compare_factors, matched_rms
    from raw_cfo_north_trial import ORDER, STOCK_PACKET, STOCK_ROOT, native_file, verified_packet
    from short_raw_diagnostic import require_warm

    request = read(root/'binding.json')
    for name,pin in request['source_sha256'].items():
        checked(HERE/name,pin)
    for label in ('containing','mirror'):
        if read(root/f'{label}-clock.json')['timing']['exit_code']:
            raise ValueError('Both declared child processes must exit successfully before scoring')
    seal = read(root/'raw-packet-seal.json')
    checked(root/ORDER[0]/'unified-short-bootstrap.json',seal['bootstrap_sha256'])
    packet,native,raw = verified_packet(root/ORDER[0],request)
    if seal['native_sha256'] != raw['native_sha256'] or seal['packet'] != str(packet):
        raise ValueError('The saved replay must use the byte-pinned complete raw packet')
    pair = json.loads(checked(SOURCE,SOURCE_SHA))
    omissions = json.loads(checked(FAR,FAR_SHA))
    archived = json.loads(checked(STOCK_ROOT/'sealed.json',STOCK_SEAL))
    stock_binding = json.loads(checked(STOCK_ROOT/'binding.json',STOCK_BIND))
    stock_clock = json.loads(checked(STOCK_ROOT/'stock-clock.json',STOCK_CLOCK))
    historical = archived['results']['stock']
    for page in [historical['cache'],*(p for when in ('before','after') for p in read(root/f'cache-{when}.json').values())]:
        require_warm(page)
    if (archived['binding_sha256'] != STOCK_BIND or historical['clock'] != stock_clock or stock_clock['exit_code']
            or historical['native_sha256'] != STOCK_PACKET or not historical['verified']
            or stock_binding['assignment']['recording'] != request['recording'] or stock_binding['machine'] != request['machine']
            or stock_binding['assignment']['region_sha256'] != request['inside_offer_sha256']
            or stock_binding['assignment']['archive'] != request['archive'] or omissions['pair_sha256'] != SOURCE_SHA
            or omissions['native_sha256'] != STOCK_PACKET or omissions['archive'] != request['archive']):
        raise ValueError('The historical named references must use the same input, region and causal archive')
    named_inside = pair['runs']['candidate']
    named_release = FastStandardAnalysisStore(STOCK_ROOT/'stock').detail(named_inside['receipt']['run_id'])
    if (named_release['input_sha256'] != STOCK_PACKET or named_release['raw_authority'] != request['authority']
            or named_release['terminal_sha256'] != named_inside['receipt']['terminal_sha256']
            or {arm:row['owner_sha256'] for arm,row in named_release['arms'].items()} != named_inside['owners']):
        raise ValueError('The archived North named owners must bind the same terminal')
    named_inside['associated'] = {arm:row['associated_points'] for arm,row in named_release['arms'].items()}
    named, ordinary = (json.loads(checked(native_file(base),pin)) for base,pin in ((STOCK_ROOT/'stock',STOCK_PACKET[7:]),(MIXED_ROOT,MIXED_PIN)))
    for old,pin in ((named,RECEIVER_SHA),(ordinary,RECIPE_SHA)):
        if (old['provenance']['detector_sha256'] != 'sha256:'+pin or old['source']['input_manifest_sha256'] != request['inventory']
                or old['source']['raw_recording_authority_digest'] != request['authority']
                or old['clock_anchor']['before']['realtime_ns'] != request['cutoff_utc_ns']):
            raise ValueError('A comparator packet differs from its enrolled native receiver or acquisition')
    factors, opportunities = compare_factors(named,ordinary,native)
    refinement = raw['receiver_audit']['native']['cfo_refinement']
    attempted = sum(row['counts']['attempted'] for row in refinement['lanes'])
    short_positive = sum(row['refined'] for row in factors['lanes'] if row['mode'] == 'short_primary')
    if (len(opportunities) != 2400 or attempted != short_positive
            or len(factors['changes']) != sum(r['counts']['changed'] for r in refinement['lanes'])):
        raise ValueError('The actual receiver audit must agree with the authenticated factor edits')
    truth_key = json.loads(checked(HERE.parent/'regional-release/scoring-key.json',TRUTH_SHA))
    truth, = {tuple(row['truth']) for row in truth_key['answers'].values() if row['recording'] == NORTH}
    scored = publications(root,request,raw,named_inside,omissions['results'][ORDER[1]],truth,opportunities.keys(),
                          {record['owner_id'] for record in factors['changes']})
    mixed_publication = json.loads(checked(HERE/'measurements/north-combined.json',HISTORICAL_MIXED))['cases']
    write(root/'result.json',dict(verified=True,raw=raw,bind=request,seal=seal,cases=scored,truth=truth,
          original_named_raw_clock=stock_clock,original_named_raw_scope=historical,
          original_named_mirror_solver={key:omissions['results'][ORDER[1]][key] for key in ('solver_cpu_s','solver_wall_s')},
          matched_unrefined_historical={mode:mixed_publication[mode] for mode in ORDER},
          factors=factors,matched_cfo=matched_rms(factors['reference']),
          digests=dict(truth=TRUTH_SHA,named_containing=SOURCE_SHA,named_omission=FAR_SHA,unrefined=MIXED_PIN,
                       named_receipt=STOCK_SEAL,scorer=sha256(Path(__file__).read_bytes()).hexdigest())))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    score(parser.parse_args().root)
