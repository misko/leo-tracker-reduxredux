# Preparation: geometry limits of receiver contrast correction

Four pure NumPy synthetic tests pass under production Python3.14.4. No recording
or orbit data, optimizer, or receiver reference coordinates are used. This is
mathematical qualification for a possible later experiment, not a position result.

For equal-precision pairs with identical common-position derivatives, an
antisymmetric receiver correction leaves the spatial gradient unchanged. The
tests verify the common/differential residual decomposition, then demonstrate
three limits: unequal receiver support, unequal precision, and different
receiver geometry. With unequal support, the same mechanism lets a correct
injected correction remove a spurious gradient and a wrong correction create one.

These identities assume known assignments and unwrapped Gaussian residuals.
They do not prove invariance for B7's clutter/association mixture or for changing
clock/timing parameters. A frequency-fit improvement alone is not a position gain.

The prospective position experiment remains conditional on the completed
[iteration90 diagnostic](../2026_10_09_position_error_iter90/README.md). No
recording experiment is frozen or launched by this preparation. B7 remains the
deployed policy, and reserve outcomes remain closed.
