"""Use the authenticated one-lane route on partner-on-hit without changing its native scorer."""

from types import SimpleNamespace
from unittest.mock import patch

from ..variants import second_on_miss
from . import second_on_miss_whole_raw as parent

TRACE = "partner-on-hit-lane-v1: "


def needs_partner(probe):
    return not second_on_miss.needs_partner(probe)


def run():
    with patch.multiple(
        parent, second_on_miss=SimpleNamespace(needs_partner=needs_partner), TRACE=TRACE
    ):
        parent.run()


if __name__ == "__main__":
    run()
