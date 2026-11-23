"""Install the joint solver decision at the v3 inference boundary."""

from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import ARMS
from mixture_trial import elapsed


def make_route(installed, reader, attempts, *, repair, signed_finish=False, collect=None, cold_start=None,
               joint_proposal=None, signed_updater=None, postfit_repair=None):
    import numpy as np
    from tools.pipeline_eval.variants.experimental import regional_bound_guard
    from blind_joint_finish import propose
    from blind_joint_repair import repair_once
    from tools import algo08_position

    proposal = propose if joint_proposal is None else joint_proposal
    options = dict(repair=repair_once if repair else None)
    if cold_start is not None:
        options["cold_start"] = cold_start

    def route(prepared, search_region, bound, stages, *, selected_evidence=None):
        observed = {}
        attempts.append(observed)
        cpu, wall = process_time(), perf_counter()
        try:
            signed, reason = proposal(prepared, search_region, bound, observed, **options)
        except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
            signed, reason = None, f"{type(exc).__name__}: {exc}"
        observed["candidate_pre_evidence_clocks"] = elapsed(cpu, wall)
        if signed is not None and signed_finish:
            from blind_joint_signed import update

            ordinary = signed
            started, began = process_time(), perf_counter()
            try:
                signed = (update if signed_updater is None else signed_updater)(prepared, ordinary, observed)
            except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                signed, reason = None, f"signed_context: {type(exc).__name__}: {exc}"
            finally:
                observed["signed_total_clocks"] = elapsed(started, began)
            if collect is not None and signed is not None:
                collect(ordinary=ordinary, signed=signed)
        if signed is not None:
            cpu, wall = process_time(), perf_counter()
            endpoints = {key: record["endpoint_east_north_km"] for key, record in signed["arms"].items()}
            exterior = regional_bound_guard.inspect_boundary(
                endpoints, search_region.width_km,
                lambda: regional_bound_guard.causal_probes(prepared["tracks"], reader, search_region,
                                                           terminal_only=True), terminal_only=True,
            )
            observed.update(exterior=exterior, exterior_clocks=elapsed(cpu, wall))
            if exterior["would_withhold"]:
                observed["decision"] = "withheld"
                return dict(status="withheld", reason="both_receivers_support_far_exterior", metrics=stages,
                            arms={arm: {"latlon": None} for arm in ARMS})
            if exterior.get("diagnostic_error"):
                reason = "exterior_evidence_unavailable"
            else:
                evidence_inputs = prepared, signed
                proposed = False
                if postfit_repair is not None:
                    new_prepared, new_signed = postfit_repair(prepared, signed, observed)
                    proposed = new_signed is not signed
                    if proposed:
                        cpu, wall = process_time(), perf_counter()
                        endpoints = {key: record["endpoint_east_north_km"] for key, record in new_signed["arms"].items()}
                        followup = regional_bound_guard.inspect_boundary(
                            endpoints, search_region.width_km,
                            lambda: regional_bound_guard.causal_probes(prepared["tracks"], reader, search_region,
                                                                       terminal_only=True), terminal_only=True)
                        audit = observed["local_future_repair"]
                        audit.update(exterior=followup, exterior_clocks=elapsed(cpu, wall))
                        if followup["would_withhold"] or followup.get("diagnostic_error"):
                            audit.update(decision="rejected", reason="repair exterior decision")
                            proposed = False
                        else:
                            evidence_inputs = new_prepared, new_signed
                cpu, wall = process_time(), perf_counter()
                try:
                    if repair:
                        packet_builder = algo08_position.selected_packet

                        def complete_packet(*args, **kwargs):
                            packet = packet_builder(*args, **kwargs)
                            if not packet["position_grid"]["complete"]:
                                raise ValueError("The original numerical evidence grid is incomplete")
                            return packet

                        with patch.object(algo08_position, "selected_packet", complete_packet):
                            try:
                                selected_evidence(*evidence_inputs, None)
                            except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                                if not proposed:
                                    raise
                                observed["local_future_repair"].update(decision="rejected", reason=f"repair evidence: {exc}",
                                                discarded_evidence_clocks=elapsed(cpu, wall))
                                proposed = False
                                selected_evidence(prepared, signed, None)
                    else:
                        selected_evidence(prepared, signed, None)
                    if proposed:
                        signed = evidence_inputs[1]
                        observed["local_future_repair"]["decision"] = "accepted"
                except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
                    reason = f"standard_evidence: {type(exc).__name__}: {exc}"
                finally:
                    observed["standard_evidence_clocks"] = elapsed(cpu, wall)
            if reason is None:
                observed["decision"] = "complete"
                return dict(status="ok", reason=None, metrics=stages, arms={arm: dict(
                    latlon=list(record["endpoint_latlon"]), rf_rms_hz=float(record["RMS_hz"])
                ) for arm, record in signed["arms"].items()})
        observed.update(decision="fallback", reason=reason)
        cpu, wall = process_time(), perf_counter()
        try:
            return installed(prepared, search_region, bound, stages, selected_evidence=selected_evidence)
        finally:
            observed["fallback_clocks"] = elapsed(cpu, wall)

    return route
