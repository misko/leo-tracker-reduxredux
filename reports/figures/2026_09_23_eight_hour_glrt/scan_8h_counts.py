import argparse
import json
import time
from pathlib import Path
from collections import Counter
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis

parser=argparse.ArgumentParser(description='Verify saved adaptive GLRT products and count passing candidates per receiver.')
parser.add_argument('--inventory',type=Path,required=True)
parser.add_argument('--bulk-root',type=Path,default=Path('/srv/bulk/leo'))
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():
    raise FileExistsError('Choose a fresh count output path')
inventory=json.loads(args.inventory.read_text())
store=ScannerTrackingInputStore(args.bulk_root)
results=[]
started=time.monotonic()
try:
    for ix,meta in enumerate(inventory['sessions'],1):
        row=dict(meta)
        try:
            if meta['mode']!='adaptive':
                raise ValueError('Fixed-mode recording requires explicit separate count path')
            pub=store.adaptive.inspect(meta['session_id'])
            m=pub.manifest
            receipt=m.receipt
            row.update(sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
                       receivers=list(receipt.plan.geometry.receiver_ids),
                       capture_state=receipt.terminal.state,
                       source_span_attested=receipt.source_span_attested,
                       complete_visit_count=receipt.complete_visit_count,
                       retained_visit_count=len(getattr(receipt,'retained_visit_indices',range(receipt.complete_visit_count))),
                       capture_seconds=(receipt.terminal.final_counter-receipt.terminal.first_counter)/receipt.plan.geometry.sample_rate_hz,
                       input_manifest_sha256=pub.manifest_sha256)
            binding=bind_actual_visit_analysis(receipt,input_manifest_sha256=pub.manifest_sha256,probe_stride_ms=120)
            counts={str(rx):Counter() for rx in receipt.plan.geometry.receiver_ids}
            with store.adaptive_analysis.job(binding) as job:
                metrics=job.manifest()
                if metrics is None:
                    raise ValueError('Metrics incomplete')
                row['configuration']=metrics.configuration.model_dump(mode='json')
                visits=0
                for visit in job.published_visits():
                    visits+=1
                    for probe in visit.probes:
                        c=counts[str(probe.receiver_id)]
                        c['probes']+=1
                        c['acquired_candidates']+=probe.candidate_count
                        c['complete_fractional_candidates']+=len(probe.candidates)
                        c['unavailable_candidates']+=len(probe.unavailable_candidates)
                        passing=sum(candidate.passed_fractional_margin_gate for candidate in probe.candidates)
                        c['glrt_detections']+=passing
                        c['probes_with_detection']+=int(passing>0)
                assert visits==len(metrics.visits)
                assert sum(c['glrt_detections'] for c in counts.values())==sum(v.passed_fractional_candidate_count for v in metrics.visits)
                assert sum(c['acquired_candidates'] for c in counts.values())==sum(v.candidate_count for v in metrics.visits)
                row['analysis_state']='complete_verified'
                row['analysis_binding_sha256']=binding.sha256
                row['counts']=counts
        except Exception as e:
            row['analysis_state']='unavailable_or_error'
            row['error']=f'{type(e).__name__}: {e}'
            print('ERROR',row['session_id'],row['error'],flush=True)
        results.append(row)
        args.output.write_text(json.dumps({**inventory,'results':results,'elapsed_s':time.monotonic()-started},indent=2)+'\n')
        if ix%4==0 or ix==len(inventory['sessions']):
            print(f'{ix}/{len(inventory["sessions"])} verified in {time.monotonic()-started:.1f}s',flush=True)
finally:
    store.close()
