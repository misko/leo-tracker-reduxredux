"""Read existing capture metadata; never contact or control radio hardware."""
import argparse,hashlib,json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--recording',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args()
if args.output.exists():raise FileExistsError('Use a new metadata receipt')
sources=[]
def read(path):
    data=path.read_bytes();sources.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest()))
    return json.loads(data)
run=read(args.recording/'run.json');readbacks=read(args.recording/'lower-tuning-readbacks.json')
segments=[]
for path in sorted(args.recording.glob('*/manifest.json')):
    d=read(path);segments.append(dict(session_id=d['session_id'],radio=d['radio'],status=d['status']))
result=dict(recording=run['run_id'],configuration_sha256=run['configuration_sha256'],
    calibration_id=run['configuration'].get('calibration_id'),targets=run['configuration']['targets'],
    mapping_authorities=sorted({t['rf_mapping_authority'] for t in run['configuration']['targets']}),
    configured_reference_lo_hz=sorted({t['lnb_lo_hz'] for t in run['configuration']['targets']}),
    sdr_if_readback_matches_nominal=all(r['applied_if_hz']==r['nominal_if_hz'] for r in readbacks),
    segment_count=len(segments),segments=segments,sources=sources,
    qualification='These receipts qualify the recorded SDR IF tuning arithmetic, not the physical LNB LO state. The target RF mappings are explicitly hypotheses. physical_lnb_control_changed=false reports that the capture did not change that control; it does not establish either receiver LO state or exclude an external controller. No RF data was collected or changed by this audit.')
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(dict(mapping_authorities=result['mapping_authorities'],segments=len(segments),
    control_flags=sorted({s['radio'].get('physical_lnb_control_changed') for s in segments}),
    if_readbacks_match=result['sdr_if_readback_matches_nominal'])))
