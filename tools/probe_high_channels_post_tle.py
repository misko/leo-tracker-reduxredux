"""Read-only later-TLE diagnostic; never replace the causal inference bank."""

import argparse
import copy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

import debug_fast_graph_unassociated as report
from probe_graph_shared_high_channels import context, select_targets
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets, ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).isoformat()


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    d = context(args); scan = d['scan']; targets = select_targets(d)
    archive = TleArchiveReader(args.archive)
    origin = scan.receipt['origin_utc_ns']
    snapshots = [s for s in archive.list_snapshots('space-track')
                 if origin + 300e9 < s.collected_utc_ns < origin + 48 * 3600e9]
    if not snapshots:
        raise ValueError('No post-observation Space-Track snapshots')
    original = {int(n): v['lines'] for n, v in scan.elements.items()}
    timeline, chosen = [], {}
    for snapshot in snapshots:
        records = {r.satellite_number: r for r in parse_element_set_records(archive.read(snapshot))
                   if r.satellite_number in original}
        changes = []
        for norad, record in records.items():
            epoch = int(parse_element_sets(record.text).element_epoch_utc_ns()[0])
            lines = [line for line in record.text.splitlines() if line.startswith(('1 ', '2 '))]
            chosen[norad] = dict(lines=lines, epoch_utc_ns=epoch,
                                  collected_utc_ns=snapshot.collected_utc_ns,
                                  digest=snapshot.digest, epoch_utc=utc(epoch))
            if lines != original[norad]: changes.append(norad)
        timeline.append(dict(collected_utc=utc(snapshot.collected_utc_ns),
            digest=snapshot.digest, changed_elements=len(changes),
            targets={str(n): chosen.get(n) for n in (57701, 58101)}))
    selected = [chosen.get(int(n), dict(lines=original[int(n)])) for n in scan.norads]
    catalogue = ElementSetCatalogue(tuple(map(str, scan.norads)), tuple(map(int, scan.norads)),
        tuple(Satrec.twoline2rv(*v['lines']) for v in selected))
    position, velocity, usable = ecef_states(catalogue, origin, scan.sky['time_s'])
    if not usable.all(): raise ValueError('Post-observation propagation failure')
    bank = dict(time_s=scan.sky['time_s'], position_km=position, velocity_km_s=velocity)
    receipt = dict(observation_utc=utc(origin), timeline=timeline,
        selected_by='latest available archive collection within 48 hours, not RF score',
        changed_elements=sum(chosen[int(n)]['lines'] != original[int(n)] for n in scan.norads if int(n) in chosen),
        missing=[int(n) for n in scan.norads if int(n) not in chosen],
        candidate_count=len(scan.norads), offline_noncausal=True,
        original_target_elements={str(n): scan.elements[str(n)] for n in (57701,58101)},
        selected=chosen, calibration_and_position_frozen=True)
    report.write(args.output/'archive_audit.json', receipt)
    print('Archive', len(snapshots), 'snapshots;', receipt['changed_elements'], 'changed elements', flush=True)
    for arm, (p, x) in d['problems'].items():
        for kind, sky in (('causal', scan.sky), ('post_observation', bank)):
            probe = copy.copy(p); probe.scan = copy.copy(scan); probe.scan.sky = sky
            results = []
            for k in targets:
                t = scan.tracks[p.members[k]]
                r = report.screen(probe, x, t, np.arange(len(t['times'])), full_catalogue=True)
                r['component'] = t['key']; results.append(r)
                print(arm,kind,t['key'],r['norad'],r['rms_hz'],r['passes_all'],flush=True)
            report.write(args.output/f'{arm}_{kind}.json',results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run','source-root','ch1','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--archive', type=Path, default=Path('/var/lib/leo/tle'))
    run(parser.parse_args())
