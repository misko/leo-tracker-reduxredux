import importlib.util
from pathlib import Path
P=Path(__file__).with_name("run.py"); S=importlib.util.spec_from_file_location("to90_test",P); R=importlib.util.module_from_spec(S); S.loader.exec_module(R)
def test_frozen_full_fov_grid():
 assert R.WIDTHS==(10.,20.,25.,30.,40.,50.,60.,70.,80.,90.)
def test_half_angle_interpretation_from_imported_source():
 m=R.load(R.SOURCE,"to90_threshold_test"); assert m.all_samples_inside(m.np.array([[m.np.sin(m.np.radians(45)),0,m.np.cos(m.np.radians(45))]]),m.np.array([0,0,1.]),90)
