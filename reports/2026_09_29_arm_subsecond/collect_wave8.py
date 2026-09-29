"""Verify and summarize Wave8 comparisons without mixing timing panels."""
import hashlib,json,re
from collect_wave6 import HERE, read_cohort, directory

def actual_dwell_mean(short):
    values=[]
    for line in (directory(short)/'rows.jsonl').read_text().splitlines():
        record=json.loads(line)
        assert record['returncode']==0 and len(record['rows'])==22
        values.append(sum(row['timings_ms']['fused_total'] for row in record['rows']))
    return sum(values)/len(values)

def input_prep_result(filename):
    path=directory('arm_wave8_integer_input')/filename
    record=json.loads(path.read_text());rates={}
    for line in record['stdout'].splitlines():
        match=re.fullmatch(r'rate=(\d+) baseline_ms=([0-9.]+) integer_ms=([0-9.]+) exact=(\d+)',line)
        assert match and match.group(4)=='1'
        rates[match.group(1)]={'control_ms':float(match.group(2)),'candidate_ms':float(match.group(3))}
    return {'path':str(path.relative_to(HERE.parent.parent)),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rates':rates}

def context_rows(short):
    path=directory(short)/'rows.jsonl';records={}
    for line in path.read_text().splitlines():
        record=json.loads(line);context=record['context']
        identity=(context['session_id'],context['visit_index'])
        assert identity not in records
        assert record.get('returncode',0)==0 and len(record['rows'])==22
        metadata=(context['sample_start_counter'],context['sample_end_counter'],
                  context['rate_hz'],context['target']['channel'],context['target']['edge'])
        records[identity]={'metadata':metadata,
            'outer_cpu_ms':sum(row['timings_ms']['fused_total'] for row in record['rows'])}
    return records,{'path':str(path.relative_to(HERE.parent.parent)),
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def paired_large_subsets():
    candidate,candidate_binding=context_rows('arm_wave8_gate_pgo/arm152')
    control,control_binding=context_rows('arm_wave8_gate_pgo/arm152-control')
    assert len(candidate)==len(control)==152 and candidate.keys()==control.keys()
    assert all(candidate[key]['metadata']==control[key]['metadata'] for key in candidate)
    training,training_binding=context_rows('arm_wave8_gate_pgo/training4')
    heldout,heldout_binding=context_rows('arm_wave6_pgo/heldout32-reference')
    all_ids=set(candidate);training_ids=set(training);heldout_ids=set(heldout)
    assert len(training_ids)==4 and len(heldout_ids)==32
    assert training_ids<=all_ids and heldout_ids<=all_ids and training_ids.isdisjoint(heldout_ids)
    def summarize(ids):
        ordered=sorted(ids);count=len(ordered);assert count
        candidate_mean=sum(candidate[key]['outer_cpu_ms'] for key in ordered)/count
        control_mean=sum(control[key]['outer_cpu_ms'] for key in ordered)/count
        return {'dwells':count,'candidate_mean_outer_cpu_ms_per_dwell':candidate_mean,
                'control_mean_outer_cpu_ms_per_dwell':control_mean,
                'reduction_from_control':1-candidate_mean/control_mean}
    without_training=all_ids-training_ids
    without_heldout=all_ids-heldout_ids
    without_either=all_ids-training_ids-heldout_ids
    assert len(without_training)==148 and len(without_heldout)==120 and len(without_either)==116
    return {'bindings':{'candidate':candidate_binding,'control':control_binding,
                        'training4':training_binding,'heldout32':heldout_binding},
            'all152':summarize(all_ids),'heldout32':summarize(heldout_ids),
            'excluding_training4':summarize(without_training),
            'excluding_heldout32':summarize(without_heldout),
            'excluding_training4_and_heldout32':summarize(without_either)}

def collect():
    cases={
        'rank_pgo_32': 'arm_wave8_frontier_rank_pgo/arm-heldout32',
        'gate_pgo_32': 'arm_wave8_gate_pgo/arm-heldout32',
        'gate_arm4': 'arm_wave8_gate_frontier/arm4-314',
        'fp32_final_arm4': 'arm_wave8_frontier_float_final/arm4',
        'adaptive_q_arm4': 'arm_wave8_adaptive_q_glrt/arm4',
        'gate_host704': 'arm_wave8_gate_frontier/host704-314',
        'gate_host_ds8': 'arm_wave8_gate_frontier/host-ds8-314-retry',
        'gate_host_ds9': 'arm_wave8_gate_frontier/host-ds9-314',
    }
    result={name:read_cohort(path) for name,path in cases.items()}
    assert all(result.values())
    baseline=actual_dwell_mean('arm_wave6_pgo/heldout32-reference')
    for name in ('rank_pgo_32','gate_pgo_32'):
        row=result[name]
        assert row['summary']['dwells']==32 and row['summary']['windows']==704
        assert row['hits']['reference_positive_hits']==921
        assert abs(actual_dwell_mean(cases[name])-row['summary']['mean_timings_ms']['fused_total'])<1e-8
        row['reduction_from_wave5']=1-row['summary']['mean_timings_ms']['fused_total']/baseline
    assert result['gate_pgo_32']['summary']['candidate_entries']==997
    assert result['gate_pgo_32']['hits']['recovered_positive_hits']==849
    assert result['gate_host_ds8']['hits']['recovered_positive_hits']==745
    assert result['gate_host_ds8']['hits']['reference_positive_hits']==785
    assert result['gate_host_ds9']['hits']['recovered_positive_hits']==861
    assert result['gate_host_ds9']['hits']['reference_positive_hits']==908
    large_candidate=read_cohort('arm_wave8_gate_pgo/arm152')
    large_control=read_cohort('arm_wave8_gate_pgo/arm152-control')
    larger=None
    if large_candidate is not None and large_control is not None:
        assert large_candidate['summary']['dwells']==large_control['summary']['dwells']==152
        assert large_candidate['summary']['windows']==large_control['summary']['windows']==3344
        larger={'gate_pgo':large_candidate,'wave5_control':large_control,
                'reduction_from_wave5':1-large_candidate['summary']['mean_timings_ms']['fused_total']/large_control['summary']['mean_timings_ms']['fused_total'],
                'paired_context_subsets':paired_large_subsets()}
    return {'schema':'arm-wave8-comparison/v1','matched_wave5_heldout32_ms':baseline,
            'heldout32_half_target_ms':baseline/2,'larger_arm152':larger,
            'rejected_input_preparation':{'scalar_integer':input_prep_result('arm-result.json'),
                                          'neon_widening':input_prep_result('arm-result-v3.json')},
            'scope':'Dense 22-window workload; frozen original reference, not current sparse production; PGO holdout excludes training but DS7 was used for method selection.',
            'cases':result}

if __name__=='__main__':
    result=collect()
    (HERE/'wave8-results.json').write_text(json.dumps(result,indent=2)+'\n')
    for name,row in result['cases'].items():
        print(name,row['summary']['mean_timings_ms']['fused_total'],
              row['hits']['recovered_positive_hits'],row['hits']['reference_positive_hits'])
