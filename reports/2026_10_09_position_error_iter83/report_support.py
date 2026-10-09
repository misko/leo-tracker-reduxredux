"""Full-membership reporting; pending cases never become zero-error results."""


def effective_result(binding, previous, receipt, digest):
    if receipt is not None:
        assert receipt["protocol_sha256"] == digest
        assert receipt["member"] == binding["member"]
        assert receipt["requested_extra_search"] == binding["requested_extra_search"]
        return receipt
    if not binding["requested_extra_search"]:
        return dict(status="retained_by_frozen_rule", operational=previous,
                    fallback_arms=[], receipt_written=False)
    return dict(status="pending", operational=None, fallback_arms=[])


def full_values(rows, arm, field):
    """A full-group distribution is available only when every endpoint is known."""
    if any(r["operational"] is None for r in rows):
        return None
    return [r["operational"][arm][field] for r in rows]
