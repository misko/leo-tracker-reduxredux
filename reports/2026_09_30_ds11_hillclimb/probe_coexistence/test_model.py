import importlib.util
from pathlib import Path

import numpy as np

spec=importlib.util.spec_from_file_location('coexistence_model_test',Path(__file__).with_name('model.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    rng=np.random.default_rng(71)
    times=np.arange(10000)/m.FS
    pilot=np.exp(.5j*np.pi*rng.integers(0,4,(300,8)))
    frequencies=(np.arange(8)-3.5)*234375
    a,ta,ha=m.design(times,200.,20000.,frequencies,pilot)
    b,tb,hb=m.design(times,550.,-55000.,frequencies,pilot)
    c,_,_=m.design(times,550.,-55000.,frequencies,pilot,roll=11)
    return a,b,c,ta&tb,ha&hb


def test_one_signal_does_not_require_second_and_two_signals_do():
    a,b,c,train,held=fixture()
    gains=np.exp(1j*np.arange(8))
    matrices=dict(a=a,b=b,joint=np.column_stack((a,b)),control=np.column_stack((a,c)))
    one=m.compare(a@gains,matrices,train,held)
    two=m.compare(a@gains+.7*b@gains,matrices,train,held)
    assert one['a']['held_nmse']<1e-20 and one['joint']['held_nmse']<1e-20
    assert two['joint']['held_nmse']<1e-20
    assert two['a']['held_nmse']>.1 and two['control']['held_nmse']>.1


def test_held_mutation_cannot_change_training_fit():
    a,b,c,train,held=fixture(); y=a@np.ones(8)+b@np.ones(8)
    original=m.compare(y,dict(joint=np.column_stack((a,b))),train,held)
    y[held]*=3
    altered=m.compare(y,dict(joint=np.column_stack((a,b))),train,held)
    assert original['joint']['training_nmse']==altered['joint']['training_nmse']
    assert altered['joint']['held_nmse']>.1


def test_native_ifft_cp_and_resampling_agree_with_design():
    from scipy.signal import resample_poly
    rng=np.random.default_rng(29)
    pilot=np.exp(.5j*np.pi*rng.integers(0,4,(300,8)))
    bins=np.arange(488,496);center=491.5*234375
    native=np.zeros((302,1056),complex)
    for symbol in range(2,302):
        spectrum=np.zeros(1024,complex);spectrum[bins]=pilot[symbol-2]
        useful=np.fft.ifft(spectrum)*1024
        native[symbol]=np.r_[useful[-32:],useful]*np.exp(-2j*np.pi*center*np.arange(1056)/240e6)
    signal=native.ravel()*np.exp(2j*np.pi*20000*np.arange(native.size)/240e6)
    samples=resample_poly(signal,1,48)
    times=np.arange(len(samples))/m.FS
    matrix,train,held=m.design(times,0.,20000.,bins*234375-center,pilot)
    result=m.compare(samples,dict(pilot=matrix),train,held)
    assert result['pilot']['held_nmse']<.01
