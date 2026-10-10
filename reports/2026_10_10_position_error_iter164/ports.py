"""Source-only adapters over129 search/continuation and150 handoff."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = HERE.parent/'2026_10_09_position_error_iter129'
POLICY=dict(search_slices=6,slice_seconds=500,continuation_slices_per_branch=2,workers=2,threads=1,point_budget=400,levels_km=[40.,20.,10.,5.],discovery_arms={'native':'fitted-c','zero':'zero-c'},modes=['native','zero'],basins=3,separation_km=12.5,local_radius_km=25.,fresh_native=True,fresh_zero=True,historical_point_import='off',final_arms=['zero-c','fitted-c'],fallback='none',handoff='frozen150')

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def replace_once(source,old,new):
    if source.count(old)!=1:raise ValueError('parent source shape changed: '+old)
    return source.replace(old,new)

def native_score(objective,vector,bank,expected_native,**options):
    # Existing fit objective already computed; no common-bank model evaluation.
    return {'native':{'objective':expected_native}}

def search_source(source):
    source=replace_once(source,'for mode in ("native", "fixed"):','for mode in ("native", "zero"):')
    source=replace_once(source,'["point", e, n, "fitted-c"], lambda: evaluator(e, n, "fitted-c")','["point", e, n, "fitted-c" if mode == "native" else "zero-c"], lambda: evaluator(e, n, "fitted-c" if mode == "native" else "zero-c")')
    source=replace_once(source,'failures[str((e, n))] = dict(point=[e, n], error=str(error))','failures[str((e, n, mode))] = dict(point=[e, n], discovery_arm="fitted-c" if mode == "native" else "zero-c", error=str(error))')
    return replace_once(source,'return row["scores"][mode]["objective"]','return row["scores"]["native"]["objective"]')

def continuation_source(source):
    source=replace_once(source,'fetched(["point", *point, "fitted-c"])["fit"]','fetched(["point", *point, "fitted-c" if branch == "native" else "zero-c"])["fit"]')
    return replace_once(source,'recover=backend["recovered_region"],','recover=RECOVERY_PORT(backend, "fitted-c" if branch == "native" else "zero-c"),')

def dependencies():
    return load('ports129_for151',PARENT/'ports.py').dependencies()

def search_slice(*args,evaluator_factory=None,**kwargs):
    source=search_source((PARENT/'search.py').read_text());namespace={'__name__':'search129_for151'}
    exec(compile(source,str(PARENT/'search.py'),'exec'),namespace)
    if evaluator_factory is None:
        driver=args[4]
        evaluator_factory=lambda *a:driver.PointEvaluator(*a,scorer=native_score)
    return namespace['search_slice'](*args,evaluator_factory=evaluator_factory,**kwargs)

def continue_slice(*args,recovery_factory=None,**kwargs):
    transition=load('transition150_for151',HERE.parent/'2026_10_10_position_error_iter150/transition.py')
    namespace={'__name__':'continue129_for151','RECOVERY_PORT':recovery_factory or transition.recovery_port}
    source=continuation_source((PARENT/'continuation.py').read_text())
    exec(compile(source,str(PARENT/'continuation.py'),'exec'),namespace)
    return namespace['continue_slice'](*args,**kwargs)

