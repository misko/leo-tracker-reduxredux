"""Show original-track conflicts exposed by precise simultaneous evidence."""

import numpy as np

import probe_ds23_joint_probe_position as joint
import probe_ds23_shared_probe_position as previous
from probe_ds23_frequency_events import cached
from run_algo01_ds23_sample import read, write, sha


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    choices = [('DS23-0186', 'DS23-0186-RX1-CH2-T006-RF10959687500.000000', 'Existing predictive track, same family 68714'),
               ('DS23-0289', 'DS23-0289-RX1-CH1-T005-RF10940312500.000000', 'Original curved track, different family 62993'),
               ('DS23-0337', 'DS23-0337-RX1-CH7-T001-RF12440312500.000000', 'Original curved track, different family 69172')]
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), constrained_layout=True)
    evidence = []
    for (case, component, title), row in zip(choices, axes, strict=True):
        source = joint.configure(case); d = previous.prepare_inputs(case)
        old = read(source/(case+'.json'))['refined_control']['arms']['fitted_c']
        saved = read(joint.OUT/(case+'.json'))
        record = saved['results']['joint_shared_curved']['arms']['fitted_c']
        p = joint.make(d, 'fitted_c', np.array(record['phase_reference']), saved['extra_entries'], True)
        x = np.asarray(record['endpoint_east_north_km']); c = p.calculate(x)
        base = previous.make(d['changed'], d['node'], d['mask'], 'fitted_c', np.asarray(old['phase_reference']),
                             d['powers'], d['means'], d['hyper'], d['original_entries'], {}, d['covariance'], False)
        before = base.calculate(old['endpoint_east_north_km'])
        if component in [r['component'] for r in p.rows]:
            k = next(k for k, r in enumerate(p.rows) if r['component'] == component)
            sl = p.slices[k]; index = p.members[k]; active = d['mask'][sl]
            track = p.scan.tracks[index]; times = track['times'][active]
            first = before['conditional_residual_hz'][sl][active]
            second = c['conditional_residual_hz'][sl][active]
        else:
            k = next(k for k, r in enumerate(p.linear_entries) if r['component'] == component)
            sl = p.linear_slices[k]; index = p.linear_entries[k]['track_index']
            track = p.scan.tracks[index]; times = track['times']
            first = before['linear_raw_prediction_residual_hz'][sl]
            second = c['linear_raw_prediction_residual_hz'][sl]
            first, second = first-first.mean(), second-second.mean()
        row[0].plot(times, first, '.-', lw=.8, label='Original calibration on refined CFO data')
        row[0].plot(times, second, '.-', lw=.8, label='Joint conditional calibration')
        row[0].set(title=case+' · '+title, xlabel='Scan time (s)', ylabel='Original track residual (Hz)')
        row[0].axhline(0, color='k', lw=.5); row[0].legend(fontsize=7)
        new = []
        for entry, sl in zip(p.joint_secondary_entries, p.joint_secondary_slices, strict=True):
            t = p.scan.tracks[entry['track_index']]['times']
            residual = c['joint_secondary_fitted_residual_hz'][sl]
            row[1].plot(t, residual, '.-', lw=.8, label=str(entry['norad']))
            new.append(dict(norad=entry['norad'], time_s=t, conditional_residual_hz=residual))
        row[1].set(title='New curved components fit closely; whole-scan gate still rejects', xlabel='Scan time (s)', ylabel='Conditional secondary residual (Hz)')
        row[1].axhline(0, color='k', lw=.5); row[1].legend(fontsize=7, title='Family')
        for a in row:
            a.grid(alpha=.2)
        evidence.append(dict(case=case, component=component, original_time_s=times, refined_control_residual_hz=first,
                             joint_residual_hz=second, new_secondary=new,
                             original_trial_sha256=sha(joint.OUT/(case+'.json'))))
    fig.suptitle('New precise evidence can fit while exposing a conflict in other retained observations\nOriginal gates unchanged; all three joint proposals rejected in both c arms')
    fig.savefig(joint.OUT/'retained_track_conflicts.png', dpi=160); plt.close(fig)
    write(joint.OUT/'retained_track_conflicts.json', dict(rows=evidence, no_GPS_used=True,
         no_original_point_or_gate_removed=True, transmitter_clock_timing_not_used_for_position=True))


if __name__ == '__main__':
    main()
