"""Validate the saved census without hardware, database access or IQ replay."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_saved_census():
    protocol = json.loads((HERE / 'protocol.json').read_text())
    for name, expected in {**protocol['source_sha256'], **protocol['exclusion_hashes']}.items():
        assert digest(ROOT / name) == expected, name
    assert digest(ROOT / '2026_09_27_ds6_roof/approved-inventory.json') == protocol['inventory_sha256']
    assert digest(ROOT / '2026_09_27_ds6_phase_opportunity/ranking.json') == protocol['ranking_sha256']
    sessions = [row['session_id'] for row in protocol['selected']]
    assert len(sessions) == len(set(sessions)) == 10
    assert not set(sessions).intersection(protocol['excluded'])
    assert {p.name.removesuffix('-plan.json') for p in HERE.glob('*-plan.json')} == set(sessions)
    pairs = visits = training = held = scans = 0
    for sid in sessions:
        plan = json.loads((HERE / f'{sid}-plan.json').read_text())
        assert plan['session_id'] == sid
        assert plan['protocol_sha256'] == digest(HERE / 'protocol.json')
        seen = set()
        scans += bool(plan['eligible_groups'])
        for group in plan['eligible_groups']:
            partitions = [v['partition'] for v in group['visits']]
            assert set(partitions) == {'train', 'held'}
            assert partitions.count('train') >= 2 and partitions.count('held') >= 2
            training += partitions.count('train')
            held += partitions.count('held')
            pairs += 1
            for visit in group['visits']:
                assert visit['visit'] not in seen
                seen.add(visit['visit'])
        visits += len(seen)
    assert (scans, pairs, visits, training, held) == (5, 12, 250, 146, 104)


if __name__ == '__main__':
    test_saved_census()
    print('Saved census checks passed')
