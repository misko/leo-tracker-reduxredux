"""Additive score accounting and training-ranked concentration diagnostics."""

import math


def summarize(rows):
    if not rows:
        raise ValueError("nonempty track rows required")
    keys = [(r["session_id"], r["track_id"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate track identity")
    loss = sum(max(-r["held_delta"], 0) for r in rows)
    gain = sum(max(r["held_delta"], 0) for r in rows)
    count = max(1, math.ceil(len(rows) * 0.1))
    ranked = sorted(
        rows, key=lambda r: (-max(-r["training_delta"], 0), r["session_id"], r["track_id"])
    )[:count]
    held_ranked = sorted(
        rows, key=lambda r: (-max(-r["held_delta"], 0), r["session_id"], r["track_id"])
    )[:count]
    positive_direction = sum(max(r["toward_original_gradient"], 0) for r in rows)
    directional = sorted(
        rows, key=lambda r: (-max(r["toward_original_gradient"], 0), r["session_id"], r["track_id"])
    )[:count]
    return {
        "tracks": len(rows),
        "held_observations": sum(r["held_count"] for r in rows),
        "held_delta": gain - loss,
        "gross_loss": loss,
        "gross_gain": gain,
        "positive_tracks": sum(r["held_delta"] > 0 for r in rows),
        "map_changed_tracks": sum(r["map_changed"] for r in rows),
        "same_map_held_delta": sum(r["held_delta"] for r in rows if not r["map_changed"]),
        "changed_map_held_delta": sum(r["held_delta"] for r in rows if r["map_changed"]),
        "top_decile_count": count,
        "training_ranked_gross_loss_share": sum(max(-r["held_delta"], 0) for r in ranked) / loss
        if loss
        else None,
        "held_ranked_gross_loss_share": sum(max(-r["held_delta"], 0) for r in held_ranked) / loss
        if loss
        else None,
        "training_ranked_held_delta": sum(r["held_delta"] for r in ranked),
        "direction_ranked_positive_gradient_share": sum(
            max(r["toward_original_gradient"], 0) for r in directional
        )
        / positive_direction
        if positive_direction
        else None,
    }
