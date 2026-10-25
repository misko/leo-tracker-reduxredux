"""Freeze the direct-measurement protocol before outcome computation."""

from pathlib import Path
import datetime
import contrasts as c


def main():
    rows=sorted((r for r in c.read(c.LEDGER)['rows'] if r['eligible']),key=lambda r:(r['captured_utc_ns'],r['case']))
    cases=[v['case'] for v in rows]
    paths=[c.LEDGER,Path(__file__),c.HERE/'contrasts.py',c.HERE/'test_contrasts.py']
    for case in cases:
        paths.extend([c.SOURCE/'family_cavity/position'/(case+'.json')])
        paths.extend(c.SOURCE/case/n for n in ('tracks.json','observations.json','radio_noise.json','bank.npz'))
        paths.extend(c.SOURCE/'causal_prior'/case/n for n in ('receipt.json','previous_receipt.json'))
    protocol=dict(version='direct same-family receiver differential r01',frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        cases=cases,cohort='all24 usable existing DS24 fast, chronological; previously exposed development data',
        selection='same original curved accepted family/IDs in both c arms; exact RF AND channel match; no new nomination',
        pairing='RX1 native anchor times bracketed by RX2 native points; no extrapolation; max bracket2s;>=4points per track-pair; lexicographic track order, unique physical RX1 anchors',
        data='alias-lifted measured CFO, normalized to11.5GHz; no fitted residual, phase, position, Gamma or geographic reference',
        cancellation='common fractional Doppler cancels only conditional on same emitter/frequency path; unrelated nonlinear path/transmitter terms remain possible',
        nuisances='per track-pair constant+linear, removed in orthonormal whitened null basis; actual rank retained',
        noise='original all-RF per-ID nominal sigma times sqrt2 unseenGamma moment; exact interpolation matrix covariance including reused endpoints; no held noise fitting',
        interpolation_sensitivity='add squared nominal Doppler curvature interpolation envelope to diagonal; max second derivative over full saved time grid and nine fixed25km-box positions, spherical6371km receiver; not phase/orbit/identity uncertainty bound',
        model='31 Gaussian centers0..300s every10s, width5s,50Hz coefficient SD at11.5GHz; no hyperparameter search',
        prediction='leave one whole paired family out within each scan; all other paired families train posterior; at least two families or explicit unsupported',
        controls=['reverse training differential polarity only','orthogonal75s circular coefficient rotation,31coefficients/310speriod; norm and training autocovariance preserved','untrained prior-only covariance'],
        metrics='full rank-aware held Gaussian loss, quadratic+logvolume, standardized mean squared error and projected native-time differential RMS; time coverage within5s',
        inference_scope='relative RX1-RX2 nonlinear contrast only; no absolute receiver attribution or position precision claim',
        existing_selection_leakage='labels,masks,aliases and noise inherited from fullRF; family holdout is conditional, not untouched identity validation',
        numerical_workers=1,maximum_workers=2,BLAS_threads=1,analysis_execution_cap_seconds=1200,
        no_position_fits=True,no_new_RF_or_IQ=True,no_GPS_for_selection=True,file_sha256={str(p):c.sha(p) for p in paths})
    c.write(c.HERE/'protocol.json',protocol)
    print('frozen',len(cases),'cases',len(paths),'files',c.sha(c.HERE/'protocol.json'))


if __name__=='__main__':
    main()
