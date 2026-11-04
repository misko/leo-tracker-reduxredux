"""Prepare standalone localization inputs through the read-only TLE archive port.

The initial policy keeps the original 48-hour archive window and newest/previous
element rules. Later recovery policies must request their own catalogue views.
No historical ALGO result, concrete storage path or evaluation position is read.
"""
import hashlib

from sgp4.api import Satrec
from sgp4.exporter import export_tle

from leo.analysis.localization_v3.orbits import regional_bank
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.sky.propagation import parse_element_sets


def validate_elements(record, cutoff):
    provenance = record['provenance']
    for key in ('element_epoch_utc_ns', 'collected_utc_ns'):
        if (key not in provenance or not isinstance(provenance[key], int)
                or provenance[key] > cutoff):
            raise ValueError(f'missing or noncausal TLE {key}')
    satellite = Satrec.twoline2rv(*record['lines'])
    epoch = int(round((satellite.jdsatepoch - 2440587.5) * 86400e9
                      + satellite.jdsatepochF * 86400e9))
    if epoch > cutoff:
        raise ValueError('TLE bytes have a future element epoch')
    if abs(epoch - provenance['element_epoch_utc_ns']) > 100000:
        raise ValueError('TLE bytes disagree with epoch provenance')


def genuine_previous(reader, snapshots, elements, cutoff, *, element_parser=parse_element_sets):
    """Preserve the production prior repair: updates must differ by >= 1 second."""
    unique = {}
    for snapshot in snapshots:
        if (snapshot.sha256 not in unique
                or snapshot.collected_utc_ns > unique[snapshot.sha256].collected_utc_ns):
            unique[snapshot.sha256] = snapshot
    previous, rejected = {}, set()
    for snapshot in unique.values():
        cat = element_parser(reader.read(snapshot))
        for name, number, satellite, epoch in zip(
                cat.names, cat.satellite_numbers, cat.satellites,
                cat.element_epoch_utc_ns(), strict=True):
            if str(number) not in elements or epoch > cutoff:
                continue
            latest = elements[str(number)]['provenance']['element_epoch_utc_ns']
            if latest - epoch < 1_000_000_000:
                if epoch < latest:
                    rejected.add(number)
                continue
            key = int(epoch), snapshot.collected_utc_ns
            if number not in previous or key > previous[number][0]:
                previous[number] = key, name, satellite, snapshot
    text, provenance = '', {}
    for number, (key, name, satellite, snapshot) in sorted(previous.items()):
        lines = export_tle(satellite)
        text += f'0 {name}\n{lines[0]}\n{lines[1]}\n'
        provenance[str(number)] = dict(epoch_utc_ns=key[0], collected_utc_ns=key[1],
                                       snapshot_digest=snapshot.digest)
    return dict(text=text, receipt=dict(sources=provenance,
                catalogue_sha256=hashlib.sha256(text.encode()).hexdigest(),
                minimum_epoch_separation_s=1., rejected_near_duplicate_norads=sorted(rejected)))


def distinct_epochs(versions, minimum_gap_ns=1_000_000_000):
    """Keep first causal publication per genuine epoch, in ascending epoch order."""
    by_epoch = {}
    for row in sorted(versions, key=lambda r:r['collected_utc_ns']):
        by_epoch.setdefault(row['epoch'], row)
    kept = []
    for row in sorted(by_epoch.values(), key=lambda r:-r['epoch']):
        if not kept or kept[-1]['epoch']-row['epoch'] >= minimum_gap_ns:
            kept.append(row)
    return kept[::-1]


