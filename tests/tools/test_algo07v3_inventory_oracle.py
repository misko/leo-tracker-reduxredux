from types import ModuleType

from algo07v3_inventory_oracle import original_inventory


def _original_one(args):
    forbidden_file_read()  # noqa: F821
    all_ids = {o['observation_id'] for o in observations}  # noqa: F821
    rows = [dict(arm='c0', count=len(all_ids), job_id=job['job_id'], label=job['label'],  # noqa: F821
                 aliases=job['aliases'], observation_ids=sorted(all_ids))]  # noqa: F821
    summary = [dict(arm='c0', total_GLRT=len(all_ids), scopes=job['scopes'])]  # noqa: F821
    write('not allowed', dict(tracks=rows, summary=summary))  # noqa: F821
    forbidden_file_write()  # noqa: F821


def test_inventory_oracle_executes_original_arithmetic_without_io():
    original = ModuleType('original_inventory')
    original.one = _original_one
    original.__file__ = __file__
    pair = {'paired': True}
    actual = original_inventory(original, [], [dict(observation_id='native')], pair, ['source'])
    assert actual == dict(summary=[dict(arm='c0', total_GLRT=1)], tracks=[dict(
        arm='c0', count=1, observation_ids=['native'])], policy=pair, prior_policy=pair)
