"""Freeze additional-scan observations and archived full visible banks.

Known roof is fixed by the association protocol. No previous fitted nuisance
parameters or candidate shortlist limits the bank. Existing corpus only.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from benchmark import ROOT,OLD,PROTOCOL,canonical_rows,group_folds,digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=int,choices=(0,1),required=True)
    args=parser.parse_args();session=PROTOCOL['additional_scans'][args.index]
    output=ROOT/'additional-scans'/session
    if output.exists():raise FileExistsError(output)
    sys.path.insert(0,str(OLD))
    import exhaustive_subset
    import all_visible_bank as bank
    from finite_set_alias_family import FamilyGeometryData
    from rough_smoke import load_module
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    directory=ROOT.parent/'2026_10_03_ds13_four_scan_curvature/scans'/session
    manifest=json.loads((directory/'bundle.json').read_text())
    if manifest['session_id']!=session:raise ValueError('Session mismatch')
    evidence_path=bank.POPULATION.parent/'analysis'/f'{session}.json'
    product=json.loads(evidence_path.read_text())['tracking']['product']
    for key in ('input_manifest_sha256','analysis_manifest_sha256'):
        if product[key]!=manifest['provenance'][key]:raise ValueError('Evidence binding mismatch')
    source_paths=[directory/'bundle.json',directory/'bundle.npz',evidence_path,ROOT/'frozen/protocol.json',
                  ROOT/'frozen/manifest.json',Path(bank.__file__),Path(__file__)]
    hashes={str(p):digest(p) for p in source_paths}
    module=load_module('additional_bundle',bank.LEGACY/'bundle.py');raw=module.Data(directory)
    raw.reference_time_s=150.;source=FamilyGeometryData(raw,manifest['family_representatives'])
    roof=np.array(json.loads((ROOT/'frozen/manifest.json').read_text())['scans']['A']['known_position_km'])
    nodes=bank._validate_nodes(source.nodes);screen_nodes=bank._visibility_nodes(source.times,nodes,timing_window_s=20.)
    _,_,observers=bank._patch_observers(roof)
    archive=TleArchiveReader(bank.TLE_ROOT)
    helper=load_module('additional_export_helpers',bank.LEGACY/'export_ds11.py')
    tle=helper._snapshot(archive,product,manifest['origin_utc_ns']);raw_payload=archive.read(tle)
    payload,debris=exclude_labelled_starlink_debris(raw_payload);catalogue=parse_element_sets(payload)
    candidates=np.array([i for i,n in enumerate(catalogue.names) if n.strip().upper().startswith('STARLINK')])
    started=time.monotonic();deadline=started+180
    visible,valid,maximum=bank._screen_visible(catalogue,candidates,manifest['origin_utc_ns'],screen_nodes,
                                              observers,propagate_candidate_states,deadline)
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    old=[lookup[int(n)] for n in raw.numbers]
    states=bank._propagate_states(catalogue,list(dict.fromkeys([*old,*sorted(visible)])),manifest['origin_utc_ns'],nodes,
                                  propagate_candidate_states,deadline)
    order=bank._expanded_order(raw.numbers,np.array(catalogue.satellite_numbers),visible,set(states))
    numbers=np.asarray(catalogue.satellite_numbers)[order];mapping={int(n):i for i,n in enumerate(numbers)}
    initial=np.zeros(6+len(numbers));initial[:2]=roof
    arrays=dict(nodes=nodes,numbers=numbers,position=np.array([states[int(i)][0] for i in order]),
        velocity=np.array([states[int(i)][1] for i in order]),initial=initial,old_numbers=raw.numbers,
        old_to_expanded=np.array([mapping[int(n)] for n in raw.numbers]),
        maximum_elevation_sine=np.array([maximum.get(int(i),np.nan) for i in order]),
        screen_visible=np.array([i in visible for i in order]),retained_original=np.array([i in old for i in order]))
    expanded=bank.ExpandedScanData(source,arrays,{'session_id':session})
    canonical,representative=canonical_rows(expanded.measured,expanded.group)
    if time.monotonic()>deadline:raise TimeoutError('Bounded bank export deadline exceeded')
    for path,expected in hashes.items():
        if digest(path)!=expected:raise ValueError('Input changed during export')
    output.mkdir(parents=True)
    np.savez_compressed(output/'expanded.npz',**arrays,**{n:getattr(expanded,n) for n in bank.OBSERVATION_NAMES},original_rows=expanded.original_rows)
    np.savez_compressed(output/'observations.npz',times_s=expanded.times,measured_hz=expanded.measured,
        group=expanded.group,receiver=expanded.receiver,channel=expanded.channel,rf_hz=expanded.rf,
        canonical_rows=canonical,representative=representative,fold=group_folds(expanded.times,expanded.group))
    receipt=dict(session_id=session,scope=__doc__,source_sha256=hashes,known_position_km=roof.tolist(),
        original_family_rows=len(source.times),denominator=len(canonical),distinct_groups=len(np.unique(expanded.group)),
        catalog_count=len(numbers),screened_starlink_count=len(candidates),
        screen_failed_numbers=[int(catalogue.satellite_numbers[i]) for i in candidates if i not in valid],
        visible_full_grid_failed_numbers=[int(catalogue.satellite_numbers[i]) for i in visible if i not in states],
        tle_digest=tle.digest,tle_collected_utc_ns=int(tle.collected_utc_ns),tle_payload_sha256=bank._sha256_bytes(raw_payload.encode()),
        screen_timing_half_window_s=20,screen_patch_half_width_km=bank.PATCH_HALF_WIDTH_KM,
        numerical_seconds=time.monotonic()-started,protocol_sha256=digest(ROOT/'frozen/protocol.json'),
        artifacts={name:digest(output/name) for name in ('expanded.npz','observations.npz')})
    with (output/'receipt.json').open('x') as stream:json.dump(receipt,stream,indent=2)
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
