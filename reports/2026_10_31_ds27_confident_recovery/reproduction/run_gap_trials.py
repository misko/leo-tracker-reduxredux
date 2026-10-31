"""Test every eligible predeclared >5-second gap fragment in two parent tracks."""
import concurrent.futures
import sys
from run_trials import STUDY, targets, stage, read, write

def work(t):
    folder=STUDY/t['case'];source=folder/'gap-source/branches.json'
    records=[]
    for branch in read(source)['branches']:
        root=folder/('gap-'+branch['branch_id']);root.mkdir(exist_ok=False)
        validation=root/'annotation';base=[sys.executable,str(STUDY/'gap_stage.py')]
        command=base+['annotate_predictive_only.py','--inventory',t['inventory'],'--output',str(validation),
            '--track',branch['branch_id'],'--native-branches',str(source),'--distinct-partitions',
            '--candidates','3','--folds','3','--uncalibrated-phase-mixture']
        annotation=stage(command,root/'annotation.log',240)
        record=dict(case=t['case'],branch_id=branch['branch_id'],points=len(branch['observation_ids']),annotation=annotation)
        if annotation['state']=='complete':
            result=read(validation/'result.json');record['identity']=result['annotation']
            if result['annotation']['status']=='conditionally_supported_identity':
                for mode,flags in [('gap_default',[]),('gap_conditional',['--conditional-satellite-refresh'])]:
                    trial=root/mode
                    command=base+['include_predictive_annotations.py','--inventory',t['inventory'],
                        '--validation',str(validation),'--output',str(trial),'--native-from-validation',*flags]
                    receipt=stage(command,root/(mode+'.log'),240)
                    if receipt['state']=='complete':
                        command=base+['audit_shared_predictive_inclusion.py','--study',t['recovery'],
                            '--trial',str(trial),'--output',str(trial/'exact_owner_replay.json')]
                        receipt['audit']=stage(command,root/(mode+'-audit.log'),180)
                    record[mode]=receipt
        write(root/'receipt.json',record);records.append(record)
        print(t['case'],branch['branch_id'],record.get('identity'),flush=True)
    return records

if __name__=='__main__':
    ts=[t for t in targets() if t['case'] in ('DS27-0004','DS27-0022')]
    write(STUDY/'gap-protocol.json',dict(cases=[t['case'] for t in ts],gap_s=5,minimum_points=12,
        minimum_span_s=10,all_eligible_fragments_tested=True,identity_revalidated=True,
        random_whole_12s_blocks=True,guard_s=2,distinct_partitions=True,
        no_GPS_inference=True,original_RF_gates=True,production_changed=False,
        hypothesis='A graph parent spanning a recorded time gap need not be a single predictive component',
        limitation='Shorter fragments have a weaker sample-size-dependent correlation test; this is not evidence that correlation disappeared'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(work,ts))
    write(STUDY/'gap-execution.json',result)
