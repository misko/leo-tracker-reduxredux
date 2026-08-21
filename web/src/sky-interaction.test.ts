import { describe, expect, it } from "vitest";
import { rotateGlobe } from "./sky-interaction";

describe("rotateGlobe", () => {
  it("rotates around both axes from a pointer drag", () => {
    expect(rotateGlobe({ x: 0.15, y: 0 }, 100, -50)).toEqual({ x: -0.15, y: 0.6 });
  });

  it("keeps vertical rotation away from an upside-down camera", () => {
    expect(rotateGlobe({ x: 0, y: 0 }, 0, 10_000).x).toBe(Math.PI / 2);
    expect(rotateGlobe({ x: 0, y: 0 }, 0, -10_000).x).toBe(-Math.PI / 2);
  });
});
