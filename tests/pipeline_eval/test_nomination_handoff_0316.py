from reports.ALGO08.v3.nomination_handoff_0316 import observed_reuse


def test_completed_lean_candidate_charges_capture_without_claiming_fallback_reuse():
    route = dict(choice={"route": "lean"}, lean_attempts=[{"decision": "complete"}],
                 nomination_handoff={"ranked_nodes": 6, "prefixes_captured": 3})
    assert all(observed_reuse(route).values())


def test_fallback_or_direct_named_are_reported_separately_from_capture():
    route = dict(choice={"route": "lean"}, lean_attempts=[{"decision": "fallback", "fallback_clocks": {"cpu_s": 1.0}}],
                 nomination_handoff={"ranked_nodes": 6, "prefixes_captured": 3, "prefixes_reused": 3})
    observed = observed_reuse(route)
    assert observed["producer_captured_complete_rank_and_prefix"]
    assert not observed["lean_complete_without_fallback"] and not observed["no_fallback_reuse"]
    assert not observed_reuse(dict(choice={"route": "named"}, lean_attempts=[]))["producer_captured_complete_rank_and_prefix"]
