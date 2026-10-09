"""Fixed receipt selection; neither reference error nor fitted score is inspected."""


def source_for(label, retry_members):
    return "retry86" if label in retry_members else "original84"


def selected_receipt(label, member, plan, original, retry):
    source = source_for(label, plan["retry_members"])
    receipt = retry if source == "retry86" else original
    if receipt is None:
        return dict(status="pending", selected_source=source)
    expected = plan["retry_protocol_sha256"] if source == "retry86" else plan["original_protocol_sha256"]
    assert receipt["member"] == member
    assert receipt["protocol_sha256"] == expected
    return dict(receipt, selected_source=source, source_protocol_sha256=expected)
