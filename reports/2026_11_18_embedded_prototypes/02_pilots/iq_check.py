"""Bounded DS26 waveform check of a folded scout and guided Qin pilot bank."""

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import time

import numpy as np
import zstandard

from run import (CASES, FREQUENCY_PERIOD, Gate, HERE, Hypothesis, INPUTS, Lane,
                 PHASE_PERIOD_US, Peak, native_probes, wrap)
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame


RECORDINGS = Path("/srv/bulk/leo/fast-scan-recordings")
RATE = 10_000_000
FRAME_SAMPLES = round(RATE / 750)
PROBE_SAMPLES = RATE // 50
MIB = 1024 * 1024
REVISIT_CASES = (0, 3, 7)
FFT_SIZE = 512
PROPOSALS = 8
REFINE_SAMPLES = 4
MARGIN = 0.10
TAPS = np.arange(2, 66)[:, None] * 44 + np.arange(44)
ALIASES = np.arange(-2, 3)
ALIAS_ROTATION = np.exp(-2j * np.pi * np.outer(ALIASES, np.arange(44)) / 44)
BINS_HZ = np.fft.fftfreq(FFT_SIZE) * FREQUENCY_PERIOD


def corpus_read(*args):
    return subprocess.run(("sudo", "-n", "-u", "leo", "--", *map(str, args)), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15).stdout


def archive_windows(case, indices, cap_mib):
    title = json.loads((INPUTS / case / "request.json").read_bytes())["title"]
    if re.fullmatch(r"fast8-auto-\d{8}-\d{6}-[0-9a-f]{8}-\d+-(lower|upper)", title) is None:
        raise ValueError("unexpected archive recording identity")
    root = RECORDINGS / title / (title + "-segment-00000000")
    manifest = json.loads(corpus_read("head", "-c", "16384", root / "manifest.json"))
    assert manifest["sample_format"] == "ci16_le" and manifest["sample_layout"] == "sample_receiver_iq"
    assert manifest["sample_rate_hz"] == RATE and manifest["receiver_ids"] == [0, 1]
    chunk = manifest["chunks"][0]
    assert chunk["first_sequence"] == 0
    for field in ("index_relative_path", "payload_relative_path"):
        assert Path(chunk[field]).name == chunk[field]
    raw_index = corpus_read("head", "-c", "65536", root / chunk["index_relative_path"])
    rows = [json.loads(line) for line in raw_index.splitlines()[:max(indices)+1]]
    compressed = corpus_read("dd", "if=" + str(root / chunk["payload_relative_path"]),
                             "bs=1M", f"count={cap_mib}", "status=none")
    assert 0 < len(compressed) <= cap_mib * MIB
    data = {}
    prefix = 0
    with zstandard.ZstdDecompressor().stream_reader(compressed) as stream:
        for seq, row in enumerate(rows):
            assert row["sequence"] == seq and row["payload_offset_bytes"] == prefix
            assert row["sample_count"] == PROBE_SAMPLES and row["receiver_count"] == 2
            raw = stream.read(row["payload_bytes"])
            prefix += len(raw)
            if len(raw) != row["payload_bytes"]:
                raise ValueError(f"compressed prefix ended in window {seq} under its fixed {cap_mib} MiB cap")
            if "sha256:" + sha256(raw).hexdigest() != row["iq_sha256"]:
                raise ValueError(f"window {seq} SHA-256 mismatch")
            if seq in indices:
                values = np.frombuffer(raw, dtype="<i2").reshape(PROBE_SAMPLES, 2, 2)
                x = values[:, 0, 0].astype(float) + 1j * values[:, 0, 1]
                data[seq] = (row, x)
    return data, len(compressed), prefix


def source_phase(counter):
    return ((counter * 750) % RATE) / RATE * PHASE_PERIOD_US


def phase_at(epoch, counter):
    return (source_phase(counter) + epoch * 1e6 / RATE) % PHASE_PERIOD_US


