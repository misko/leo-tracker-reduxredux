"""Read-side export through the deployed multirate ShortWindowReader port.

Run with the immutable deployed reader on PYTHONPATH, not the older research
reader. This script does no signal fitting and never modifies recording data.
"""
import argparse,hashlib,inspect,json
from pathlib import Path
import numpy as np


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def export(args):
    from leo.storage.short_window import ShortWindowReader
    from leo.contracts.digests import canonical_digest
    plan=json.loads(args.plan.read_text());inventory=json.loads(args.inventory.read_text())
    if 'sha256:'+canonical_digest(inventory).removeprefix('sha256:')!=plan['input_manifest_digest']:
        raise ValueError('input inventory authority differs')
    args.output.mkdir(parents=True,exist_ok=False)
    required={p['visit_index']:p for p in plan['points']}
    if len(required)!=len(plan['points']):raise ValueError('one frozen receiver per visit required')
    total=0;exported=[];authorities=[];read_count=0
    for entry in inventory['segments']:
        first,last=total,total+entry['windows'];total=last
        selected={v:p for v,p in required.items() if first<=v<last}
        if not selected:continue
        reader=ShortWindowReader(Path(entry['path']))
        if reader.manifest_sha256!=entry['manifest_digest']:raise ValueError('segment manifest differs')
        if reader.manifest.sample_rate_hz!=plan['sample_rate_hz']:raise ValueError('sample rate differs')
        authorities.append(dict(path=str(reader.path/'manifest.json'),sha256=sha(reader.path/'manifest.json')))
        # Consume full selected segments to complete chunk-level hash checks.
        for window in reader.windows():
            read_count+=1;visit=window.index.acquisition['global_visit']
            if visit not in selected:continue
            p=selected[visit]
            if window.index.iq_sha256!=p['iq_sha256'] or window.index.acquisition['sample_start']!=p['sample_start']:
                raise ValueError('raw window differs from native measurement')
            rx=reader.manifest.receiver_ids.index(p['receiver_id']);samples=np.array(window.samples[:,rx,:],copy=True)
            if samples.shape!=(plan['window_samples'],2):raise ValueError('window geometry differs')
            name=f'visit-{visit:06d}.npy'
            with (args.output/name).open('xb') as f:np.save(f,samples,allow_pickle=False)
            exported.append(dict(p,array=name,array_sha256=sha(args.output/name)))
    if len(exported)!=len(required):raise ValueError('not every nominated point exported')
    reader_path=Path(inspect.getfile(ShortWindowReader));import leo.contracts.multirate_window_recording as contracts
    write(args.output/'manifest.json',dict(points=exported,sample_rate_hz=plan['sample_rate_hz'],raw_windows_read=read_count,
        input_inventory=str(args.inventory),input_inventory_sha256=sha(args.inventory),plan_sha256=sha(args.plan),
        recording_manifests=authorities,reader_source=str(reader_path),reader_source_sha256=sha(reader_path),
        multirate_contract_source=inspect.getfile(contracts),multirate_contract_source_sha256=sha(inspect.getfile(contracts)),
        exporter_source_sha256=sha(__file__),all_selected_windows_hash_verified=True,no_new_RF=True))
    print('exported',len(exported),'points; verified',read_count,'raw windows',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','inventory','output'):p.add_argument('--'+name,type=Path,required=True)
    export(p.parse_args())
