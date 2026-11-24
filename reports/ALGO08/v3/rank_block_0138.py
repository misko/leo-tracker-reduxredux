"""Audit an anchor-block rank bound from the installed source and saved clocks."""

import gzip
from hashlib import sha256
import json
from math import fsum, log1p
from pathlib import Path
from statistics import median


MEASUREMENTS = Path(__file__).resolve().parent/'measurements'
RELEASE = Path('/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3')
VARIANTS = Path('/opt/leo-algo08/algo08v3/payload/tools/pipeline_eval/variants')
ROUTE = Path('/dev/shm/leo-v3-history-risk-0138-pair02/routed/risk-route.json')
FILES = {
    'profile': (MEASUREMENTS/'inference-0138-functions.json.gz', '2e956fd46174dc499d04b252eda8616c3873208acfbda5ad08655bc37f1851aa'),
    'dense_rank': (MEASUREMENTS/'catalogue-block-dense-pair.json.gz', 'f018d6337a58a1c91014a9b36d1020555bbf9bdc31b39fc3c6f144eaa0a2c11b'),
    'contrast': (MEASUREMENTS/'curvature-filter.json', '39fc851292f933ece4261dcb6d8c4f8444822ca6343cb0f5b419ce1d2ab481ec'),
    'panel': (MEASUREMENTS/'history-risk-six-case.json.gz', '7463c2ddd0597a962a5e62ffc653616c960013b7a8178c1c3820b9a713cc80bc'),
    'route': (ROUTE, '1ce09cff6155d2cdf3efbad8344bc51def0ee1c7e435cd1b5acb2d08ca408d58'),
}
MODULES = {
    VARIANTS/'v5_core.py': '30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407',
    VARIANTS/'algo08_dense_discovery.py': 'd8c221ba3240de78b7dad1d657c0c01d425b9384658aa7ed9a7679c28b8439f1',
    RELEASE/'hierarchical.py': 'c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e',
    RELEASE/'position.py': 'c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d',
    RELEASE/'discovery.py': '7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a',
    RELEASE/'families.py': 'd165b623a36a1a3c396348b665ca5a9ad51342c6bc7472d5b05694cc1619150c',
}


def load(path, expected):
    body = path.read_bytes()
    if path.suffix == '.gz':
        body = gzip.decompress(body)
    if sha256(body).hexdigest() != expected:
        raise ValueError(f'Unrecognized evidence at {path}')
    return body


def grouped_gamma_floor(energy, count, *, beta=2.):
    """Exact-real relaxation of one stock unit-power data and Gamma penalty."""
    if not (energy >= 0 and count > 0 and beta > 0):
        raise ValueError('Require nonnegative energy and positive count and rate')
    return (2*beta+count)*log1p(energy/(2*beta))


def rank_edges(profile):
    cold, = profile['cold']
    clock, = cold['rank_calls']
    direct = {}
    for row in cold['functions']:
        edges = [c for c in row['callers'] if Path(c['path']).name == 'v5_core.py' and c['name'] == 'ranked_initial_nodes']
        if edges:
            edge, = edges
            direct[Path(row['path']).name, row['name']] = edge
    scopes = {label: direct[port] for label, port in {
        'centre_nomination': ('discovery.py','fresh_discovery'),
        'corner_exploration': ('algo08_dense_discovery.py','exploration'),
        'corner_alias_construction': ('families.py','__init__'),
        'normal_position_construction': ('position.py','__init__'),
        'normal_position_scoring': ('position.py','residual'),
    }.items()}
    if [row['calls'] for row in scopes.values()] != [1,4,4,7,7]:
        raise ValueError('Unexpected seed/anchor or fixed-rank counts')
    created = direct['discovery.py','signature']['calls']
    if created != 8 or fsum(row['inclusive_s'] for row in scopes.values()) > clock['cpu_ns']/1e9:
        raise ValueError('Rank scopes overlap or do not match the original eight outputs')
    finish = fsum(scopes[name]['inclusive_s'] for name in ('normal_position_construction','normal_position_scoring'))
    return dict(enclosing=clock, scopes=scopes, proposals_before_dedup=created, distinct=7,
                post_signature_all_scores_free_upper_cpu_s=finish)


def scored_dense(receipt):
    result = receipt['result']['rank']
    ranks = result['paired']
    scores = ranks['original_scores']
    if (scores != sorted(scores) or len(scores) != result['ordered_ranks'] or len(scores) < 4
            or scores != ranks['candidate_scores'] or not ranks['ordered_signatures_match']):
        raise ValueError('Expected exact control scores for the complete saved ordering')
    return dict(scores=scores, third_score=scores[2], fourth_gap=scores[3]-scores[2],
                relative_fourth_gap=(scores[3]-scores[2])/scores[2])


def held_route(document):
    result, = document['solves']
    trial, = result['lean_attempts']
    cold = trial['cold']
    prefix = {row['branch']: row['score'] for row in cold['prefix']}
    final = {row['branch']: row['score'] for row in cold['completed']}
    return dict(catalogue=cold['catalogue'], status=cold['routing'], exact_origin_order=list(prefix),
                prefix_order=sorted(prefix, key=prefix.get), final_order=sorted(final, key=final.get),
                prefix_scores=prefix, final_scores=final, pairwise_track_overlap=cold['overlap'])


def panel_budget(panel):
    enrolled = panel['enrolled']
    candidates, reference = {}, {}
    for case in panel['case_order']:
        row = enrolled[case]
        candidates[case] = row['result']['clock']['elapsed_s']+row['source_stage']['preflight']['elapsed_ns']/1e9
        reference[case] = row['result']['archive_stock_clock']['elapsed_s']
    infer, = enrolled['0138']['result']['prep_timing']['infer']
    clock = infer['elapsed_ns']/1e9
    return dict(original_inference_s=clock,
                uniform_6_78_percent_equivalent_s=clock*.0678, uniform_40_09_percent_equivalent_s=clock*.4009,
                original_median=median(candidates[key]/sec for key,sec in reference.items()),
                zero_0138_candidate_optimistic_median=median((candidates[key] if key!='0138' else 0)/sec
                                                            for key,sec in reference.items()),
                stock_target_s=reference['0138']*.5)


def main():
    for path, pin in MODULES.items():
        load(path, pin)
    data = {label: json.loads(load(*values)) for label,values in FILES.items()}
    contrast = {key: {field: value[field] for field in ('catalogue_rows','filter','fallback_fraction','credited_gross_cpu_s')}
                for key,value in data['contrast'].items()}
    rank = rank_edges(data['profile'])
    output = dict(source_sha256={str(path): pin for path,pin in MODULES.items()},
                  receipts={key: val[1] for key,val in FILES.items()}, measured_0138=rank,
                  dense_top_three=scored_dense(data['dense_rank']), observed_0138=held_route(data['route']),
                  archived_exact_contrast=contrast, saved_gates=panel_budget(data['panel']),
                  illustrative_gamma_floor=dict(energy=10_000, count=100, softened=grouped_gamma_floor(10_000,100)),
                  certified_distinct_anchor_blocks_skippable_with_common_bound=0, numerical_runs=0)
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
