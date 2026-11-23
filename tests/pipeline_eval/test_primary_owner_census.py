import json

import pytest

from reports.ALGO08.v3.primary_owner_census import census, digest, joined_owners


def owner_digest(catalog):
    return "sha256:" + digest(json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode())


def saved_packet():
    evidence = ("test:0:123", "test:0:456", "test:1:123", "test:1:456")
    names = ["sha256:" + digest(value.encode()) for value in evidence]
    probes = [{"candidates": [{"candidate_rank": rank}]} for rank in (0, 1, 0)] + [{"candidates": []}]
    keys = [(1, 3, 0.1, -12000.), (1, 3, 0.3, -12000.), (2, 3, 0.1, -12000.)]
    observations = [dict(observation_id=name, receiver=rx, channel=channel, time_s=time, measured_cfo_hz=cfo)
                    for name, (rx, channel, time, cfo) in zip(names, keys)]
    packet = dict(owner_rows={"c0": [[*keys[1], 15]], "fitted_c": [[*keys[1], 15], [*keys[2], 18]]},
                  owners={"c0": owner_digest({names[1]: 15}),
                          "fitted_c": owner_digest({names[1]: 15, names[2]: 18})})
    return probes, evidence, observations, packet


def test_distinct_arms_keep_their_denominators_and_exact_ranks():
    probes, evidence, observations, packet = saved_packet()
    owners = joined_owners(probes, evidence, observations, packet, owner_digest)
    result = census(probes, owners, range(len(probes)))
    assert result == dict(opportunities=4, selected=dict(total=3, rank0=2, rank1=1),
                          owned={"c0": dict(total=1, rank0=0, rank1=1),
                                 "fitted_c": dict(total=2, rank0=1, rank1=1)})
    assert census(probes, owners, {0, 2, 3})["owned"]["c0"] == dict(total=0, rank0=0, rank1=0)


def test_nearby_owner_and_wrong_norad_cannot_pass_exact_join():
    probes, evidence, observations, packet = saved_packet()
    packet["owner_rows"]["c0"][0][3] += 1e-8
    with pytest.raises(ValueError, match="No exact native observation"):
        joined_owners(probes, evidence, observations, packet, owner_digest)

    probes, evidence, observations, packet = saved_packet()
    packet["owner_rows"]["c0"][0][-1] += 1
    with pytest.raises(ValueError, match="reconstruct owner digest"):
        joined_owners(probes, evidence, observations, packet, owner_digest)
