"""Run unchanged report algorithms in an isolated additional-scan namespace.

A/B below are compatibility slots, not the original development scans. The
manifest binds each slot to its frozen additional session. Slot A retains the
existing .8/13 detection prior and B .8/15, without outcome-dependent tuning.
"""
import argparse,importlib,json,shutil,sys
from contextlib import contextmanager
from benchmark import ROOT,OLD,PROTOCOL,digest
from additional_data import load_additional

OUTPUT=ROOT/'additional-comparison'
MAPPING=dict(zip(('A','B'),PROTOCOL['additional_scans']))
STAGES={'bootstrap':'coherent_bootstrap','calibration':'training_calibration',
        'discovery':'adaptive_discovery','union':'training_union','decode':'heldout_decoders','identity':'heldout_identity'}


@contextmanager
def redirected(module,runtime,output,mapping,loader,argv):
    previous=(module.ROOT,module.SESSIONS,runtime.load_expanded_scan,sys.argv)
    module.ROOT=output;module.SESSIONS=mapping;runtime.load_expanded_scan=loader;sys.argv=argv
    try:yield
    finally:module.ROOT,module.SESSIONS,runtime.load_expanded_scan,sys.argv=previous


def prepare():
    manifest_path=OUTPUT/'frozen/manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        if {k:v['session_id'] for k,v in manifest['scans'].items()}!=MAPPING:raise ValueError('Additional slot mapping changed')
        for path,expected in manifest['source_sha256'].items():
            if digest(path)!=expected:raise ValueError(f'Frozen additional algorithm/input changed: {path}')
        return
    if OUTPUT.exists():raise FileExistsError('Partial additional setup; inspect before continuing')
    scans={};sources={}
    for label,session in MAPPING.items():
        _,receipt=load_additional(session)
        path=ROOT/'additional-scans'/session/'receipt.json';sources[str(path)]=digest(path)
        scans[label]=dict(session_id=session,known_position_km=receipt['known_position_km'],
                          denominator=receipt['denominator'],detection_probability=.8/(13 if label=='A' else 15))
    for name in (*STAGES.values(),'additional_pipeline','additional_data','benchmark','feasible_tracklets','sparse_activity'):
        path=ROOT/f'{name}.py';sources[str(path)]=digest(path)
    (OUTPUT/'frozen').mkdir(parents=True)
    shutil.copyfile(ROOT/'frozen/protocol.json',OUTPUT/'frozen/protocol.json')
    for label,session in MAPPING.items():
        shutil.copyfile(ROOT/'additional-scans'/session/'observations.npz',OUTPUT/'frozen'/f'{label}-observations.npz')
    with manifest_path.open('x') as stream:
        json.dump(dict(scope=__doc__,scans=scans,source_sha256=sources,original_goal_protocol_sha256=digest(ROOT/'frozen/protocol.json')),
                  stream,indent=2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=STAGES,required=True)
    parser.add_argument('--scan',choices=MAPPING,required=True);parser.add_argument('--fold',type=int,choices=range(5),required=True)
    parser.add_argument('--arm',choices=('fitted-c','zero-c'));args=parser.parse_args()
    if (args.stage=='discovery')!=(args.arm is not None):raise ValueError('--arm is required only for discovery')
    prepare()
    if args.stage=='bootstrap' and (OUTPUT/'training-coherent-bootstrap'/f'fold-{args.fold}'/f'{args.scan}.json').exists():
        raise FileExistsError('Preserve existing bootstrap')
    sys.path.insert(0,str(OLD));import exhaustive_subset as runtime
    module=importlib.import_module(STAGES[args.stage])
    def loader(session):return load_additional(session)[0]
    argv=[module.__file__,'--scan',args.scan,'--fold',str(args.fold)]
    if args.arm:argv+=['--arm',args.arm]
    print('Additional scan',MAPPING[args.scan],'slot',args.scan,'stage',args.stage,'fold',args.fold,flush=True)
    with redirected(module,runtime,OUTPUT,MAPPING,loader,argv):module.main()


if __name__=='__main__':main()