class PilotBank:
    """Shared two-lag FFT proposals and exact-versus-rolled 64-symbol pilot scores."""

    def __init__(self, edge):
        template = np.asarray(qin_edge_pilot_frame(RATE, edge), np.complex128)
        control = np.asarray(qin_edge_pilot_frame(RATE, edge, symbol_roll=CONTROL_SYMBOL_ROLL), np.complex128)
        self.reference = np.stack((template[TAPS], control[TAPS])).conj()
        self.lag_references = []
        for lag in (4, 20):
            feature = np.roll(template, -lag) * template.conj()
            feature -= feature.mean()
            self.lag_references.append((lag, np.fft.fft(feature).conj(), np.linalg.norm(feature)))

    def coarse(self, x):
        folds = np.rint(np.arange(math.floor(x.size * 750 / RATE) - 1) * RATE / 750).astype(int)
        folds = folds[:, None] + np.arange(FRAME_SAMPLES)[None, :]
        scores = np.zeros(FRAME_SAMPLES)
        for lag, template_fft, template_norm in self.lag_references:
            feature = (x[folds + lag] * x[folds].conj()).mean(axis=0)
            feature -= feature.mean()
            scale = np.linalg.norm(feature) * template_norm
            if scale > 0.:
                scores += np.abs(np.fft.ifft(np.fft.fft(feature) * template_fft)) / scale
        return scores

    def search(self, x, counter, gates=None):
        start = time.perf_counter()
        proposal = self.coarse(x)
        coarse = time.perf_counter()
        epoch_grid = np.arange(FRAME_SAMPLES)
        phases = phase_at(epoch_grid, counter)
        if gates is not None:
            possible = np.zeros(FRAME_SAMPLES, dtype=bool)
            for gate in gates:
                possible |= np.abs(wrap(phases - gate.phase_us, PHASE_PERIOD_US)) <= gate.half_us
            proposal[~possible] = -np.inf
        epochs = set()
        for _ in range(PROPOSALS):
            peak = int(proposal.argmax())
            if not np.isfinite(proposal[peak]):
                break
            epochs.update(int(ep) for ep in (peak + np.arange(-REFINE_SAMPLES, REFINE_SAMPLES+1)) % FRAME_SAMPLES)
            proposal[(peak + np.arange(-12, 13)) % FRAME_SAMPLES] = -np.inf

        frame_starts = np.rint(np.arange(15) * RATE / 750).astype(int)
        best = None
        cells = 0
        tested_epochs = 0
        for epoch in sorted(epochs):
            use = None
            if gates is not None:
                use = np.zeros(FFT_SIZE, dtype=bool)
                for gate in gates:
                    if abs(wrap(phases[epoch] - gate.phase_us, PHASE_PERIOD_US)) <= gate.half_us:
                        use |= np.abs(wrap(BINS_HZ - gate.frequency, FREQUENCY_PERIOD)) <= gate.half_hz
                if not use.any():
                    continue
            starts = frame_starts[frame_starts + epoch + TAPS[-1, -1] < x.size]
            if len(starts) < 2:
                continue
            samples = x[starts[:, None, None] + epoch + TAPS[None, :, :]]
            z = np.einsum("fst,kst,at->kafs", samples, self.reference, ALIAS_ROTATION, optimize=True)
            ceiling = np.sum(np.sum(abs(z), axis=-1)**2, axis=-1)
            if use is None:
                hz = BINS_HZ
                spectrum = np.fft.fft(z, n=FFT_SIZE, axis=-1)
            else:
                hz = BINS_HZ[use]
                steering = np.exp(-2j * np.pi * np.outer(np.arange(TAPS.shape[0]), hz) / FREQUENCY_PERIOD)
                spectrum = z @ steering
            power = np.sum(abs(spectrum)**2, axis=-2)
            norm = np.divide(power, ceiling[:, :, None], out=np.zeros_like(power), where=ceiling[:, :, None] > 0.)
            arg = np.argmax(norm[0], axis=-1)
            exact = norm[0, np.arange(ALIASES.size), arg]
            control = np.max(norm[1], axis=-1)
            margin = exact - control
            alias = int(np.argmax(margin))
            cells += 2 * ALIASES.size * hz.size
            tested_epochs += 1
            if best is None or margin[alias] > best["margin"]:
                best = dict(epoch_sample=epoch, phase_us=float(phases[epoch]), cfo_hz=float(hz[arg[alias]]),
                            alias_cfo_hz=float(hz[arg[alias]] + ALIASES[alias] * FREQUENCY_PERIOD),
                            exact=float(exact[alias]), control=float(control[alias]), margin=float(margin[alias]),
                            frames=len(starts), passed=bool(margin[alias] >= MARGIN))
        return dict(winner=best, tested_epochs=tested_epochs, scored_epoch_alias_cfo_cells=cells,
                    coarse_wall_ms=1000 * (coarse - start), total_wall_ms=1000 * (time.perf_counter() - start))


