"""Complete low-rate overview and downloadable, non-truncated probe evidence."""

import gzip
import io

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.starlink.partial_band_segments import associate_partial_band_segments
from leo.contracts.digests import canonical_json_bytes


def render_partial_band(binding, visits):
    probes = [p for visit in visits for p in visit.probes]
    if len(probes) != binding.expected_probes:
        raise ValueError("cannot render incomplete probe inventory")
    segments = associate_partial_band_segments(probes)
    artifacts = {
        "probes.jsonl.gz": gzip.compress(
            b"".join(canonical_json_bytes(p.model_dump(mode="json")) + b"\n" for p in probes),
            mtime=0,
        ),
        "segments.json": canonical_json_bytes(
            dict(
                schema_version=1,
                binding_sha256=binding.digest,
                policy="separate-target-rx-cfo-joins-gap1p5s-ambiguous-abstain-v1",
                segments=segments,
                candidate_only=True,
            )
        ),
    }
    for name in ("coverage", "glrt64-response", "cfo-trajectories", "bandwidth"):
        fig = Figure(figsize=(14, 8), layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(4, 1, sharex=True)
        for channel, ax in enumerate(axes, 1):
            for rx in (0, 1):
                rows = [p for p in probes if p.channel == channel and p.receiver_id == rx]
                color = ("#2367a8", "#c56719")[rx]
                if name == "coverage":
                    ax.scatter(
                        [p.time_s for p in rows],
                        [rx] * len(rows),
                        s=3,
                        c=color,
                        label=f"RX{rx}: {len(rows)} analyzed probes",
                    )
                    hits = [p for p in rows if p.state == "candidate"]
                    ax.scatter(
                        [p.time_s for p in hits], [rx + 0.18] * len(hits), s=3, c=color, marker="x"
                    )
                    ax.set_yticks((0, 1), ("RX0", "RX1"))
                elif name == "glrt64-response":
                    ax.scatter(
                        [p.time_s for p in rows],
                        [
                            max((c.evaluation_score for c in p.candidates), default=0.0)
                            for p in rows
                        ],
                        s=3,
                        c=color,
                        label=f"RX{rx} evaluation",
                    )
                    ax.plot(
                        [p.time_s for p in rows],
                        [p.control_training_score for p in rows],
                        color=color,
                        alpha=0.4,
                        lw=0.5,
                        label=f"RX{rx} searched control (fit)",
                    )
                    ax.set_ylabel("Projection score")
                else:
                    points = [(p, c) for p in rows for c in p.candidates if c.passed]
                    ax.scatter(
                        [p.time_s for p, c in points],
                        [
                            c.cfo_hz / 1000
                            if name == "cfo-trajectories"
                            else c.observable_tone_centers
                            for p, c in points
                        ],
                        s=3,
                        c=color,
                        label=f"RX{rx} confirmed candidates",
                    )
                    ax.set_ylabel(
                        "Receiver CFO (kHz)"
                        if name == "cfo-trajectories"
                        else "Tone centers in model band"
                    )
                    if name == "cfo-trajectories":
                        for seg in segments:
                            if seg["channel"] == channel and seg["receiver_id"] == rx:
                                # Draw only consecutive observations within a retained visit.
                                observations = seg["observations"]
                                for a, b in zip(observations, observations[1:], strict=False):
                                    if a["visit_index"] == b["visit_index"]:
                                        ax.plot(
                                            [a["time_s"], b["time_s"]],
                                            [a["cfo_hz"] / 1000, b["cfo_hz"] / 1000],
                                            color=color,
                                            alpha=0.5,
                                            lw=0.6,
                                        )
            ax.set_title(
                f"CH{channel} · "
                + ",".join(sorted({p.edge for p in probes if p.channel == channel})),
                loc="left",
            )
            ax.legend(loc="upper right", fontsize=7)
            ax.grid(alpha=0.2)
        axes[-1].set_xlabel("Seconds since capture start; retune gaps are retained")
        fig.suptitle(
            f"{binding.session_id} · native 1.25 MS/s · {name}\n"
            "Experimental partial-band GLRT64 · grouped random evaluation · candidate-only"
        )
        stream = io.BytesIO()
        fig.savefig(stream, format="png", dpi=120, metadata={"Software": "leo-partial-band-v1"})
        artifacts[name + ".png"] = stream.getvalue()
    return artifacts
