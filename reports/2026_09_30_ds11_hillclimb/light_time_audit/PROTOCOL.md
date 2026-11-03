# Classical geometric signal travel-time audit

At the original IID locations/timing for scans 0 and 16, quantify reception-
versus transmission-epoch geometric Doppler using all retained candidates.
No fitting or reference location is used. Reuse verified original state banks.
Interpolate position and velocity exactly as the baseline; estimate local
acceleration from the surrounding timing-grid velocities. Locally approximate
emission position quadratically and velocity linearly over the light time.
Iterate range/c six times and rotate emission ECEF into reception ECEF.
Differentiate the implicit range equation, including the light-time derivative.
Report absolute correction and its training-mean-centered shape, both for all
candidate/track rows and for each training-selected original MAP candidate.

This is a classical geometric approximation, not a complete relativistic,
atmospheric or satellite-clock model. It does not validate absolute states.
Synthetic radial and rotating-frame finite-range derivative tests are required.
Source convention: ESA Navipedia, Satellite Coordinates Computation,
https://gssc.esa.int/navipedia/index.php/Satellite_Coordinates_Computation
The range-rate formula is derived by differentiating that retarded geometry.
No geographic advancement gate is inferred from correction size alone.
