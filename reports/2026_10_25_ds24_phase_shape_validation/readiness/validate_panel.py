"""Validate an eight-case frozen research panel through public contracts only.

No IQ payload, position estimate/error, fit, GLRT regeneration or dataset edit.
"""
import csv
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import traceback
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.storage.fast_scan import FastScanStore
from leo.storage.short_window import ShortWindowReader
from leo.storage.uri import confined_path

HERE = Path(__file__).resolve().parent
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
OLD = Path('/srv/bulk/leo/research/ds25-20261024')


def read(path):
    return json.loads(Path(path).read_bytes())


def write(name, value):
    with (HERE / name).open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False); handle.write('\n')


def binding(path):
    path = Path(path); raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=sha256_digest(raw))


def when(ns):
    return datetime.fromtimestamp(ns/1e9, timezone.utc).isoformat()


def identity_keys(row):
    result = {row.get('recording_id'), row.get('session_id'), row.get('raw_authority_digest'),
              row.get('raw_identity_sha256'), row.get('raw_recording', {}).get('identity_sha256')}
    result.update(row.get('session_ids', []))
    return {v for v in result if isinstance(v, str) and v}


def validate(item, frozen, store):
    path = store.tracking_input_path(frozen['run_id'])
    raw = path.read_bytes()
    assert sha256_digest(raw) == frozen['contract']['sha256'], 'contract changed after input freeze'
    document = json.loads(raw)
    # Dataclass contract validation plus explicit finite/coverage checks below.
    env = dict(os.environ, PYTHONPATH='/home/mouse9911/gits/leo-shared-production-main/src')
    import sys
    checked = subprocess.run([sys.executable,'-B',str(HERE/'validate_tracking_contract.py'),
        str(path),frozen['contract']['sha256']],env=env,capture_output=True,text=True,check=True,timeout=45)
    typed_receipt = json.loads(checked.stdout)
    assert typed_receipt['typed_TrackingInput_valid']
    source = SimpleNamespace(**document['source'])
    source.probes = tuple(SimpleNamespace(**dict(probe,candidates=tuple(SimpleNamespace(**c) for c in probe['candidates'])))
                          for probe in document['source']['probes'])
    assert source.session_id == item['session_id']
    assert source.qualified and source.sample_rate_hz == 10000000 and source.probe_ms == 20
    assert document['provenance']['run_id'] == frozen['run_id']
    inventory = store.source(source.session_id, source.input_manifest_sha256)
    assert inventory['kind'] == 'fast-scan-source' and inventory['recording_name'] == item['recording_id']
    assert canonical_digest(inventory) == source.input_manifest_sha256
    n = inventory['window_count']
    assert n == document['provenance']['window_count']
    manifests = []; index_bindings = []; windows = []; content = []; config_bindings = []
    generations = set(); station_metadata = []; raw_paths = set(); receivers = None
    for entry in inventory['segments']:
        reader = ShortWindowReader(Path(entry['path']))  # constructor reads manifest only
        manifest = reader.manifest
        assert reader.manifest_sha256 == entry['manifest_digest']
        assert manifest.status == 'complete' and not manifest.failure
        assert manifest.window_count == entry['windows'] and manifest.sample_rate_hz == 10000000
        assert manifest.schema_version == 2 and manifest.configuration['sample_rate_hz'] == 10000000
        assert manifest.radio['serial'] == source.radio_id
        if receivers is None: receivers = tuple(manifest.receiver_ids)
        assert tuple(manifest.receiver_ids) == receivers and len(receivers) == 2
        targets = {r['target_id']:r for r in manifest.configuration['targets']}
        assert len(targets) == len(manifest.configuration['targets'])
        configuration_digest = canonical_digest([manifest.configuration, manifest.radio, manifest.receiver_ids])
        config_bindings.append(configuration_digest)
        for key in ('station_id','deployment_id','pose_id','mount_id','setup_id'):
            if key in manifest.configuration:
                station_metadata.append(dict(key=key,value=manifest.configuration[key]))
        manifests.append(dict(path=str(reader.path/'manifest.json'), sha256=reader.manifest_sha256,
            created_utc_ns=manifest.created_utc_ns, finalized_utc_ns=manifest.finalized_utc_ns,
            configuration_digest=configuration_digest, radio_id=source.radio_id,
            receiver_ids=list(receivers), window_count=manifest.window_count))
        raw_paths.add(str(reader.path.parent))
        for chunk in manifest.chunks:
            index_path = confined_path(reader.path, reader.path/chunk.index_relative_path, must_exist=True)
            index_raw = index_path.read_bytes()
            assert len(index_raw) == chunk.index_bytes and sha256_digest(index_raw) == chunk.index_sha256
            index_bindings.append(dict(path=str(index_path),bytes=len(index_raw),sha256=chunk.index_sha256))
            content.append((chunk.compressed_sha256,chunk.index_sha256))
            rows = [ShortWindowIndexV2.model_validate_json(line) for line in index_raw.splitlines()]
            assert len(rows) == chunk.window_count
            offset = 0
            for local,row in enumerate(rows):
                assert row.sequence == chunk.first_sequence+local and row.payload_offset_bytes == offset
                assert row.receiver_count == len(receivers)
                a = row.acquisition; target = targets[row.target_id]
                assert a['global_visit'] == len(windows)
                assert int(a['sample_end'])-int(a['sample_start']) == row.sample_count
                generations.add(a['generation'])
                windows.append(dict(iq_sha256=row.iq_sha256,sample_start=a['sample_start'],
                    sample_end=a['sample_end'],sample_count=row.sample_count,
                    channel=target['channel'],edge=target['edge']))
                offset += row.payload_bytes
            assert offset == chunk.uncompressed_bytes
    assert len(set(config_bindings)) == 1, 'mixed configurations across segments'
    assert len(windows) == n and len(generations) == 1
    assert source.stream_generation == f'continuous-iio-{next(iter(generations)):016x}'
    authority = canonical_digest([source.input_manifest_sha256,[w['iq_sha256'] for w in windows]])
    assert authority == source.raw_recording_authority_digest, 'raw authority does not reconcile'
    content_identity = sha256_digest(json.dumps(sorted(content),separators=(',',':')).encode())
    excluded = document['provenance'].get('excluded_windows',[])
    excluded_ids = {r['visit'] for r in excluded}
    assert len(excluded_ids) == len(excluded) == document['provenance'].get('invalid_capture',0)
    assert all(0 <= v < n for v in excluded_ids)
    for row in excluded:
        assert row['iq_sha256'] == windows[row['visit']]['iq_sha256']
    assert document['provenance'].get('processed_windows',n-len(excluded)) == n-len(excluded)
    probe_keys = set(); candidates = 0
    for probe in source.probes:
        assert probe.visit_index not in excluded_ids
        key = (probe.visit_index,probe.receiver_id,probe.probe_index)
        assert key not in probe_keys; probe_keys.add(key)
        assert probe.receiver_id in receivers and probe.probe_index == 0 and probe.probe_start_ms == 0
        w = windows[probe.visit_index]
        assert probe.channel == w['channel'] and probe.edge == w['edge']
        assert probe.valid_start_counter == w['sample_start']
        assert probe.payload_start_sample == probe.visit_index*200000
        assert math.isfinite(probe.actual_rf_hz) and probe.actual_rf_hz > 0
        ranks = []
        for candidate in probe.candidates:
            ranks.append(candidate.candidate_rank); candidates += 1
            assert candidate.candidate_rank >= 0 and candidate.integer_epoch_sample >= 0
            assert all(math.isfinite(getattr(candidate,key)) for key in (
                'fractional_epoch_offset_samples','fractional_tracking_cfo_hz','fractional_exact_score',
                'fractional_control_score','fractional_margin'))
            assert candidate.passed_fractional_margin_gate == (candidate.fractional_margin >= .025)
        assert len(ranks) == len(set(ranks))
    expected = {(visit,receiver,0) for visit in range(n) if visit not in excluded_ids for receiver in receivers}
    assert probe_keys == expected, 'incomplete valid-window/receiver coverage'
    assert document['last_sample_counter'] == windows[-1]['sample_end']
    captured = min(m['created_utc_ns'] for m in manifests)
    assert captured >= read(HERE/'panel_protocol.json')['cutoff_utc_ns']
    assert len(raw_paths) == 1
    # Exact numerical fields are not position evidence or error lookups.
    tracking = dict(path=str(path),sha256=frozen['contract']['sha256'],
        raw_recording_authority_digest=authority,input_manifest_sha256=source.input_manifest_sha256,
        capture_start_utc_ns=source.capture_start_utc_ns,capture_end_utc_ns=source.capture_end_utc_ns)
    sample = dict(dataset_label=item['research_case'],recording_id=item['recording_id'],
        case_id=item['recording_id']+'-'+content_identity[-12:],session_id=source.session_id,
        session_ids=[source.session_id],mode='fast',recording_format='short_window_iq_recording',
        sample_rate_hz=10000000,channels=sorted({w['channel'] for w in windows}),
        observed_channels=sorted({p.channel for p in source.probes}),captured_utc_ns=captured,
        recording_state='complete',window_count=n,raw_authority_digest=authority,
        raw_identity_sha256=content_identity,source_inputs=[],tracking_inputs=[tracking],
        raw_recording=dict(identity_sha256=content_identity,root=next(iter(raw_paths)),duplicate_roots=[],
            segments=manifests,integrity_errors=[],iq_hash_verification='public manifest/index metadata verified; IQ payloads not read'),
        public_source_binding=dict(port='FastScanStore.source',session_id=source.session_id,
            canonical_inventory_digest=source.input_manifest_sha256))
    assert sample['channels'] == list(range(1,9))
    return dict(case=item['research_case'],recording_id=item['recording_id'],status='ready',
        sample_member=sample,captured_utc=when(captured),contract=frozen['contract'],
        source_contract_type='TrackingInput; fast adapter capture_mode='+source.capture_mode,
        isolated_public_contract_validation=typed_receipt,
        analysis_manifest_digest_declared=source.analysis_manifest_sha256,
        analysis_artifacts_independently_reloaded=False,raw_authority_reconstructed=True,
        raw_content_identity=content_identity,source_inventory_canonical_digest=source.input_manifest_sha256,
        manifests=manifests,index_bindings=index_bindings,configuration_digest=config_bindings[0],
        station_deployment_metadata=station_metadata,radio_id=source.radio_id,
        stream_generation=source.stream_generation,probes=len(source.probes),candidate_records=candidates,
        excluded_windows=len(excluded),valid_window_receiver_coverage_verified=True,
        contract_bytes_rechecked_after_validation=sha256_digest(path.read_bytes())==frozen['contract']['sha256'],
        payloads_read_or_rehashed=False,geographic_exposure='not yet audited')


