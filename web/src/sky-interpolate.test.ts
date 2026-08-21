import { describe, expect, it } from "vitest";
import {
  domeProjection,
  interpolateAzimuth,
  interpolateSeries,
  interpolateTrack,
  locateSegment,
} from "./sky-interpolate";

const KNOTS = [0, 30, 60, 90, 120];

describe("locateSegment", () => {
  it("clamps outside the sampled span rather than extrapolating", () => {
    expect(locateSegment(KNOTS, -50)).toEqual({ index: 0, fraction: 0 });
    expect(locateSegment(KNOTS, 500)).toEqual({ index: 3, fraction: 1 });
  });

  it("finds the containing segment and the fraction along it", () => {
    expect(locateSegment(KNOTS, 45)).toEqual({ index: 1, fraction: 0.5 });
    expect(locateSegment(KNOTS, 60)).toEqual({ index: 2, fraction: 0 });
  });

  it("refuses a span it cannot interpolate", () => {
    expect(() => locateSegment([5], 5)).toThrow(/at least two knots/);
  });
});

describe("interpolateTrack", () => {
  it("passes exactly through every knot", () => {
    const positions = [0, 0, 0, 1, 2, 3, 2, 4, 6, 3, 6, 9, 4, 8, 12];
    KNOTS.forEach((knot, index) => {
      const point = interpolateTrack(positions, KNOTS, knot);
      expect(point.x).toBeCloseTo(positions[index * 3], 9);
      expect(point.y).toBeCloseTo(positions[index * 3 + 1], 9);
      expect(point.z).toBeCloseTo(positions[index * 3 + 2], 9);
    });
  });

  it("reproduces a straight line exactly between knots", () => {
    const positions = [0, 0, 0, 1, 2, 3, 2, 4, 6, 3, 6, 9, 4, 8, 12];
    const middle = interpolateTrack(positions, KNOTS, 45);
    expect(middle.x).toBeCloseTo(1.5, 9);
    expect(middle.y).toBeCloseTo(3, 9);
    expect(middle.z).toBeCloseTo(4.5, 9);
  });

  it("follows a curve more closely than straight segments do", () => {
    // A quarter circle sampled at the knots; the chord midpoint falls short of
    // the arc, and the spline should sit closer to the true radius.
    const radius = 100;
    const positions: number[] = [];
    KNOTS.forEach((knot) => {
      const angle = (knot / 120) * (Math.PI / 2);
      positions.push(radius * Math.cos(angle), radius * Math.sin(angle), 0);
    });
    const t = 45;
    const spline = interpolateTrack(positions, KNOTS, t);
    const a = { x: positions[3], y: positions[4] };
    const b = { x: positions[6], y: positions[7] };
    const chord = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };

    const splineError = Math.abs(Math.hypot(spline.x, spline.y) - radius);
    const chordError = Math.abs(Math.hypot(chord.x, chord.y) - radius);
    expect(splineError).toBeLessThan(chordError);
  });

  it("applies the quantisation scale", () => {
    const positions = [10, 20, 30, 10, 20, 30, 10, 20, 30];
    const point = interpolateTrack(positions, [0, 1, 2], 1, 0.25);
    expect(point.x).toBeCloseTo(2.5, 9);
    expect(point.y).toBeCloseTo(5, 9);
    expect(point.z).toBeCloseTo(7.5, 9);
  });

  it("rejects a track that does not cover the declared knots", () => {
    expect(() => interpolateTrack([1, 2, 3], KNOTS, 0)).toThrow(/declared knots/);
  });
});

describe("interpolateAzimuth", () => {
  it("crosses north the short way", () => {
    // 359 -> 1 is two degrees east, not 358 degrees west.
    const midpoint = interpolateAzimuth([359, 1], [0, 10], 5);
    expect(midpoint).toBeCloseTo(0, 6);
  });

  it("crosses north the short way in the other direction", () => {
    expect(interpolateAzimuth([1, 359], [0, 10], 5)).toBeCloseTo(0, 6);
  });

  it("always returns a compass bearing", () => {
    for (const t of [0, 2.5, 5, 7.5, 10]) {
      const value = interpolateAzimuth([350, 20], [0, 10], t);
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(360);
    }
  });

  it("interpolates an ordinary span linearly", () => {
    expect(interpolateAzimuth([90, 100], [0, 10], 5)).toBeCloseTo(95, 9);
  });
});

describe("interpolateSeries", () => {
  it("blends linearly between knots", () => {
    expect(interpolateSeries([10, 20, 30], [0, 10, 20], 5)).toBeCloseTo(15, 9);
    expect(interpolateSeries([10, 20, 30], [0, 10, 20], 20)).toBeCloseTo(30, 9);
  });
});

describe("domeProjection", () => {
  it("puts the zenith at the centre and the horizon on the unit circle", () => {
    const zenith = domeProjection(123, 90);
    expect(Math.hypot(zenith.x, zenith.y)).toBeCloseTo(0, 9);
    expect(Math.hypot(...Object.values(domeProjection(0, 0)))).toBeCloseTo(1, 9);
  });

  it("places north up and east to the right", () => {
    const north = domeProjection(0, 0);
    expect(north.x).toBeCloseTo(0, 9);
    expect(north.y).toBeCloseTo(1, 9);

    const east = domeProjection(90, 0);
    expect(east.x).toBeCloseTo(1, 9);
    expect(east.y).toBeCloseTo(0, 9);

    const south = domeProjection(180, 0);
    expect(south.y).toBeCloseTo(-1, 9);
  });

  it("clamps below the horizon rather than escaping the disc", () => {
    const below = domeProjection(45, -30);
    expect(Math.hypot(below.x, below.y)).toBeLessThanOrEqual(1 + 1e-9);
  });
});
