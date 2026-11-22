"""Recover absolute pilot scores only when the retained observation can use them."""


def retained_factor(votes, recover):
    """Return the retained exact factor, or None. Indices follow the supplied votes."""
    if len(votes) > 2:
        raise ValueError("At most two measured carriers per RF lane")
    if not votes or max(votes) < 3:
        return None
    if len(votes) == 1:
        return recover(0)
    if abs(votes[0] - votes[1]) >= 2:
        # The deployed vote override selects this carrier for either margin ordering.
        return recover(0 if votes[0] > votes[1] else 1)
    pair = [recover(0), recover(1)]
    winner = max(range(2), key=lambda i: (pair[i]["fractional_margin"], -pair[i]["candidate_rank"]))
    return pair[winner] if votes[winner] >= 3 else None
