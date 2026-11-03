"""Bind public metrics completion and exact export-policy orbit snapshots."""
import hashlib
import inspect
import json
from pathlib import Path
import time
from leo.contracts.digests import canonical_digest
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_set_records
from availability_policy import available,orbit_available

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    started=time.monotonic();ip=HERE.parent/'acquisition-calibration-inventory.json'
    cutoff=json.loads(ip.read_text())['earliest_target_utc_ns']
    captures=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    analyses=AdaptiveHopAnalysisStore(Path('/srv/bulk/leo'),read_only=True)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshots=archive.list_snapshots()
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'availability_policy.py',ip)}
    for obj in (canonical_digest,AdaptiveHopIqStore,AdaptiveHopAnalysisStore,bind_actual_visit_analysis,TleArchiveReader,parse_element_set_records):
        p=Path(inspect.getfile(obj));sources[str(p)]=digest(p)
    rows=[];cache={}
    try:
        for ordinal in range(4):
            path=HERE/f'capture-{ordinal:02d}.json';doc=json.loads(path.read_text());sources[str(path)]=digest(path)
            published=captures.inspect(doc['session_id']);assert published.manifest_sha256==doc['input_manifest_sha256']
            binding=bind_actual_visit_analysis(published.manifest.receipt,input_manifest_sha256=published.manifest_sha256,probe_stride_ms=120)
            with analyses.job(binding) as job:metrics=job.manifest()
            assert metrics is not None
            data=metrics.model_dump(mode='json');assert canonical_digest(data)==doc['analysis_manifest_sha256']
            assert data['input_manifest_sha256']==doc['input_manifest_sha256']
            capture=doc['capture_metadata'];finalized=int(data['finalized_utc_ns'])
            qualified=available(capture['capture_end_utc_ns'],capture['finalized_utc_ns'],finalized,cutoff)
            start=published.manifest.timing.first_sample_estimate_utc_ns
            selected=[]
            for provider in sorted({r.provider for r in snapshots}):
                choices=[r for r in snapshots if r.provider==provider and r.collected_utc_ns<start-505_000_000_000]
                if not choices:continue
                ref=max(choices,key=lambda r:(r.collected_utc_ns,r.sha256));mtime=ref.path.stat().st_mtime_ns
                sources[str(ref.path)]=digest(ref.path)
                if ref.digest not in cache:
                    text=archive.read(ref);assert hashlib.sha256(text.encode()).hexdigest()==ref.sha256
                    filtered,_=exclude_labelled_starlink_debris(text)
                    records=parse_element_set_records(filtered);cache[ref.digest]=(len(records),sum(r.name.upper().startswith('STARLINK') for r in records))
                count,starlink=cache[ref.digest]
                selected.append(dict(provider=provider,snapshot_sha256=ref.digest,path=str(ref.path),request_utc_ns=ref.collected_utc_ns,
                                     local_mtime_ns=mtime,available_before_capture=orbit_available(ref.collected_utc_ns,mtime,start),
                                     records=count,starlink_records=starlink))
            baseline=archive.select_latest_before(start-505_000_000_000)
            assert any(r['snapshot_sha256']==baseline.digest for r in selected)
            rows.append(dict(ordinal=ordinal,session_id=doc['session_id'],family=doc['family'],
                             analysis_finalized_utc_ns=finalized,analysis_lead_to_ds11_s=(cutoff-finalized)/1e9,
                             recorded_analysis_available=qualified,metrics_manifest=data,
                             input_manifest_sha256=doc['input_manifest_sha256'],analysis_manifest_sha256=doc['analysis_manifest_sha256'],
                             baseline_snapshot_sha256=baseline.digest,provider_sources=selected,
                             orbit_archive_available=bool(selected and all(r['available_before_capture'] and r['starlink_records']>0 for r in selected))))
    finally:captures.close();analyses.close()
    out=dict(cutoff_utc_ns=cutoff,rows=rows,sources=sources,
             passed=all(r['recorded_analysis_available'] and r['orbit_archive_available'] for r in rows),
             metadata_completion_evidence_not_independent_attestation=True,propagation_checked=False,
             calibration_ready=False,elapsed_s=time.monotonic()-started)
    with (HERE/'availability.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(dict(passed=out['passed'],elapsed_s=out['elapsed_s'],rows=[{k:r[k] for k in ('ordinal','family','analysis_lead_to_ds11_s','recorded_analysis_available','orbit_archive_available')} for r in rows]),indent=2))


if __name__=='__main__':main()
