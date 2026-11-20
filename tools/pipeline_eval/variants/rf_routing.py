"""Choose one configured physical RF for the original GLRT before dispatch begins."""

from hashlib import sha256
from re import fullmatch


def choose_rf(seed, rf_centers):
    """Rank integer-Hz centres by a fixed seed, independent of detections or survey."""
    if not isinstance(seed, str) or not fullmatch(r"(?:sha256:)?[a-fA-F0-9]{64}", seed):
        raise ValueError("a 256-bit hexadecimal assignment seed is required")
    seed = seed.removeprefix("sha256:").lower()
    centers = set()
    for center in rf_centers:
        if (
            isinstance(center, bool)
            or not isinstance(center, (int, float))
            or not 0 < center < 2**53
            or int(center) != center
        ):
            raise ValueError("configured RF centres must be positive integer Hz")
        centers.add(int(center))
    if not centers:
        raise ValueError("the receiver needs at least one configured RF centre")

    def rank(rf):
        return sha256(f"whole-rf-v1|{seed}|{rf}".encode("ascii")).digest(), rf

    return min(centers, key=rank)
