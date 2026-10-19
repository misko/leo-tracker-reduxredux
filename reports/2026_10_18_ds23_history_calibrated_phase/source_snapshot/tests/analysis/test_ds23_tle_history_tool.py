"""Historical trend priors must not learn from epoch round-trip duplicates."""

import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from export_ds23_causal_history import distinct_epochs


def test_distinct_history_drops_subsecond_epoch_duplicates():
    rows=[dict(epoch=10_000_000_000,collected_utc_ns=20),
          dict(epoch=10_000_800_000,collected_utc_ns=30),
          dict(epoch=5_000_000_000,collected_utc_ns=15)]
    assert [r['epoch'] for r in distinct_epochs(rows)]==[5_000_000_000,10_000_800_000]


def test_first_publication_of_same_epoch_preserves_historical_causality():
    rows=[dict(epoch=100,collected_utc_ns=20),dict(epoch=100,collected_utc_ns=10)]
    assert distinct_epochs(rows)[0]['collected_utc_ns']==10
