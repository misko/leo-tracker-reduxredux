from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_hash_adapter import descriptor,original


def test_manifest_hash_is_not_stripped_for_prefixed_loader_contract():
    for row in original.membership():
        case=descriptor(row)
        assert case.raw_sha256==row['raw_npy']['sha256']
        assert case.raw_sha256.startswith('sha256:') and len(case.raw_sha256)==71
        assert case.source_counter==row['source_start_counter']
        assert case.split=='development' and case.activity_policy=='recorded_unknown'
