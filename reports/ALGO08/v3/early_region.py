"""Move the original far-exterior proof before expensive inference, with per-inference reuse."""

from contextlib import contextmanager
from time import process_time
from unittest.mock import patch


def before_fit(fit, reader, check, audit, catalogue_for, *, skip_empty=False):
    from tools.pipeline_eval.variants.experimental import regional_bound_guard as guard

    def route(prepared, region, bound, stages, **kwargs):
        tracks = prepared["tracks"]
        clocks = process_time()
        if skip_empty and len(tracks["tracks"]) == 0:
            # The regional likelihood cannot score an empty graph. Let the original
            # inference path decide whether this input warrants a position.
            audit.append(dict(result=dict(complete=False, reason="no_graph_tracks_to_score"),
                              cpu_s=process_time()-clocks, reused=0, skipped_empty_graph=True))
            return fit(prepared, region, bound, stages, **kwargs)
        try:
            proof = check(tracks, reader, region, terminal_only=True)
        except (OSError, ValueError) as exc:
            proof = {"complete": False, "diagnostic_error": str(exc)}
        row = dict(result=proof, cpu_s=process_time()-clocks, reused=0)
        audit.append(row)
        if proof.get("complete") and proof.get("would_withhold"):
            return dict(status="withheld", reason="both_receivers_support_far_exterior",
                        arms={name: dict(latlon=None) for name in guard.ARMS},
                        metrics=dict(stages, regional_bound_guard=proof))
        if not proof.get("complete"):
            return fit(prepared, region, bound, stages, **kwargs)

        def reuse(other_tracks, archive, offered, *, catalogue=None, terminal_only=False):
            if (other_tracks is tracks and archive.root == reader.root and offered is region and terminal_only
                    and (catalogue is None or catalogue is catalogue_for(tracks, reader))):
                row["reused"] += 1
                return dict(proof)
            return check(other_tracks, archive, offered, catalogue=catalogue, terminal_only=terminal_only)

        with patch.object(guard, "causal_probes", reuse):
            return fit(prepared, region, bound, stages, **kwargs)

    return route


@contextmanager
def preflight(reader, audit, counts):
    from prepared_exterior import handoff
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard as guard

    with handoff(reader) as (live, tally, _):
        with patch.object(v5_core, "infer", before_fit(v5_core.infer, reader, guard.causal_probes, audit, live.match)):
            yield
        counts.update(tally)
