"""Collect fourth-wave ARM timing and standard-hit audits."""
import json
import collect_wave3 as collector

collector.METHODS = [
    ('wave3-control', 'arm_wave3_combined', 'host704', ['arm4', 'arm4-repeat']),
    ('proposal-preplan', 'arm_proposal_preplan', 'host704', ['arm4']),
    ('rank-fast-v1', 'arm_proposal_rank_fast', 'host704', ['arm4']),
    ('rank-fast-v2', 'arm_proposal_rank_fast_v2', 'host704', ['arm4']),
    ('float-final-ffts', 'arm_wave4_float_fft', 'host704', ['arm4']),
    ('fine-input-neon', 'arm_fine_input_neon', 'host704-fused', ['arm4-fused']),
    ('conditioned-order-neon', 'arm_conditioned_order_neon', 'host704-fused', ['arm4']),
    ('coarse-epoch4', 'arm_coarse_epoch4', 'host704', ['arm4']),
    ('combined-exact-proposals', 'arm_wave4_combined', 'host704', ['arm4', 'arm4-repeat']),
]

if __name__ == '__main__':
    result=collector.collect()
    for method in result['methods']:
        if method['method']=='fine-input-neon':
            method['qualification']='REJECTED: terminal-frame out-of-bounds read reproduced by ASan; aggregate hit audit does not prove correctness'
    (collector.HERE/'wave4-results.json').write_text(json.dumps(result, indent=2)+'\n')
