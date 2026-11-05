from types import SimpleNamespace

from algo07v3_cavity_oracle import numerical_one


def _original_one(case, output_dir=None):
    forbidden()  # noqa: F821
    try:
        d = setup(case)  # noqa: F821
        nom = read('old result')  # noqa: F821
        result = dict(status='complete', x=d['x'], names=nom['names'],
                      nomination_sha256=sha('old result'))  # noqa: F821
        print('not printed')
    except Exception as exc:
        result = dict(status='failed', error=repr(exc))
    finally:
        forbidden()  # noqa: F821
    write('old output', result)  # noqa: F821
    return result


def test_external_cavity_body_keeps_scientific_results_without_file_or_signal_access():
    module = SimpleNamespace(one=_original_one, __file__=__file__)
    # inspect.getsourcefile accepts modules, not arbitrary namespaces.
    import types
    original = types.ModuleType('test_cavity')
    original.one, original.__file__ = module.one, __file__
    assert numerical_one(original, dict(case='SCAN', x=3), dict(names=[1, 2])) == dict(
        status='complete', x=3, names=[1, 2])
