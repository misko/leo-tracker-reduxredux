from confirm_ds23_owner_only_reentry import gate_view


def test_owner_gate_view_preserves_original_bound_geometry_and_calibration():
    class Problem:
        def __init__(self):self.supported=[1,2]
        def state(self,x):return self.supported
        def calculate(self,x):return self.supported
        def conditional_frequency(self,x):return self.supported
    p=Problem();view=gate_view(p,[2])
    assert view.supported==[1]
    assert view.state(None)==[1,2]
    assert view.calculate(None)==[1,2]
    assert view.conditional_frequency(None)==[1,2]
    assert p.supported==[1,2]