def prepare_phase_history(reader, elements, metadata, *, element_parser=parse_element_sets):
    cutoff = metadata['causal_cutoff_utc_ns']
    snapshots = [s for s in reader.list_snapshots('space-track')
                 if cutoff-72*3600*1_000_000_000 <= s.collected_utc_ns <= cutoff]
    unique = {}
    for snapshot in snapshots:
        if (snapshot.sha256 not in unique
                or snapshot.collected_utc_ns < unique[snapshot.sha256].collected_utc_ns):
            unique[snapshot.sha256] = snapshot
    history, sources = {number:[] for number in elements}, []
    for snapshot in sorted(unique.values()):
        cat = element_parser(reader.read(snapshot))
        sources.append(dict(collected_utc_ns=snapshot.collected_utc_ns, sha256=snapshot.sha256))
        for number, satellite, epoch in zip(cat.satellite_numbers, cat.satellites,
                                            cat.element_epoch_utc_ns(), strict=True):
            if str(number) not in elements or epoch > cutoff:
                continue
            history[str(number)].append(dict(lines=list(export_tle(satellite)), epoch=int(epoch),
                collected_utc_ns=snapshot.collected_utc_ns, snapshot_sha256=snapshot.sha256))
    history = {number:distinct_epochs(rows) for number, rows in history.items()}
    return dict(case='SCAN', origin_utc_ns=metadata['anchor_utc_ns'], cutoff_utc_ns=cutoff,
                past_versions=history, sources=sources, history_window_hours=72,
                candidates=len(elements), genuine_distinct_epochs=True,
                no_following_TLE_or_GPS=True, archive_access_is_read_only=True)


def prepare_initial_sky(reader, tracks, metadata, *, screen_latitude_deg, screen_longitude_deg,
                        element_parser=parse_element_sets):
    """Build initial orbit evidence directly from a scan and causal archive.

    Returns numerical arrays and textual element/provenance evidence. Persistence
    and its content hashes belong to the application adapter, not the analyzer.
    """
    cutoff, origin = metadata['causal_cutoff_utc_ns'], metadata['anchor_utc_ns']
    snapshots = [s for s in reader.list_snapshots('space-track')
                 if cutoff - 172800_000_000_000 <= s.collected_utc_ns <= cutoff]

    class Recent:
        def list_snapshots(self, provider):
            return tuple(snapshots)

        def read(self, snapshot):
            return reader.read(snapshot)

    causal = causal_catalogue(Recent(), cutoff, element_parser=element_parser)
    duration = max(300., max(float(t['times'][-1]) for t in tracks))
    regional = regional_bank(causal.catalogue, origin, duration,
                             screen_latitude_deg=screen_latitude_deg,
                             screen_longitude_deg=screen_longitude_deg)
    chosen, selected = regional['catalogue'], regional['source_indices']
    elements, latest_text = {}, ''
    for local, original in enumerate(selected):
        name, satellite = chosen.names[local], chosen.satellites[local]
        lines = export_tle(satellite)
        record = dict(lines=list(lines), provenance=causal.provenance[int(original)])
        validate_elements(record, cutoff)
        elements[str(chosen.satellite_numbers[local])] = record
        latest_text += f'0 {name}\n{lines[0]}\n{lines[1]}\n'
    lookup, old = set(chosen.satellite_numbers), {}
    for snapshot in snapshots:
        cat = element_parser(reader.read(snapshot))
        for name, number, satellite, epoch in zip(
                cat.names, cat.satellite_numbers, cat.satellites,
                cat.element_epoch_utc_ns(), strict=True):
            if (number not in lookup
                    or epoch >= elements[str(number)]['provenance']['element_epoch_utc_ns']
                    or epoch > cutoff):
                continue
            key = (int(epoch), snapshot.collected_utc_ns)
            if number not in old or key > old[number][0]:
                old[number] = key, name, satellite, snapshot
    text, provenance = '', {}
    for number, (key, name, satellite, snapshot) in sorted(old.items()):
        lines = export_tle(satellite)
        text += f'0 {name}\n{lines[0]}\n{lines[1]}\n'
        provenance[str(number)] = dict(epoch_utc_ns=key[0], collected_utc_ns=key[1],
                                       snapshot_digest=snapshot.digest)
    if not old:
        raise ValueError('no previous causal catalogue; cannot replay declared orbit priors')
    prior = genuine_previous(reader, snapshots, elements, cutoff, element_parser=element_parser)
    return dict(bank=regional['bank'], nominal_elements=elements, selected_tle=latest_text,
                previous_tle=text,
                genuine_previous_tle=prior['text'], genuine_previous_receipt=prior['receipt'],
                previous_receipt=dict(sources=provenance,
                                      catalogue_sha256=hashlib.sha256(text.encode()).hexdigest()),
                metadata=dict(origin_utc_ns=origin, cutoff_utc_ns=cutoff,
                              regional_center=[screen_latitude_deg, screen_longitude_deg],
                              candidate_count=len(chosen), snapshot_count=len(snapshots),
                              previous_count=len(old), reference_position_used=False))
