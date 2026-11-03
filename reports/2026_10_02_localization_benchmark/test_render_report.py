from render_report import number, table


def test_missing_number_is_not_reported_as_zero():
    assert number(None) == "—"
    assert number(0) == "0.000"


def test_table_preserves_status_and_denominators():
    result = table(["Method", "Status", "Success"], [["test", "limit_reached", "2/16"]])
    assert "limit_reached" in result
    assert "2/16" in result
