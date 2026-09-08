from tools.report_native_presence_power import quality_counts


def test_quality_counts_do_not_promote_extra_flags_to_reference_matches():
    def row(reference, matched, detected, rate=5000000, variant="fast"):
        return {
            "variant": variant,
            "result": {"rate_hz": rate},
            "reference_positive": reference,
            "matched_reference": matched,
            "detected": detected,
        }

    rows = [
        row(True, True, True),
        row(True, False, True),
        row(True, False, False),
        row(False, False, True),
        row(True, True, True, rate=2500000),
        row(True, True, True, variant="other"),
    ]
    assert quality_counts(rows, "fast", 5000000) == (1, 1, 1)
    assert quality_counts(rows, "absent", 5000000) == (0, 0, 0)