def main():
    began = time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('600s total input-processing cap')))
    signal.alarm(600)
    protocol = read(HERE/'panel_protocol.json')
    store = FastScanStore('/srv/bulk/leo')
    frozen = []
    for item in protocol['members']:
        job = store.automatic_status(item['recording_id'])
        assert job['state'] == 'complete' and job['session_id'] == item['session_id']
        path = store.tracking_input_path(job['run_id'])
        assert str(path) in {r['path'] for r in item['source_session_matched_contract_metadata']}
        frozen.append(dict(case=item['research_case'],recording_id=item['recording_id'],
            session_id=item['session_id'],run_id=job['run_id'],automatic_state=job['state'],
            contract=binding(path),automatic_job_metadata_sha256=sha256_digest(canonical_json_bytes(job))))
    write('frozen_input_hashes.json',dict(protocol_sha256=binding(HERE/'panel_protocol.json')['sha256'],
        sources=frozen,source_hashes_frozen_before_typed_validation=True))
    rows = []
    for item,source in zip(protocol['members'],frozen,strict=True):
        started = time.monotonic()
        try:
            row = validate(item,source,store)
        except TimeoutError:
            raise
        except Exception as exc:
            row = dict(case=item['research_case'],recording_id=item['recording_id'],status='blocked',
                error=repr(exc),traceback=traceback.format_exc(),frozen_source=source)
        row['seconds'] = time.monotonic()-started
        rows.append(row); write(item['research_case']+'_validation.json',row)
        print(item['research_case'],row['status'],row.get('error',''),round(row['seconds'],3),flush=True)
        gc.collect()
    ready = [r for r in rows if r['status']=='ready']
    # Exposure lookup projects identity columns only; never uses outcome values.
    prior_sample = read(OLD/'sample.json')
    prior_identity = [(r['dataset_label'],identity_keys(r)) for r in prior_sample['selected']]
    with (OLD/'tables/positions.csv').open() as handle:
        table = csv.reader(handle);header=next(table);columns=[header.index(k) for k in ('case','recording_id')]
        table_identities=[(r[columns[0]],r[columns[1]]) for r in table]
    patterns=set()
    for row in ready:
        m=row['sample_member'];keys=identity_keys(m)
        matches=[case for case,prior in prior_identity if keys & prior]
        tablematches=sorted({case for case,recording in table_identities if recording in keys})
        row['prior_DS24_DS25_sample_identity_matches']=matches
        row['prior_DS24_DS25_position_table_identity_matches']=tablematches
        row['geographic_exposure']='no identity match in checked DS24/DS25 authorities; broader human exposure not established'
        patterns.update(keys)
    (HERE/'identity_patterns.txt').write_text('\n'.join(sorted(patterns))+'\n')
    grep=subprocess.run(['git','grep','-l','-F','-f',str(HERE/'identity_patterns.txt'),'HEAD','--',
        'reports/**/*.json','reports/**/*.csv','reports/**/*.md'],cwd=PUBLISHER,capture_output=True,text=True,check=False)
    assert grep.returncode in (0,1),grep.stderr
    matches=grep.stdout.splitlines()
    exposure=dict(prior_sample=binding(OLD/'sample.json'),prior_position_table=binding(OLD/'tables/positions.csv'),
        identity_projection_only=True,no_outcome_values_used=True,publisher_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PUBLISHER,text=True).strip(),
        published_text_files_matching_any_panel_identity=matches,
        known_metadata_only_suffixes=['/audit/exposure_inventory02.json','/audit/exposure_metadata.csv'],
        search_scope='tracked report JSON/CSV/Markdown only; no compressed releases, private notebooks or exhaustive human-exposure proof')
    write('exposure_matches.json',exposure)
    for row in ready:
        assert not row['prior_DS24_DS25_sample_identity_matches']
        assert not row['prior_DS24_DS25_position_table_identity_matches']
    assert [r['sample_member']['captured_utc_ns'] for r in ready] == sorted(r['sample_member']['captured_utc_ns'] for r in ready)
    write('sample.json',dict(study='RX1 rf50 chronological later-input research panel',
        panel_protocol_sha256=binding(HERE/'panel_protocol.json')['sha256'],
        sampling='fixed first8 previous-complete metadata rows; no replacement; failures retained in readiness accounting',
        selected=[r['sample_member'] for r in ready],frozen_panel_size=8,
        unavailable_cases=[r['case'] for r in rows if r['status']!='ready'],dataset_mint=False))
    summary=dict(all_selected_inputs_ready=len(ready)==8,selected=8,ready=len(ready),blocked=8-len(ready),
        rows=[dict(case=r['case'],recording_id=r['recording_id'],status=r['status'],seconds=r['seconds']) for r in rows],
        validation_rows=rows,elapsed_processing_seconds=time.monotonic()-began,processing_cap_seconds=600,
        no_replacement=True,position_fits=0,IQ_payloads_read=False,geographic_errors_or_position_estimates_read=False,
        prior_dataset_identity_matches=0,published_identity_match_file_count=len(matches),
        full_clean_geographic_holdout_claimed=False,source_binding=binding(Path(__file__)))
    write('readiness.json',summary)
    import leo.storage.fast_scan,leo.storage.short_window
    source_modules=[Path(m.__file__) for m in (leo.storage.fast_scan,leo.storage.short_window)]
    write('readiness_seal.json',dict(files={str(p.relative_to(HERE)):binding(p)['sha256'] for p in HERE.glob('*') if p.is_file() and p.name!='readiness_seal.json'},
        public_port_modules=[binding(p) for p in source_modules],processing_seconds=summary['elapsed_processing_seconds'],
        IQ_read=False,position_fits=0,new_geographic_outcomes_read=False))
    print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,(dict,list))}),flush=True)


if __name__ == '__main__':
    main()
