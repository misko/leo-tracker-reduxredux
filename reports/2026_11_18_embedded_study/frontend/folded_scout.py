"""Blind two-lag epoch proposals and a bounded symbol FFT on archived dual-RX DS9 IQ."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


ROOT = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_30_native_adaptive_deployment/ds9")
PORTABLE = ROOT / "portable80"
RATE = 2_500_000
PERIOD = 1/4.4e-6
CELLS = round(RATE/750)
FRAME_STARTS = np.rint(np.arange(15)*RATE/750).astype(int)
FOLDS = FRAME_STARTS[:14,None] + np.arange(CELLS)[None,:]
TAPS = np.arange(2,66)[:,None]*11 + np.arange(11)
NFFT = 256


def scout(x, template, tune_aliases):
    scores = np.zeros(CELLS)
    for lag in (1,5):
        feature = (x[FOLDS+lag]*x[FOLDS].conj()).mean(axis=0)
        rf = np.roll(template,-lag)*template.conj()
        a = np.fft.fft(feature-feature.mean())
        b = np.fft.fft(rf-rf.mean())
        corr = np.fft.ifft(a*b.conj())
        scores += abs(corr) / (np.linalg.norm(feature-feature.mean())*np.linalg.norm(rf-rf.mean()))
    epochs = []
    for _ in range(4):
        peak = int(np.argmax(scores))
        epochs.append(peak)
        scores[(np.arange(-5,6)+peak)%CELLS] = -np.inf
    estimates = []
    symbols = template[TAPS]
    tuning = np.arange(-2,3) if tune_aliases else np.array([0])
    taps = np.exp(-2j*np.pi*np.outer(tuning, np.arange(11))/11)
    for epoch in epochs:
        choice = None
        for shift in range(-2,3):
            phase = (epoch+shift)%CELLS
            indices = FRAME_STARTS[:14,None,None] + phase + TAPS[None,:,:]
            samples = x[indices]
            z = np.einsum("fsj,sj,aj->afs",samples,symbols.conj(),taps,optimize=True)
            powers = np.mean(abs(np.fft.fft(z,NFFT,axis=2))**2,axis=1)
            alias, peak = np.unravel_index(np.argmax(powers),powers.shape)
            before, center, after = powers[alias,[(peak-1)%NFFT,peak,(peak+1)%NFFT]]
            sub = 0.5*(before-after)/(before-2*center+after) if center>max(before,after) else 0.
            hz = (((peak+sub)/NFFT+0.5)%1. -0.5)*PERIOD
            score = center / (np.mean(np.sum(abs(samples)**2,axis=(1,2)))*np.sum(abs(symbols)**2))
            if choice is None or score>choice[0]:
                choice = (float(score),int(phase),float(hz))
        estimates.append(choice)
    return sorted(estimates,reverse=True)


def frequency_match(observed, ref_hz):
    return abs((observed-ref_hz+PERIOD/2)%PERIOD-PERIOD/2)<=8000


def phase_match(observed, ref_samples):
    return abs((observed-ref_samples+CELLS/2)%CELLS-CELLS/2)<=4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-five-aliases",action="store_true")
    args = parser.parse_args()
    oracle = json.loads((ROOT/"deployed-fractional-oracle.json").read_text())
    ref = {(v["session_id"],v["visit_index"],v["probe"]["receiver_id"]): v["probe"] for v in oracle["rows"]}
    totals = Counter()
    rows = []
    for schedule in sorted((PORTABLE/"deployed-wrapper-schedules").glob("*.tsv")):
        for line in schedule.read_text().splitlines():
            parts = line.split("\t")
            meta = json.loads(parts[-1])
            tpl = np.fromfile(PORTABLE/"fixtures"/Path(parts[4]).name,np.complex128)
            payload = (PORTABLE/"fixtures"/Path(parts[6]).name).read_bytes()
            assert sha256(payload).hexdigest()==meta["raw_sha256"]
            raw = np.frombuffer(payload,"<i2").reshape(-1,2,2)[:50_000]
            session = meta["session_id"]
            visit = meta["visit_index"]
            for rx in (0,1):
                x = raw[:,rx,0].astype(np.float64) + 1j*raw[:,rx,1]
                answers = scout(x,tpl,args.test_five_aliases)
                candidates = ref[session,visit,rx]["candidates"]
                eligible = [v for v in candidates if v["passed_fractional_margin_gate"]]
                totals["probes"] += 1
                if eligible:
                    winner = max(eligible,key=lambda c:(c["fractional_margin"],-c["candidate_rank"]))
                    epoch = winner["integer_epoch_sample"]+winner["fractional_epoch_offset_samples"]
                    hz = winner["fractional_tracking_cfo_hz"]
                    a = [phase_match(e,epoch) for s,e,f in answers]
                    b = [p and frequency_match(f,hz) for p,(s,e,f) in zip(a,answers)]
                    null = [phase_match(e+CELLS/3,epoch) and frequency_match(f+PERIOD/3,hz) for s,e,f in answers]
                    totals.update(reference_positive=1,top4_phase=any(a),top4_joint=any(b),
                                  top1_joint=b[0],shifted_joint=any(null))
                else:
                    totals["reference_empty"] += 1
                rows.append(dict(session=session,visit=visit,rx=rx,sha256=meta["raw_sha256"],
                       estimates=answers,reference_positive=bool(eligible)))
    doc = dict(data="DS9 archived portable80",rate_hz=RATE,frames=14,symbols=64,epoch_peaks=4,
               timing_refinements=5,fft=NFFT,amplitude_aliases=5 if args.test_five_aliases else 1,
               epoch_tolerance_samples=4,cfo_tolerance_hz=8000,
               summary=totals,rows=rows)
    stem = "folded-scout-five-aliases" if args.test_five_aliases else "folded-scout"
    (Path(__file__).parent/(stem+".json")).write_text(json.dumps(doc,indent=2)+"\n")
    print(json.dumps(totals,indent=2))


if __name__ == "__main__":
    main()
