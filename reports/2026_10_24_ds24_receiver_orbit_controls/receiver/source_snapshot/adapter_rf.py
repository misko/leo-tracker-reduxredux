"""Predeclared primary: 50 Hz RF-scaled RX1 shared process."""
from adapter import build_method

def build(d,arm,reference,case):
    return build_method(d,arm,reference,case,'fast_rx1_rf50')
