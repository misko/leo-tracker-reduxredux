export interface GlobeRotation {
  x: number;
  y: number;
}

/** Convert a pointer drag into a bounded two-axis globe rotation. */
export function rotateGlobe(
  rotation: GlobeRotation,
  deltaX: number,
  deltaY: number,
  sensitivity = 0.006,
): GlobeRotation {
  return {
    x: Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotation.x + deltaY * sensitivity)),
    y: rotation.y + deltaX * sensitivity,
  };
}