def signal_match(first, second):
    if first is None or second is None:
        return None
    dhz = abs(wrap(first["cfo_hz"] - second["cfo_hz"], FREQUENCY_PERIOD))
    dus = abs(wrap(first["phase_us"] - second["phase_us"], PHASE_PERIOD_US))
    return dict(abs_wrapped_cfo_hz=dhz, abs_wrapped_phase_us=dus, within_8khz_and_1p6us=dhz <= 8000 and dus <= 1.6)


def positive(result):
    return result is not None and result["winner"] is not None and result["winner"]["passed"]


def compare(blind, guided):
    return dict(blind_passed=bool(positive(blind)), guided_passed=bool(positive(guided)),
                agreement=signal_match(blind["winner"], guided["winner"]) if guided is not None else None)


def reference(data):
    if not data.peaks:
        return None
    p = data.peaks[0]
    return dict(cfo_hz=p.frequency, phase_us=p.phase_us, margin=p.margin)


def run_case(case, index, bank_by_edge):
    revisit = index in REVISIT_CASES
    indices, cap = ((0, 8), 14) if revisit else ((0, 1), 4)
    # The explicit cap below includes the compressed stream prefix needed to
    # reach the preselected raw windows, including unscored intermediate IQ.
    windows, compressed_bytes, prefix = archive_windows(case, indices, cap)
    native = json.loads((INPUTS / case / "native.json").read_bytes())
    zero = native["clock_anchor"]["sample_counter"]
    probes = {round((probe.time - .01) * RATE) + zero: probe for probe in native_probes(native) if probe.receiver == 1}
    results = []
    first_probe = None
    for sequence in indices:
        row, x = windows[sequence]
        start_count = row["acquisition"]["sample_start"]
        probe = probes[start_count]
        edge = row["target_id"].split("-")[1]
        detector = bank_by_edge[edge]
        counter = start_count - zero
        blind = detector.search(x, counter)
        saved = reference(probe)
        result = dict(sequence=sequence, receiver_id=0, channel=probe.channel, edge=edge,
                      valid_start_counter=start_count, iq_sha256=row["iq_sha256"],
                      blind=blind, archived_blind_winner=saved, raw_vs_archived=signal_match(blind["winner"], saved))
        if sequence == 0:
            first_probe = probe
            first = detector.search(x[:PROBE_SAMPLES//2], counter)
            second_counter = counter + PROBE_SAMPLES//2
            second_blind = detector.search(x[PROBE_SAMPLES//2:], second_counter)
            gate = None
            second_guided = None
            if positive(first):
                seed = first["winner"]
                gate = Hypothesis(0.005, Peak(0, seed["cfo_hz"], seed["phase_us"], seed["margin"])).predict(.015)
                second_guided = detector.search(x[PROBE_SAMPLES//2:], second_counter, (gate,))
            result["split_10ms"] = dict(first_blind=first, second_blind=second_blind, second_guided=second_guided,
                                       gate=asdict(gate) if gate is not None else None,
                                       comparison=compare(second_blind, second_guided))
        elif revisit:
            assert first_probe is not None and first_probe.lane == probe.lane and first_probe.time < probe.time
            lane = Lane()
            assert lane.observe(first_probe)[0] == "scout"
            gates = [hypothesis.predict(probe.time) for hypothesis in lane.hypotheses]
            guided = detector.search(x, counter, gates) if gates else None
            result["first_revisit"] = dict(seed="previous full archived native candidates",
                                          elapsed_s=probe.time - first_probe.time,
                                          gates=list(map(asdict, gates)), guided=guided,
                                          comparison=compare(blind, guided))
        results.append(result)
    return dict(case=case, status="checked", compressed_bytes_read=compressed_bytes,
                decompressed_prefix_bytes=prefix, windows=results)


def summary(results):
    tallies = Counter()
    matched_pairs = {"split": [], "revisit": []}
    for case in results:
        if case["status"] != "checked":
            continue
        for window in case["windows"]:
            tallies["raw_windows"] += 1
            tallies["raw_blind_positive"] += positive(window["blind"])
            tallies["archived_winner_present"] += window["archived_blind_winner"] is not None
            match = window["raw_vs_archived"]
            tallies["raw_blind_positive_and_matched_archived"] += bool(
                positive(window["blind"]) and match and match["within_8khz_and_1p6us"])
            if "split_10ms" in window:
                item = window["split_10ms"]
                matched_pairs["split"].append((item["second_blind"], item["second_guided"], item["comparison"]))
            if "first_revisit" in window:
                item = window["first_revisit"]
                matched_pairs["revisit"].append((window["blind"], item["guided"], item["comparison"]))
    pairs = {}
    for label, samples in matched_pairs.items():
        tested = [(blind, guided, cmp) for blind, guided, cmp in samples if guided is not None]
        pairs[label] = dict(preselected=len(samples), gates_available_and_tested=len(tested),
                            blind_positives_with_guided_test=sum(cmp["blind_passed"] for _, _, cmp in tested),
                            guided_positives=sum(cmp["guided_passed"] for _, _, cmp in tested),
                            both_positive_matching=sum(bool(cmp["blind_passed"] and cmp["guided_passed"] and
                                                            cmp["agreement"]["within_8khz_and_1p6us"])
                                                       for _, _, cmp in tested),
                            median_blind_wall_ms=statistics.median(blind["total_wall_ms"] for blind, _, _ in tested)
                            if tested else None,
                            median_guided_wall_ms=statistics.median(guided["total_wall_ms"] for _, guided, _ in tested)
                            if tested else None,
                            median_cell_fraction=statistics.median(guided["scored_epoch_alias_cfo_cells"] /
                                                                    blind["scored_epoch_alias_cfo_cells"]
                                                                    for blind, guided, _ in tested)
                            if tested else None)
    return dict(tallies, matched=pairs)


def check(bank):
    template = qin_edge_pilot_frame(RATE, "lower")
    x = np.zeros(PROBE_SAMPLES, dtype=np.complex128)
    epoch = 2991
    frequency = 37_000.
    for frame in np.rint(np.arange(14) * RATE / 750).astype(int):
        start = frame + epoch
        stop = min(x.size, start + template.size)
        x[start:stop] = template[:stop-start]
    x *= np.exp(2j * np.pi * frequency * np.arange(x.size) / RATE)
    rng = np.random.default_rng(186)
    x += .08 * (rng.normal(size=x.size) + 1j * rng.normal(size=x.size))
    gate = Gate(frequency + 170., phase_at(epoch, 0) + .3, 1600., 12.)
    blind, guided = bank.search(x, 0), bank.search(x, 0, (gate,))
    assert all(positive(result) for result in (blind, guided))
    assert compare(blind, guided)["agreement"]["within_8khz_and_1p6us"]
    for result in (blind, guided):
        assert abs(result["winner"]["cfo_hz"] - frequency) < 1000.
        assert abs(result["winner"]["epoch_sample"] - epoch) <= 2
    assert guided["scored_epoch_alias_cfo_cells"] < blind["scored_epoch_alias_cfo_cells"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "iq-check.json")
    args = parser.parse_args()
    banks = {edge: PilotBank(edge) for edge in ("lower", "upper")}
    check(banks["lower"])
    if args.check_only:
        print("Qin waveform search synthetic check passed")
        return
    start = time.perf_counter()
    results = []
    for index, case in enumerate(CASES):
        try:
            result = run_case(case, index, banks)
        except subprocess.CalledProcessError as exc:
            result = dict(case=case, status="archive_read_failed", reason=exc.stderr.decode(errors="replace").strip())
        except (ValueError, zstandard.ZstdError) as exc:
            result = dict(case=case, status="archive_payload_unusable", reason=str(exc))
        results.append(result)
        print(case, result["status"], flush=True)
    report = dict(
        scope="Archived raw IQ supplemental sample. RX1 fixed. Two distinct 20 ms windows per case. Blind and guided comparisons within each test use identical second-window samples.",
        selection="Windows 0 and 8 for fixed panel positions 1, 4 and 8; windows 0 and 1 otherwise. Every window 0 also has a disjoint first-10-ms blind seed versus second-10-ms blind and guided comparison. Guided tests require an available prior seed and never condition selection on the test window outcome.",
        read_cap_mib=62,
        compressed_bytes_read=sum(case.get("compressed_bytes_read", 0) for case in results),
        qin_bank=dict(rate_hz=RATE, folded_lags_samples=[4, 20], max_epoch_proposals=PROPOSALS,
                      epoch_refinement_half_samples=REFINE_SAMPLES, ofdm_symbols=64,
                      aliases=ALIASES.tolist(), fft_cells=FFT_SIZE, illustrative_margin=MARGIN),
        timing_scope="Single numerical thread on host. Bank wall time includes folded proposals and matched bank, excludes archive reads, decoding, template construction and Python import.",
        timing_wall_s=time.perf_counter() - start, synthetic_check="passed", cases=results, summary=summary(results),
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
