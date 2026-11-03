"""Wrapped Student offset plus Cauchy noise, with residual/scale derivatives."""
import math

import numpy as np

from offset_grid_quadrature import prepare


def student_wrapped(r, period, scale, df):
    x = ((np.asarray(r)+period/2) % period-period/2)[..., None]+period*np.arange(-8, 9)
    constant = math.exp(math.lgamma((df+1)/2)-math.lgamma(df/2))/math.sqrt(df*np.pi)/scale
    terms = constant*(1+(x/scale)**2/df)**(-(df+1)/2)
    dr = -(df+1)*x/(df*scale*scale+x*x)
    ds = (-1+(df+1)*x*x/(df*scale*scale+x*x))/scale
    return terms.sum(axis=-1), (terms*dr).sum(axis=-1), (terms*ds).sum(axis=-1)


def _quadrature_pdf(r, period, scale, df, noise, order=None):
    if order is None:
        previous = _quadrature_pdf(r, period, scale, df, noise, order=32)
        for refinement in [64, 128, 256]:
            current = _quadrature_pdf(r, period, scale, df, noise, order=refinement)
            if np.max(abs(current/previous-1)) < 1e-8:
                return current
            previous = current
        raise ArithmeticError('marginal quadrature did not converge')
    groups = [dict(period_hz=period, residuals_hz=[float(x)]) for x in np.ravel(r)]
    weights, ratios = prepare(groups, scale, df, noise, order=order)
    return (ratios@np.exp(weights)/period).reshape(np.shape(r))


def density(r, period, scale, df, noise, *, derivatives=True):
    """Return PDF, dPDF/dresidual, dPDF/doffset_scale; noise is fixed."""
    if period <= 0 or scale <= 0 or noise < 0 or df <= 2:
        raise ValueError('invalid marginal density parameters')
    r = np.asarray(r, dtype=float)
    if noise == 0:
        return student_wrapped(r, period, scale, df)
    if df != int(df) or int(df) % 2 == 0:
        value = _quadrature_pdf(r, period, scale, df, noise)
        if not derivatives:
            return value, None, None
        step = max(.001, scale*1e-5)
        dr = (_quadrature_pdf(r+step, period, scale, df, noise)
              -_quadrature_pdf(r-step, period, scale, df, noise))/(2*step)
        ds = (_quadrature_pdf(r, period, scale+step, df, noise)
              -_quadrature_pdf(r, period, scale-step, df, noise))/(2*step)
        return value, dr, ds
    # For df=2m+1 the Student characteristic function is exp(-a|w|)
    # times a degree-m polynomial, a=sqrt(df)*scale. Cauchy convolution
    # changes the exponential scale to a+noise. Sum its wrapped Fourier
    # series via rational negative-integer polylogarithms.
    m, h = (int(df)-1)//2, 2*np.pi/period
    a = math.sqrt(df)*scale
    phase = (r+period/2) % period-period/2
    exponent = -(a+noise)*h+1j*h*phase
    z, denominator = np.exp(exponent), -np.expm1(exponent)
    polylogs = [z/denominator]
    eulerian = [1]
    for n in range(1, m+2):
        if n > 1:
            previous = eulerian
            eulerian = [(k+1)*(previous[k] if k < len(previous) else 0)
                        +(n-k)*(previous[k-1] if k else 0) for k in range(n)]
        polylogs.append(z*np.polynomial.polynomial.polyval(z, eulerian)/denominator**(n+1))
    value = np.zeros_like(z)
    dr, ds = np.zeros_like(z), np.zeros_like(z)
    for j in range(m+1):
        coefficient = (2**j*math.factorial(m)*math.factorial(2*m-j)
                       /(math.factorial(2*m)*math.factorial(m-j)*math.factorial(j)))
        term = coefficient*(a*h)**j
        value += term*polylogs[j]
        dr += term*1j*h*polylogs[j+1]
        ds += term*((j/scale)*polylogs[j]-h*math.sqrt(df)*polylogs[j+1])
    pdf = (1+2*value.real)/period
    if np.any(pdf <= 0) or not np.all(np.isfinite(pdf)):
        raise ArithmeticError('nonpositive or nonfinite convolution density')
    return pdf, 2*dr.real/period, 2*ds.real/period
