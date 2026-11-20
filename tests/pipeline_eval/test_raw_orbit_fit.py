from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval import corpus
from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification.raw_orbit_fit import check_packet


def packet_fixture():
    packet = dict(
        observation={"tracks": [{"times": [1.0, 2.0], "values": [14.0, 15.0]}]},
        offer={"center": [1.0, 2.0], "width_km": 25},
        catalogue="causal test elements",
    )
    receipt = dict(
        observation_sha256=sha256(corpus._packed(packet["observation"])).hexdigest(),
        input_sha256=sha256(encoded(packet)).hexdigest(),
        native_sha256="test-native",
        capture_authority={"clock_sha256": "test-clock"},
    )
    return packet, receipt


def test_both_methods_use_the_exact_receipted_fit_packet():
    packet, receipt = packet_fixture()
    result = check_packet(
        packet["observation"],
        packet,
        receipt,
        receipt["native_sha256"],
        receipt["capture_authority"],
    )
    assert result == receipt["observation_sha256"]


@pytest.mark.parametrize("change", ("clock", "native", "tile", "orbit", "measurement"))
def test_rejects_surrogate_support_or_catalogue(change):
    packet, receipt = packet_fixture()
    native = receipt["native_sha256"]
    authority = deepcopy(receipt["capture_authority"])
    if change == "clock":
        authority["clock_sha256"] = "different"
    elif change == "native":
        native = "different"
    elif change == "tile":
        packet["offer"]["width_km"] = 3
    elif change == "orbit":
        packet["catalogue"] = "future data"
    elif change == "measurement":
        packet["observation"]["tracks"][0]["values"][1] += 0.001
    with pytest.raises(ValueError, match="locked lean fit packet"):
        check_packet(packet["observation"], packet, receipt, native, authority)
