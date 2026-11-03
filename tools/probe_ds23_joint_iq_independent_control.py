"""Does common-clock target IQ beat an independently varying target transmitter?"""

from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

from audit_ds23_joint_receiver_iq import context
from ds23_common_receiver_clock import fit
from ds23_iq_gain_prediction import target_gain_density
from ds23_joint_component_rf import JointComponentWorkspace
from ds23_joint_gain_controls import frame_coefficients
from probe_ds23_joint_receiver_iq import OUT as RAW
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT/'reports/2026_10_21_ds23_common_clock_alias_refit/evaluation.json'
OUT = ROOT/'reports/2026_10_21_ds23_joint_iq_independent_control'


def one(row):
    samples, fs, edge, epochs, segments = context(row)
    previous = next(r for r in read(SOURCE)['rows'] if r['index'] == row['index'])
    times = np.array([ix.mean()/fs for ix in segments])
    records = []
    for fold in row['folds']:
        train = np.arange(len(segments)) % 2 == fold['parity']
        support = [ix for k, ix in enumerate(segments) if train[k]]
        previous_fold = next(f for f in previous['folds'] if f['parity'] == fold['parity'])
        for source in [0, 1]:
            rx = 1-source
            native = np.array(previous_fold['native_training_fits'][rx]['parameters'])
            ws = JointComponentWorkspace(samples[rx], fs, edge, epochs[rx], support)
            columns = ws.columns(native)
            coefficients, covariance = frame_coefficients(samples[rx], columns, support)
            model = fit(times[train], np.ones_like(coefficients), coefficients,
                covariance, covariance, np.zeros(2), mode='independent')
            p = np.asarray(model['parameters'])
            scale = np.asarray(model['second_scale'])
            ratio = p[:4:2]+1j*p[1:4:2]
            gain_covariance = np.diag(np.exp(p[-2:])*scale**2)
            sigma = fold['models']['common']['noise_variance_from_training_IQ_only'][rx]
            nll = 0.
            for k, ix in enumerate(segments):
                if train[k]:
                    continue
                mean = ratio*scale*np.exp(2j*np.pi*p[4:6]*(times[k]-model['time_center_s']))
                nll += target_gain_density(samples[rx, ix], columns[ix], mean, gain_covariance, sigma)
            common = fold['models']['common']['predictions'][source]['NLL']
            records.append(dict(parity=fold['parity'], source_receiver=source+1, target_receiver=rx+1,
                independent_gain_model=model, independent_target_raw_NLL=float(nll),
                common_target_raw_NLL=common, common_vs_independent_target_raw_gain=float(nll-common)))
    return dict(index=row['index'], case=row['case'], window_key=row['entry']['window_key'], cohort=row['cohort'],
        records=records, all_RX_folds_common_beats_independent=all(r['common_vs_independent_target_raw_gain'] > 0 for r in records),
        previous_common_vs_separate_candidate=row['conditional_raw_IQ_common_clock_candidate'])


def main():
    OUT.mkdir(exist_ok=True)
    source = read(RAW/'evaluation.json')
    protocol = dict(raw_source_sha256=sha(RAW/'evaluation.json'), native_source_sha256=sha(SOURCE), workers=6,
        source_tools={n:sha(ROOT/'tools'/n) for n in [__file__.split('/')[-1], 'ds23_iq_gain_prediction.py', 'ds23_common_receiver_clock.py']},
        baseline='independent target gain mean with frequency ramp and Gaussian discrepancy learned on training frames; held target IQ integrated, no fitted held gain',
        native_target_CFO_epoch_rate_fixed_from_training_RF_only=True,
        normalization_and_target_DC_subspace_match_raw_source_prediction=True,
        no_GPS_TLE_new_RF_or_position_used=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen independent-target RF comparator changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one, r) for r in source['rows']])]
    rows.sort(key=lambda r:r['index'])
    write(OUT/'evaluation.json', dict(rows=rows, all_terminal=True, protocol_sha256=sha(target),
        common_clock_candidates_also_beating_independent=[r['index'] for r in rows
            if r['previous_common_vs_separate_candidate'] and r['all_RX_folds_common_beats_independent']],
        no_absolute_frequency_accuracy_or_position_improvement_established=True))
    print([(r['index'],r['all_RX_folds_common_beats_independent'],
        min(q['common_vs_independent_target_raw_gain'] for q in r['records'])) for r in rows], flush=True)


if __name__ == '__main__':
    main()
