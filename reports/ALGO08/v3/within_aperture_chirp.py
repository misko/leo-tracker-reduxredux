"""Location-free, post-centroid chirp bounds for the installed semicoherent verifier."""

from dataclasses import dataclass
from math import cos, pi, sin, sqrt
from statistics import fmean


RATE = 10_000_000
TAPS = 44
SYMBOLS = 64
FFT = 512
BIN_HZ = RATE/(FFT*TAPS)
SLOPE_STRESS = 8000.
SYMBOL_TIMES = tuple((i-(SYMBOLS-1)/2)*TAPS/RATE for i in range(SYMBOLS))


def variance(x):
    mean = fmean(x)
    return fmean((v-mean)**2 for v in x)


VAR_U = variance(SYMBOL_TIMES)
VAR_U2 = variance(tuple(u*u for u in SYMBOL_TIMES))
VAR_SAMPLE = ((TAPS*SYMBOLS)**2-1)/(12*RATE**2)


@dataclass(frozen=True)
class Exposure:
    centres: tuple[float, ...]
    scout_width_s: float

    @property
    def centroid(self):
        return fmean(self.centres)

    @property
    def centred(self):
        return tuple(t-self.centroid for t in self.centres)

    @property
    def half_pilot(self):
        return (TAPS*SYMBOLS-1)/(2*RATE)

    @property
    def extent(self):
        return self.centres[0]-self.half_pilot, self.centres[-1]+self.half_pilot


def exposure(factor, short):
    """Literal fractional verifier support including the native bounds guard."""
    samples, max_frames = (80_000, 5) if short else (200_000, 15)
    offset = factor["fractional_epoch_offset_samples"]
    epoch = factor["integer_epoch_sample"]
    integer = abs(offset-round(offset)) <= 1e-12
    centres = []
    for frame in range(max_frames):
        start = epoch+(40_000*frame+1)//3+2*TAPS+offset
        if start < (0 if integer else 7) or start+TAPS*SYMBOLS-1 >= samples-(0 if integer else 8):
            break
        centres.append((start+(TAPS*SYMBOLS-1)/2)/RATE)
    if not centres:
        raise ValueError("Factor lies outside its verified pilot exposure")
    scout_frames = 5 if short else 14
    scout_width = ((40_000*(scout_frames-1)+1)//3)/RATE
    return Exposure(tuple(centres), scout_width)


def bounds(scope, rate):
    """Bound the ideal power perturbation at every f and the sample support."""
    x = scope.centred
    variance_x = variance(x)
    uniform = pi**2 * rate**2 * (4*variance_x*VAR_U+VAR_U2)
    h = scope.half_pilot
    arc = []
    for centre in x:
        a,b = centre-h,centre+h
        squares = (a*a,b*b,0.) if a<=0<=b else (a*a,b*b)
        arc.append(pi*abs(rate)*(max(squares)-min(squares)))
    phase = max(arc)
    low,high = scope.extent
    return dict(duration_s=high-low,radius_s=max(abs(low-scope.centroid),abs(high-scope.centroid)),
                instantaneous_span_hz=abs(rate)*(high-low),
                deterministic_uniform_spread_hz=abs(rate)*sqrt(variance_x+VAR_SAMPLE),
                uniform_power_bound=min(1.,uniform), max_frame_phase_arc_rad=phase,
                unequal_weight_symbol_power_bound=min(1.,2*sin(min(pi,phase)/2)),
                ideal_center_power_loss_bound=sin(min(pi,phase)/2)**2,
                delay_product_phase_spread_rad=2*pi*abs(rate)*(TAPS*SYMBOLS/(2*RATE))*scope.scout_width_s)


def ideal_power(scope, rate, frequency):
    """Symmetric symbol-spectrum equation used by the independent component test."""
    sums = []
    for t in scope.centred:
        phases = tuple(2*pi*((rate*t-frequency)*u+rate*u*u/2) for u in SYMBOL_TIMES)
        sums.append(fmean(cos(p) for p in phases)**2+fmean(sin(p) for p in phases)**2)
    return fmean(sums)


def compare_bounds(full, short, slope, acceleration_bound):
    b20,b8 = bounds(full,slope),bounds(short,slope)
    return dict(centroid_term_hz=slope*(short.centroid-full.centroid),
                centered_carrier_support_bound_hz=abs(slope)*(b20["radius_s"]+b8["radius_s"]),
                combined_uniform_frame_spread_hz=sqrt(b20["deterministic_uniform_spread_hz"]**2+
                                                     b8["deterministic_uniform_spread_hz"]**2),
                centroid_curvature_bound_hz=acceleration_bound/2*(variance(full.centres)+variance(short.centres)+2*VAR_SAMPLE),
                candidate=b8,installed=b20)
