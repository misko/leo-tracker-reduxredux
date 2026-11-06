"""Attribute original empty-prior work while retaining complete captured outputs."""

import ast
import hashlib
import inspect
import json
import time
from pathlib import Path

import algo07v3_prefixed_prior_oracle as reference
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint


def main():
    root = Path(__file__).resolve().parent
    source = inspect.getsource(reference.hierarchical_bound)
    tree = ast.parse(source)
    loop = next(n for n in tree.body[0].body
                if isinstance(n,ast.For) and ast.unparse(n.iter)=='range(iterations)')
    labels = {'precision':'precision_allocation',
              'precision[selected]':'empty_precision_assignment',
              'prior_energy':'empty_prior_energy','next_prior_rate':'empty_prior_rate'}
    body, found = [], []
    for node in loop.body:
        target = ast.unparse(node.targets[0]) if isinstance(node,ast.Assign) else ''
        if target in labels:
            label = labels[target]
            found.append(label)
            body += ast.parse('_began = _clock()').body
            body.append(node)
            body += ast.parse(f'_record({label!r}, _clock()-_began)').body
        else:
            if target=='change':
                assert isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='max'
                wrapper = ast.parse('_observe("empty_prior_change", lambda: None)',mode='eval').body
                wrapper.args[1].body = node.value.args[1]
                node.value.args[1] = wrapper
            body.append(node)
    assert sorted(found)==sorted(labels.values())
    loop.body = body
    tree = ast.fix_missing_locations(tree)
    (root/'profile-original.py').write_text(source)
    (root/'profile-generated.py').write_text(ast.unparse(tree)+'\n')
    cases = []
    base = Path('/srv/bulk/leo-dev')
    captures = [('initial',base/'algo07v3-initial-capture-20261106/fitted_c-capture'),
                ('recovery',base/'algo07v3-posterior-current-profile-20261105')]
    for name, capture in captures:
        metadata = json.loads((capture/'hardest.json').read_bytes())
        arrays_digest = hashlib.sha256((capture/'hardest.npz').read_bytes()).hexdigest()
        assert arrays_digest == metadata['arrays_sha256']
        with np.load(capture/'hardest.npz',allow_pickle=False) as data:
            args = [data[f'argument_{i}'] for i in range(4)]
            kw = dict(metadata['scalar_keywords'])
            kw.update({k.removeprefix('keyword_'):data[k] for k in data.files
                       if k.startswith('keyword_')})
        prior = kw.get('prior_groups')
        assert prior is None or np.all(prior < 0)
        expected = fingerprint(reference.hierarchical_bound(*args,**kw))
        before = fingerprint((args,kw))
        timings = {}
        def record(label, seconds, timings=timings):
            timings.setdefault(label,[]).append(seconds)
        def observe(label, operation, record=record):
            began = time.perf_counter()
            value = operation()
            record(label,time.perf_counter()-began)
            return value
        scope = dict(vars(reference),_clock=time.perf_counter,_record=record,_observe=observe)
        exec(compile(tree,'<profile-empty-priors>','exec'),scope)
        clocks = []
        for _ in range(3):
            began = time.perf_counter()
            actual = scope['hierarchical_bound'](*args,**kw)
            clocks.append(time.perf_counter()-began)
            assert fingerprint(actual)==expected
        assert before==fingerprint((args,kw))
        parts = {k:dict(calls=len(v),seconds=sum(v)) for k,v in timings.items()}
        cases.append(dict(name=name,capture=str(capture),arrays_sha256=metadata['arrays_sha256'],
            exact=True,seconds=clocks,parts=parts,
            observed_fraction=sum(map(sum,timings.values()))/sum(clocks)))
    paths=[Path(__file__),Path(reference.__file__),Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (root/'empty-update-profile.json').write_text(json.dumps(dict(cases=cases,
        profiled=True,full_pipeline_speedup=None,bindings=bindings),indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('name','observed_fraction')} for r in cases]))


if __name__=='__main__':
    main()
