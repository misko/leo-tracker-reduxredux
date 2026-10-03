"""Conservative receiver/target-separated CFO associations, not satellite IDs."""

from collections import defaultdict

import numpy as np


def associate_partial_band_segments(probes):
    groups = defaultdict(list)
    for probe in probes:
        for candidate in probe.candidates:
            if candidate.passed:
                groups[(probe.channel, probe.edge, probe.receiver_id)].append((probe, candidate))
    output = []
    for key, rows in sorted(groups.items()):
        tracks = []
        for probe, candidate in sorted(rows, key=lambda pair: (pair[0].time_s, pair[1].rank)):
            plausible = []
            for i, track in enumerate(tracks):
                dt = probe.time_s - track[-1][0].time_s
                if not 0 < dt <= 1.5:
                    continue
                slope = 0.0
                if len(track) >= 3:
                    recent = track[-8:]
                    times = np.array([p.time_s for p, _ in recent])
                    values = np.array([c.cfo_hz for _, c in recent])
                    slope = float(np.polyfit(times - times[0], values, 1)[0])
                predicted = track[-1][1].cfo_hz + slope * dt
                residual = abs(candidate.cfo_hz - predicted)
                if abs(slope) <= 6000 and residual <= 300 + 1000 * dt:
                    plausible.append((residual, i))
            # Ambiguous joins remain new hypotheses; do not force association.
            if len(plausible) == 1:
                tracks[plausible[0][1]].append((probe, candidate))
            else:
                tracks.append([(probe, candidate)])
        for track in tracks:
            if len(track) < 4 or track[-1][0].time_s - track[0][0].time_s < 0.06:
                continue
            t = np.array([p.time_s for p, _ in track])
            f = np.array([c.cfo_hz for _, c in track])
            line = np.polyfit(t - t[0], f, 1)
            output.append(
                dict(
                    channel=key[0],
                    edge=key[1],
                    receiver_id=key[2],
                    start_time_s=float(t[0]),
                    end_time_s=float(t[-1]),
                    slope_hz_s=float(line[0]),
                    cfo_at_start_hz=float(line[1]),
                    rms_hz=float(np.sqrt(np.mean((f - np.polyval(line, t - t[0])) ** 2))),
                    observations=[
                        dict(
                            visit_index=p.visit_index,
                            probe_index=p.probe_index,
                            candidate_rank=c.rank,
                            time_s=p.time_s,
                            cfo_hz=c.cfo_hz,
                        )
                        for p, c in track
                    ],
                    candidate_only=True,
                )
            )
    return output
