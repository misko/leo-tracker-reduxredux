from tools.pipeline_eval.qualification import compact_roof_completion as completion


def test_supplement_includes_only_unlaunched_and_preserves_planned_order():
    def row(attempted, source, status):
        return dict(attempted=attempted, source=source, result=dict(status=status))

    rows = {
        "y": row(False, "not_launched", "missing"),
        "z": row(False, "not_launched", "missing"),
        "timeout": row(True, "fresh_complement_replay", "timed_out"),
        "failure": row(True, "fresh_complement_replay", "failed"),
        "unavailable": row(False, "unavailable_input", "unavailable"),
        "uncertain": row(None, "unconfirmed_claim", "missing"),
    }
    order = ["timeout", "z", "unavailable", "failure", "uncertain", "y"]
    assert completion.unlaunched(rows, order) == ["z", "y"]
