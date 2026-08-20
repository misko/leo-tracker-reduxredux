// Interpolation between the sparse knots the server ships.
//
// The server propagates; the browser only fills in between. Keeping this pure
// and free of any WebGL reference is deliberate, because it is the part with
// arithmetic in it and therefore the part worth testing directly.

/** Position of one knot triple, in the units the frame set declares. */
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/**
 * Locate `t` within ascending `knots`.
 *
 * Returns the index of the knot at or before `t`, clamped so that callers
 * always receive a usable segment, together with the fraction along it.
 */
export function locateSegment(
  knots: readonly number[],
  t: number,
): { index: number; fraction: number } {
  if (knots.length < 2) throw new Error("interpolation needs at least two knots");
  if (t <= knots[0]) return { index: 0, fraction: 0 };
  const last = knots.length - 1;
  if (t >= knots[last]) return { index: last - 1, fraction: 1 };
  let low = 0;
  let high = last;
  while (high - low > 1) {
    const middle = (low + high) >> 1;
    if (knots[middle] <= t) low = middle;
    else high = middle;
  }
  const span = knots[low + 1] - knots[low];
  return { index: low, fraction: span === 0 ? 0 : (t - knots[low]) / span };
}

function component(positions: readonly number[], knot: number, axis: number): number {
  return positions[knot * 3 + axis];
}

/**
 * Catmull-Rom interpolation of a flattened xyz track at time `t`.
 *
 * A satellite arc over a two-minute window is very nearly cubic, so a spline
 * through the knots reconstructs it far better than straight segments, which
 * visibly corner at each knot. End segments duplicate the terminal knot, which
 * is the standard clamped form and keeps the curve inside the sampled span.
 *
 * `scale` converts the integer counts the contract carries into kilometres.
 */
export function interpolateTrack(
  positions: readonly number[],
  knots: readonly number[],
  t: number,
  scale = 1,
): Vec3 {
  const knotCount = knots.length;
  if (positions.length !== knotCount * 3) {
    throw new Error("track does not cover exactly the declared knots");
  }
  const { index, fraction } = locateSegment(knots, t);
  const p0 = Math.max(index - 1, 0);
  const p1 = index;
  const p2 = Math.min(index + 1, knotCount - 1);
  const p3 = Math.min(index + 2, knotCount - 1);

  const axis = (a: number): number => {
    const v0 = component(positions, p0, a);
    const v1 = component(positions, p1, a);
    const v2 = component(positions, p2, a);
    const v3 = component(positions, p3, a);
    const t2 = fraction * fraction;
    const t3 = t2 * fraction;
    return (
      0.5 *
      (2 * v1 +
        (-v0 + v2) * fraction +
        (2 * v0 - 5 * v1 + 4 * v2 - v3) * t2 +
        (-v0 + 3 * v1 - 3 * v2 + v3) * t3)
    );
  };

  return { x: axis(0) * scale, y: axis(1) * scale, z: axis(2) * scale };
}

/** Interpolate a scalar series, used for azimuth-free values like elevation. */
export function interpolateSeries(
  values: readonly number[],
  knots: readonly number[],
  t: number,
): number {
  const { index, fraction } = locateSegment(knots, t);
  return values[index] + (values[index + 1] - values[index]) * fraction;
}

/**
 * Interpolate an azimuth series across the north wrap.
 *
 * Azimuths are cyclic, so a track passing north steps 359 -> 1 and a linear
 * blend would sweep the long way round the compass. Each step is reduced into
 * (-180, 180] before it is applied.
 */
export function interpolateAzimuth(
  values: readonly number[],
  knots: readonly number[],
  t: number,
): number {
  const { index, fraction } = locateSegment(knots, t);
  const start = values[index];
  let delta = values[index + 1] - start;
  while (delta > 180) delta -= 360;
  while (delta <= -180) delta += 360;
  const raw = start + delta * fraction;
  return ((raw % 360) + 360) % 360;
}

/**
 * Project azimuth and elevation onto a unit dome disc.
 *
 * The horizon is the unit circle and the zenith is the origin, which is the
 * usual all-sky convention: north is up the screen and east is to the right,
 * so the chart reads the way a person facing north and looking up would see it.
 */
export function domeProjection(
  azimuthDeg: number,
  elevationDeg: number,
): { x: number; y: number } {
  const radius = Math.max(0, Math.min(1, 1 - elevationDeg / 90));
  const angle = (azimuthDeg * Math.PI) / 180;
  return { x: radius * Math.sin(angle), y: radius * Math.cos(angle) };
}
