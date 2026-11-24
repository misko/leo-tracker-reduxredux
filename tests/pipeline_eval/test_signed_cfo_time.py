"""Same-atom matching and chronological block boundaries."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"reports"/"ALGO08"/"v3"))
from signed_cfo_time import ALIAS, SAMPLE_RATE, blocks, dependence, difference, split


def factor(hz, integer, frac=0.):
    return dict(fractional_tracking_cfo_hz=hz, integer_epoch_sample=integer, fractional_epoch_offset_samples=frac)


def row(i, *, short=True,lift=0,piece="measure"):
    return dict(id=i, track="track", piece=piece, ordinal=i, lift=lift,
                counter=i*SAMPLE_RATE, short=short, lane_index=i)


def test_measurement_atom_has_no_alias_or_timing_wrap():
    source = factor(120, 100, .125)
    assert difference(source,factor(114, 99, .5)) == (-6,-.625,True,True)
    assert difference(source,factor(120+ALIAS,100))[2:] == (False,True)
    assert difference(source,factor(120,13_433))[2:] == (False,True)
    assert difference(source,factor(371,100))[2:] == (False,False)


def test_blocks_preserve_piece_endpoints_and_anchors_and_same_alias():
    points = [row(i,short=i!=3,lift=int(i>=6)) for i in range(10)]
    assert blocks(points) == [[1,2],[4,5],[6,7]]
    points[7]["counter"] += 4*SAMPLE_RATE
    assert blocks(points) == [[1,2],[4,5]]


def test_split_breaks_missing_member_and_changed_relative_alias():
    def match(i, lift=0):
        return dict(candidate=row(i,lift=lift),installed=row(i),relative_lift=lift)
    timeline = [match(0),match(1),match(3),match(4,1)]
    assert [len(run) for run in split(timeline)] == [2,1,1]


def test_detrend_subtracts_affine_component_and_lag_calls_never_cross_gaps():
    clean = [1,-1,2,-2,1,-1,2,-2]
    shifted = [dict(candidate=row(i),installed=row(i),relative_lift=0,value=x+2*i+11)
               for i,x in enumerate(clean)]
    base = [dict(m,value=x) for m,x in zip(shifted,clean,strict=True)]
    a = dependence([shifted],"value")
    b = dependence([base],"value")
    assert a["detrended"][0] == 7
    assert a["detrended"][1] == pytest.approx(b["detrended"][1])
    assert a["strict_opportunity_adjacency"] == a["detrended"]
    assert sum(r["pairs"] for r in a["variogram"]) == 28
    assert dependence([shifted[:4],shifted[4:]],"value")["detrended"] == [0,None]
