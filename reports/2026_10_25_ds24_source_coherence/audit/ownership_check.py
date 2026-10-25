"""Artifact-only native/gauge and historical-duration checks, no RF scores."""
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OWN = ROOT / 'ownership'
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024/DS24-0013')
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    checks = []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    protocol = read(OWN / 'protocol02.json')
    bindings = dict(protocol['files'])
    for name, digest in read(OWN / 'seal.json')['files'].items():
        bindings[str(OWN / name)] = digest
    bindings.update(read(OWN / 'overlay_protocol.json')['files'])
    check('frozen ownership, exported-contract and overlay bytes exact', all(sha(p) == h for p, h in bindings.items()))
    native = {row['observation_id']: row for row in read(SOURCE / 'observations.json')}
    tracks = {row['key']: row for row in read(SOURCE / 'tracks.json')}
    rows = list(csv.DictReader((OWN / 'native_winners.csv').open()))
    check('every reported native winner exactly matches original observation', len(native) == 4808 and all(
        r['winner_native_id'] in native and float(r['time_s']) == native[r['winner_native_id']]['time_s'] and
        float(r['native_CFO_Hz']) == native[r['winner_native_id']]['measured_cfo_hz'] and
        int(r['channel']) == native[r['winner_native_id']]['channel'] and
        abs(float(r['graph_gauge_CFO_Hz']) - float(r['native_CFO_Hz']) + 2 / 4.4e-6) < 1e-7 for r in rows))
    summary = read(OWN / 'results.json')
    for result in summary['rows']:
        selected = tracks[result['selected_component']]
        local = [r for r in rows if int(r['channel']) == result['channel']]
        check('complete-source IDs and local counts remain exact: CH' + str(result['channel']),
              selected['observation_ids'] == result['complete_native_IDs'] and
              len(local) == result['local_native_winners'] and len(selected['observation_ids']) == result['whole_source_points'] and
              sum(r['selected_source'] == 'True' for r in local) == result['local_selected_source_points'])
    ch4 = tracks['DS24-0013-RX2-CH4-T000-RF11690312500.000000']
    times = np.asarray(ch4['times'])
    eligibility = read(ROOT / 'eligibility/summary.json')
    for row in eligibility['proposed_metadata_cuts']:
        cut = row['cut_after_count']
        prefix, suffix = float(times[cut - 1] - times[0]), float(times[-1] - times[cut])
        check('original duration predicate replay: cut' + str(cut),
              prefix == row['prefix_duration_s'] and suffix == row['suffix_duration_s'] and
              (prefix >= 20) == row['prefix_passes_old_duration'] and (suffix >= 20) == row['suffix_passes_old_duration'])
    check('witness already structure-flagged; midpoint prefix is historically ineligible',
          ch4['quality_status'] == 'structure_flagged' and
          ch4['diagnostics']['pieces'][0]['adjacent_residual_correlation'] == .823467627881679 and
          not next(q for q in eligibility['proposed_metadata_cuts'] if q['cut_after_count'] == 21)['prefix_passes_old_duration'])
    local_ch4 = [r for r in rows if int(r['channel']) == 4]
    other = [r for r in local_ch4 if r['original_graph_owner'] != ch4['key']]
    check('all43 original witness IDs remain oneowner; other localowner starts later',
          sum(r['original_graph_owner'] == ch4['key'] for r in local_ch4) == 43 and
          len(other) == 6 and min(float(r['time_s']) for r in other) > 266.)
    extra = [r for r in rows if int(r['channel']) == 3 and not r['original_graph_owner']]
    check('CH3 gap winner retained as unassigned, not a new owner',
          any(abs(float(r['time_s']) - 238.921705) < 1e-6 and r['winner_native_id'] in native for r in extra))
    receipt = dict(all_passed=all(c['passed'] for c in checks), checks=checks,
        seconds=time.monotonic() - began, source_sha256=sha(__file__),
        source_protocol_sha256=sha(OWN / 'protocol02.json'), source_seal_sha256=sha(OWN / 'seal.json'),
        propagation_calls=0, position_fits=0, new_RF_scores=0, geographic_truth_read=False,
        scope='Original peak alternatives are same-probe hypotheses, not additional independent measurements. No graph switch or physical identity is established by this metadata trace.')
    with (HERE / 'ownership_check.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(path=str(HERE / 'ownership_check.json'), all_passed=receipt['all_passed'], seconds=receipt['seconds'], failed=[c for c in checks if not c['passed']])))


if __name__ == '__main__':
    main()
