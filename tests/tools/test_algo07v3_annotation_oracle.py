from types import ModuleType

from algo07v3_annotation_oracle import reference_annotation


def _run(args):
    out = args.output
    out.mkdir(parents=True)
    inv = read(args.inventory)  # noqa: F821
    d = context(inv)  # noqa: F821
    write(out/'protocol.json', dict(job=inv['job'], keep=d['keep']))  # noqa: F821
    write(out/'nominations-1.json', dict(norad=123))  # noqa: F821
    write(out/'seed-1.json', dict(seed=1))  # noqa: F821
    write(out/'result.json', dict(job=inv['job'], seconds=100., norad=123))  # noqa: F821


def test_annotation_oracle_captures_original_writes_without_directory_access():
    module = ModuleType('frozen_annotation')
    module.run, module.__file__ = _run, __file__
    result = reference_annotation(module, dict(keep=[True,False]), {},
                                  dict(track_id='target',inactive_fragment=False))
    assert result == dict(protocol=dict(keep=[True,False]), nominations={1:dict(norad=123)},
                          attempts={1:dict(seed=1)}, result=dict(norad=123))
