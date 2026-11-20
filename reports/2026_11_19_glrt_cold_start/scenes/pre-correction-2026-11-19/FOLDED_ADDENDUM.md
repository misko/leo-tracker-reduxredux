# Prospective folded-Doppler addendum

The two originally declared global receivers had started evaluating
the new synthetic packet when the folded-Doppler release froze.
The packet labels, seed and solver outputs remained unopened.
The two-method scorer was held while the third method was added.

Lock the folded-Doppler Python and C sources to the existing input
seal. Attempt global folded-Doppler inference on all five public
acquisitions with the same 150 s per-case limit and no location prior.
The simulation, input manifest and two existing source locks stay
unchanged. Seal the additional predictions separately, then verify
both seals before scoring the three receivers against the same
coordinates and shuffle label.
