"""Measurement-only export through the existing pinned public reader.

Run with the deployed multirate source on PYTHONPATH. Every selected segment
is exhausted to complete window, compressed-chunk and raw-chunk digest checks.
"""
import hashlib
import inspect
import json
import signal
import time
from pathlib import Path
import numpy as np
from leo.storage.short_window import ShortWindowReader

OUT=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('240s export cap')));signal.alarm(240)
    protocol=json.loads((OUT/'raw-amended-protocol.json').read_text());plan=json.loads((OUT/'raw-plan.json').read_text())
    old=json.loads((OUT/'raw-pilot-receipt.json').read_text());bindings={p['visit_index']:p for p in old['rows']}
    inventory=json.loads(Path(protocol['input_inventory']).read_text());required={p['visit_index']:p for p in plan['points']}
    panel=OUT/'raw-panel';panel.mkdir(exist_ok=True);rows=[];segments=[];decoded=0
    receipt=dict(status='running',decoded_windows=0,scored_windows=0,selected_windows=18,reader_source=inspect.getfile(ShortWindowReader),
        reader_source_sha256=sha(inspect.getfile(ShortWindowReader)),read_only_recording=True,rows=rows,segments=segments)
    def save():
        receipt['seconds']=time.monotonic()-began;receipt['decoded_windows']=decoded
        (OUT/'raw-export-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    save()
    try:
        start=0
        for number,entry in enumerate(inventory['segments']):
            first,last=start,start+entry['windows'];start=last
            if number not in protocol['selected_segments']:continue
            reader=ShortWindowReader(Path(entry['path']))
            assert reader.manifest_sha256==entry['manifest_digest']
            assert reader.manifest.sample_rate_hz==plan['sample_rate_hz']
            segment=dict(number=number,path=entry['path'],manifest_digest=entry['manifest_digest'],manifest_sha256=sha(reader.path/'manifest.json'),decoded_windows=0,completed=False)
            segments.append(segment);save()
            for window in reader.windows():
                decoded+=1;segment['decoded_windows']+=1
                assert decoded<=protocol['maximum_decoded_windows']
                visit=window.index.acquisition['global_visit']
                if visit not in required:continue
                p=required[visit];bound=bindings[visit]
                assert window.index.iq_sha256==bound['iq_sha256']
                assert window.index.acquisition['sample_start']==p['sample_start']
                rx=reader.manifest.receiver_ids.index(p['receiver_id'])
                values=np.array(window.samples[:,rx,:],copy=True)
                assert values.shape==(200000,2)
                target=panel/f'visit-{visit:06d}.npy';np.save(target,values,allow_pickle=False)
                rows.append(dict(visit_index=visit,array=str(target),array_sha256=sha(target),raw_window_iq_sha256=window.index.iq_sha256,receiver_id=p['receiver_id']))
            assert segment['decoded_windows']==entry['windows']
            segment['completed']=True;save();print('segment',number,'decoded',segment['decoded_windows'],'selected',len(rows),'seconds',round(time.monotonic()-began,2),flush=True)
        assert len(rows)==len(required)==18
        assert {r['visit_index'] for r in rows}==set(required)
        receipt['status']='complete';receipt['all_selected_segment_and_window_digests_verified']=True;save()
    except Exception as exc:
        receipt['status']='failed';receipt['error']=f'{type(exc).__name__}: {exc}';save();raise


if __name__=='__main__':main()
