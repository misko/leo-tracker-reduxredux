"""Prospective validation of recurring, non-pilot header sign patterns."""

import hashlib
import json

import matplotlib
import numpy as np
from analyze import OUT

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    hypothesis_path = OUT / "word-hypothesis.json"
    h = json.loads(hypothesis_path.read_text())
    out = OUT / "holdout-upper"
    inventory = json.loads((out / "inventory.json").read_text())
    records = json.loads((out / "recovery.json").read_text())
    archive = np.load(out / "recovery-soft-symbols.npz")
    assert np.array_equal(archive["bins"], h["subcarrier_indices"])
    for row in inventory["exports"]:
        assert row["session_id"] == h["holdout_session"]
        assert row["probe"]["visit_index"] == h["holdout_visit"]
    values = [archive[r["name"] + "_deviations"][:, h["ofdm_symbol"] - 2, :].real for r in records]
    proposed = [
        np.array([1 if b == "1" else -1 for b in h[f"phase_{phase}_word"]]) for phase in [0, 1]
    ]
    alignment = np.arange(h["alignment_frames"])
    scores = []
    for offset in range(3):
        scores.append(
            sum(
                float(
                    np.sum(
                        values[0][alignment[(alignment + offset) % 3 == phase], :2]
                        * proposed[phase][:2]
                    )
                )
                for phase in [0, 1]
            )
        )
    offset = int(np.argmax(scores))
    variance = np.array(
        [np.mean([d["pilot_holdout_evm"] ** 2 for d in r["diagnostics"]]) for r in records]
    )
    weights = 1 / variance
    weights /= weights.sum()
    combined = sum(w * z for w, z in zip(weights, values, strict=True))
    validation_frames = np.arange(h["alignment_frames"], len(combined))
    rng = np.random.default_rng(208947)
    results = []
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    for phase in [0, 1]:
        indices = validation_frames[(validation_frames + offset) % 3 == phase]
        checks = []
        for name, x in zip(["RX0", "RX1", "combined"], [*values, combined], strict=True):
            sample = x[indices]
            mean = sample.mean(axis=0)
            se = sample.std(axis=0, ddof=1) / np.sqrt(len(sample))
            boot = sample[rng.integers(0, len(sample), size=(5000, len(sample)))].mean(axis=1)
            # Simultaneous 99% bootstrap band over the 24 inspected positions.
            radius = float(
                np.quantile(np.max(abs(boot - mean) / np.maximum(se, 1e-12), axis=1), 0.99)
            )
            lower, upper = mean - radius * se, mean + radius * se
            word = "".join("1" if v > 0 else "0" for v in mean)
            certified = "".join(
                "1" if lo > 0 else "0" if hi < 0 else "?"
                for lo, hi in zip(lower, upper, strict=True)
            )
            checks.append(
                dict(
                    source=name,
                    frames=len(indices),
                    frame_indices=indices.tolist(),
                    mean_sign_pattern=word,
                    simultaneous_99_percent_pattern=certified,
                    matches_frozen_proposal=(word == h[f"phase_{phase}_word"]),
                    mean=mean.tolist(),
                    lower=lower.tolist(),
                    upper=upper.tolist(),
                    simultaneous_bootstrap_radius=radius,
                )
            )
            if name == "combined":
                axes[phase].errorbar(
                    np.arange(24),
                    mean,
                    yerr=radius * se,
                    fmt="o",
                    capsize=3,
                    label="held-out combined mean; simultaneous 99% bootstrap band",
                )
        axes[phase].plot(
            np.arange(24), proposed[phase], "x", color="tab:orange", label="frozen proposal"
        )
        axes[phase].axhline(0, color="grey", lw=0.8)
        axes[phase].axvline(11.5, color="grey", ls="--", lw=0.8)
        axes[phase].set(
            ylabel="Template-removed I",
            title=f"Frozen proposal for phase {phase}: "
            f"{h[f'phase_{phase}_word'][:12]} | {h[f'phase_{phase}_word'][12:]}",
        )
        axes[phase].legend(fontsize=8)
        results.append(dict(phase=phase, proposed_word=h[f"phase_{phase}_word"], validation=checks))
    axes[-1].set_xticks(np.arange(24), h["subcarrier_indices"], rotation=60)
    axes[-1].set_xlabel("Native OFDM subcarrier index; the dashed gap excludes known pilots")
    fig.suptitle("Held-out DS7 visit 208: recurring data signs in OFDM symbol 4")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out / "recurring-word-validation.png", dpi=160)
    result = dict(
        hypothesis_sha256=hashlib.sha256(hypothesis_path.read_bytes()).hexdigest(),
        session_id=h["holdout_session"],
        visit=h["holdout_visit"],
        ofdm_symbol=h["ofdm_symbol"],
        subcarrier_indices=h["subcarrier_indices"],
        alignment_scores=scores,
        selected_cyclic_offset=offset,
        excluded_alignment_frames=h["alignment_frames"],
        period_frames=3,
        nominal_period_s=3 / 750,
        cycle_hypothesis_validated=all(
            check["matches_frozen_proposal"]
            for word in results
            for check in word["validation"]
            if check["source"] == "combined"
        ),
        observed_combined_patterns=[
            check["simultaneous_99_percent_pattern"]
            for word in results
            for check in word["validation"]
            if check["source"] == "combined"
        ],
        words=results,
        limitations=[
            "Signs are relative to the published template and SSS phase convention.",
            "Frequency gaps mean these are not asserted contiguous packet bytes.",
            "Bootstrap bands assume repeat observations; they are not FEC/CRC checks.",
            "The proposed cycle failed held-out validation; do not interpret it as timing data.",
        ],
    )
    (out / "recurring-words.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
