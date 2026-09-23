"""Matched physical-bandwidth pilot replay on two frozen high-rate visits."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import resample_poly

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S, OFDM_SYMBOL_DURATION_S, edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from leo.scanner.adaptive_hop_analysis import Feature103VisitAnalysisV3, Feature104VisitAnalysisV4
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/figures/2026_09_23_matched_bandwidth_phase/v3"
SEED = 20260923
TARGET_RATE = 2_500_000
GROUP_MS = 20
GUARD_MS = .25
CASES = (("scan-fw-9b88653c7a012fc2", 760, Feature103VisitAnalysisV3),
         ("scan-fw-894676bdae3d7b2c", 475, Feature104VisitAnalysisV4))


def split_groups(count: int, seed: int = SEED) -> tuple[list[int], list[int]]:
    train = sorted(random.Random(seed).sample(range(count), count // 2))
    return train, sorted(set(range(count)) - set(train))


def circular_affine(time_s: np.ndarray, phase: np.ndarray, train: np.ndarray) -> tuple[float, float]:
    # The complex cross-vector phase is 2π periodic.  At 20-ms centers slopes
    # separated by 50 Hz are equivalent; retain the principal representative.
    grid = np.linspace(-25., 25., 801)
    score = []
    for hz in grid:
        z = np.exp(1j * (phase[train] - 2 * np.pi * hz * time_s[train]))
        score.append(abs(np.mean(z)))
    hz = float(grid[int(np.argmax(score))])
    intercept = float(np.angle(np.mean(np.exp(1j * (phase[train] - 2*np.pi*hz*time_s[train])))))
    return intercept, hz


def wrapped_phase_error(phase: np.ndarray, prediction: np.ndarray) -> np.ndarray:
    """The known complex pilot-vector cross phase has its ordinary 2π gauge."""
    return np.angle(np.exp(1j * (phase - prediction)))


def _design(times: np.ndarray, fs: float, epoch: int, cfo: float, edge: str, roll: int) -> np.ndarray:
    out = np.zeros((len(times), 8), complex)
    states = qin_edge_pilot_symbols(edge, symbol_roll=roll)
    freqs = edge_frequencies_hz(edge)
    frame = round(fs / 750.)
    # Cover all possibly intersecting rounded frame starts, evaluating at actual high-rate time.
    low = int(np.floor((times.min() - epoch) / frame)) - 2
    high = int(np.ceil((times.max() - epoch) / frame)) + 2
    for k in range(low, high + 1):
        start = epoch + round(k * fs / 750.)
        local = (times - start) / fs
        sym = np.floor(local / OFDM_SYMBOL_DURATION_S).astype(int)
        use = (sym >= 2) & (sym < 302)
        if not np.any(use):
            continue
        offset = local[use] - sym[use] * OFDM_SYMBOL_DURATION_S - CYCLIC_PREFIX_DURATION_S
        out[use] = (states[sym[use] - 2] * np.exp(2j*np.pi*freqs[None,:]*offset[:,None])
                    * np.exp(2j*np.pi*cfo*times[use,None]/fs) / np.sqrt(8))
    return out


def coefficients(values: np.ndarray, times_high: np.ndarray, fs_high: int, epoch: int, cfo: float, edge: str, roll: int = 0):
    x = _design(times_high, fs_high, epoch, cfo, edge, roll)
    good = np.any(x != 0, axis=1)
    if np.count_nonzero(good) < 80:
        return np.full(8, np.nan + 1j*np.nan), 0., np.count_nonzero(good)
    a, *_ = np.linalg.lstsq(x[good], values[good], rcond=None)
    coh = float(np.linalg.norm(x[good] @ a) / max(np.linalg.norm(values[good]), np.finfo(float).tiny))
    return a, coh, int(np.count_nonzero(good))


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    rows, binding = [], {"seed": SEED, "protocol": hashlib.sha256((ROOT / "reports/2026_09_23_matched_bandwidth_phase_protocol.md").read_bytes()).hexdigest(), "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), ROOT / "src/leo/analysis/starlink/templates.py")}, "target_rate_hz": TARGET_RATE, "pilot_relative_span_hz": 1_640_625.0, "guard_ms": GUARD_MS}
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        for session, visit_index, model in CASES:
            path = ROOT / "reports/figures/2026_09_23_phase_multirate" / session / "comparison.json"
            comparison = json.loads(path.read_text())
            row = next(x for x in comparison["visits"] if x["visit"] == visit_index)
            visit = model.model_validate(row["dense_glrt"])
            fs = visit.configuration.sample_rate_hz
            factor = fs // TARGET_RATE
            if factor * TARGET_RATE != fs:
                raise ValueError("expected integer 2.5 MS/s factor")
            edge = visit.target.edge
            candidates = []
            for rx in (0, 1):
                probe = next(p for p in visit.probes if p.receiver_id == rx and p.probe_index == 0)
                candidate = next(c for c in probe.candidates if c.candidate_rank == 0)
                candidates.append((candidate.integer_epoch_sample, candidate.acquired_cfo_hz))
            train, held = split_groups(6)
            with AdaptiveHopAnalysisInputStore(store).source(session) as source:
                ordinal = next(i for i,v in enumerate(source.visits) if v.event.visit_index == visit_index)
                iq = source.read_visit(ordinal)
                if hashlib.sha256(iq.tobytes()).hexdigest() != row["iq_sha256"]:
                    raise ValueError("IQ digest mismatch")
                binding[session] = {"comparison_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "iq_sha256": row["iq_sha256"], "input_manifest_sha256": source.input_manifest_sha256}
                group = fs * GROUP_MS // 1000
                guard = round(fs * GUARD_MS / 1000)
                for gid in range(6):
                    start, stop = gid*group, (gid+1)*group
                    raw = iq[start:stop].astype(np.complex128)
                    raw_times = np.arange(start, stop, dtype=float)
                    # Centre the prebound pilot before the 2.5-MS/s anti-alias
                    # filter.  This makes the retained eight-tone band identical
                    # in physical frequency for both arms.
                    centered = raw * np.exp(-2j*np.pi*raw_times[:,None]*np.array([c[1] for c in candidates])[None,:]/fs)
                    arms = {"full": (centered, raw_times)}
                    narrow = resample_poly(centered, up=1, down=factor, axis=0, window=("kaiser", 8.6), padtype="constant")
                    arms["narrow_2p5"] = (narrow, start + np.arange(len(narrow), dtype=float)*factor)
                    item = {"session_id":session, "visit":visit_index, "sample_rate_hz":fs, "group_id":gid, "partition":"train" if gid in train else "held", "time_s":(gid+.5)*GROUP_MS/1000, "arms":{}}
                    for name,(values,times) in arms.items():
                        keep = (times >= start+guard) & (times < stop-guard)
                        values, times = values[keep], times[keep]
                        a0,c0,n0 = coefficients(values[:,0], times, fs, candidates[0][0], 0., edge)
                        a1,c1,n1 = coefficients(values[:,1], times, fs, candidates[1][0], 0., edge)
                        q0,ctrl0,_ = coefficients(values[:,0], times, fs, candidates[0][0], 0., edge, roll=17)
                        q1,ctrl1,_ = coefficients(values[:,1], times, fs, candidates[1][0], 0., edge, roll=17)
                        cross = np.vdot(a0, a1)
                        # Unmodelled broad-band RX coherence after the frozen per-RX NCOs.
                        b = np.vdot(values[:,0], values[:,1])
                        denom = np.linalg.norm(values[:,0])*np.linalg.norm(values[:,1])
                        item["arms"][name] = {"pilot_phase_rad":float(np.angle(cross)), "pilot_vector_coherence":float(abs(cross)/(np.linalg.norm(a0)*np.linalg.norm(a1))), "exact_projection_rx0":c0, "exact_projection_rx1":c1, "rolled_projection_rx0":ctrl0, "rolled_projection_rx1":ctrl1, "usable_samples":min(n0,n1), "broadband_cross_coherence":float(abs(b)/max(denom,np.finfo(float).tiny)), "broadband_cross_phase_rad":float(np.angle(b))}
                    rows.append(item)
    finally:
        store.close()
    summaries=[]
    fig, axes = plt.subplots(2, 1, figsize=(9,6), sharex=True, layout="constrained")
    for ax,(session,visit,_model) in zip(axes, CASES, strict=True):
        case=[r for r in rows if r['session_id']==session]
        summary={"session_id":session,"visit":visit,"groups":{"train":split_groups(6)[0],"held":split_groups(6)[1]},"arms":{}}
        for arm,color in (("full","tab:blue"),("narrow_2p5","tab:orange")):
            t=np.array([r['time_s'] for r in case]); p=np.array([r['arms'][arm]['pilot_phase_rad'] for r in case]); train=np.array([r['partition']=='train' for r in case]); held=~train
            intercept,hz=circular_affine(t,p,train)
            err=wrapped_phase_error(p, intercept+2*np.pi*hz*t)
            summary['arms'][arm]={"train_phase_resultant":float(abs(np.mean(np.exp(1j*err[train])))),"held_phase_resultant":float(abs(np.mean(np.exp(1j*err[held])))),"held_phase_rms_rad":float(np.sqrt(np.mean(err[held]**2))),"training_only_slope_hz":hz,"median_exact_projection_rx0":float(np.median([r['arms'][arm]['exact_projection_rx0'] for r in case])),"median_exact_projection_rx1":float(np.median([r['arms'][arm]['exact_projection_rx1'] for r in case])),"median_broadband_cross_coherence":float(np.median([r['arms'][arm]['broadband_cross_coherence'] for r in case]))}
            ax.plot(t[train]*1e3, p[train], 'o', color=color, label=f'{arm} train')
            ax.plot(t[held]*1e3, p[held], 'x', color=color, label=f'{arm} held')
        ax.set_title(f'{session} visit {visit}: raw pilot-vector RX phase')
        ax.set_ylabel('wrapped phase [rad]'); ax.legend(ncol=2, fontsize=8)
        summaries.append(summary)
    axes[-1].set_xlabel('physical group center [ms]')
    fig.savefig(OUT/'phase-v-time-full-vs-narrow.png', dpi=160)
    (OUT/'results.json').write_text(json.dumps({"binding":binding,"rows":rows,"summaries":summaries},indent=2)+"\n")


if __name__ == '__main__':
    run()
