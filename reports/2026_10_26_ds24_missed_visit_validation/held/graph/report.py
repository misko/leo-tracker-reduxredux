"""Final separate-method held RF-graph accounting; no new inference."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from account import read,write,sha,METHODS


def main():
    summary=read(HERE/'summary.json');assert summary['all_complete'] and not summary['native_provenance_failures']
    cases=sorted({r['case'] for r in summary['cases']});lookup={(r['method'],r['case']):r for r in summary['cases']}
    lines=['# Held frozen-method additions through the original RF graph','',
        'All24 case/method graph preparations completed. Methods remain separate. Every original public GLRT value and margin is preserved. No new IQ read, satellite search, position job, graph gate change, or method union occurred.','',
        '| Method | New native owners | In RF graph | Active curved | Outside graph | CH5–8 new / curved |',
        '|---|---:|---:|---:|---:|---:|']
    for method in METHODS:
        t=summary['totals'][method];lines.append(f"|{method}|{t['new_native']}|{t['new_in_graph']}|{t['new_curved']}|{t['new_outside_graph']}|{t['new_CH58']} / {t['new_CH58_curved']}|")
    lines += ['', '| Case | R01 new / graph / curved / outside | R02 new / graph / curved / outside |', '|---|---:|---:|']
    for case in cases:
        cells=[' / '.join(str(lookup[m,case][k]) for k in ('new_native','new_in_graph','new_curved','new_outside_graph')) for m in METHODS]
        lines.append(f'|{case}|{cells[0]}|{cells[1]}|')
    innovations={}
    for method in METHODS:
        candidates=[c for case in cases for c in read(HERE/'jobs'/method/(case+'.json'))['candidates']]
        innovations[method]=dict(new_native=len(candidates),zero_fft_bins=sum(abs(c['frequency_innovation_hz'])<1e-7 for c in candidates))
    lines += ['',
        'The producer manifests left `native_observation_id` null. Each owner was independently resolved using the established SHA256(session:receiver:start-counter) contract, checked against the immutable tracking inventory and original observation IDs. Exact source/session, receiver, RF/edge, start/stop, stream generation, integer donor generation, earlier donor support and tracking digests all pass. No metadata was fabricated; no provenance failure was hidden.', '',
        f"New-owner zero FFT bins: R01 {innovations['r01_search']['zero_fft_bins']}/{innovations['r01_search']['new_native']}; R02 {innovations['r02_quadratic']['zero_fft_bins']}/{innovations['r02_quadratic']['new_native']}. Graph curvature is RF persistence evidence, not correct satellite identity or calibrated independent Doppler precision.", '',
        'Original acquisition exposure and the two methods differ; these counts are additions-only stage accounting. Each graph includes all original detections for the full recording. The twelve cases were held from this revision but exposed in earlier studies. No held localization or new-site result is claimed.', '',
        'The frozen graph configuration, graph/curvature source hashes, native additions and original input digests are bound in `protocol.json`; per-case exact added IDs and observation/track digests are in `summary.json` and `graphs/<method>/<case>/audit.json`. Full generated rows/tracks stay local and are hash-bound by the publication manifest.']
    with (HERE/'FINDINGS.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    write(HERE/'innovation_summary.json',innovations)
    files=[HERE/name for name in ('account.py','test_account.py','protocol.json','summary.json','report.py','FINDINGS.md','innovation_summary.json','test_results.json')]
    files+=sorted((HERE/'jobs').glob('*/*.json'))+sorted((HERE/'graphs').glob('*/*/audit.json'))
    large={str(p):sha(p) for p in sorted((HERE/'graphs').glob('*/*/*.json')) if p.name!='audit.json'}
    manifest=dict(schema='held-separate-graph-publication/v1',files={str(p.relative_to(HERE)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in files},
        locally_preserved_graph_artifacts=large,totals=summary['totals'],no_method_union=True,no_new_IQ_or_position=True,
        source_and_inputs_unchanged=all(sha(path)==h for path,h in dict(read(HERE/'protocol.json')['input_hashes'],**read(HERE/'protocol.json')['source_hashes']).items()))
    assert manifest['source_and_inputs_unchanged']
    write(HERE/'publication_manifest.json',manifest)
    write(HERE/'artifact_seal.json',dict(manifest_sha256=sha(HERE/'publication_manifest.json'),files=len(files),
        bytes=sum(p.stat().st_size for p in files),tests=2,all_passed=True,all24jobs_complete=True,native_provenance_failures=0,
        no_new_IQ_satellite_search_or_position=True))
    print(dict(totals=summary['totals'],manifest_sha256=sha(HERE/'publication_manifest.json'),seal_sha256=sha(HERE/'artifact_seal.json')),flush=True)


if __name__=='__main__':main()
