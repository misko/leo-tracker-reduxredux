import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SkyInterface } from "./SkyView";
import type {
  GlobeFrameSetV1,
  SkySiteListV1,
  SkySnapshotListV1,
  SkyViewFrameSetV1,
  SkyViewObjectDetailV1,
  SkyViewTleComparisonV1,
} from "./sky-contracts";

const ANCHOR_NS = 1_787_238_197_000_000_000;
const KNOTS = [
  ANCHOR_NS - 60_000_000_000,
  ANCHOR_NS - 30_000_000_000,
  ANCHOR_NS,
  ANCHOR_NS + 30_000_000_000,
  ANCHOR_NS + 60_000_000_000,
];

const sites: SkySiteListV1 = {
  schema_version: 1,
  sites: [
    {
      schema_version: 1,
      name: "spinnaker-sausalito",
      label: "Spinnaker, Sausalito",
      latitude_deg: 37.858988,
      longitude_deg: -122.478103,
      altitude_m: -29,
      position_uncertainty_m: 50,
      provenance: "OpenStreetMap named node",
    },
  ],
};

const snapshots: SkySnapshotListV1 = {
  schema_version: 1,
  archive_root: "/var/lib/leo/tle",
  returned_count: 1,
  source_count: 1,
  truncated: false,
  snapshots: [
    {
      schema_version: 1,
      provider: "space-track",
      collected_utc: "2026-08-20T15:03:17Z",
      collected_utc_ns: ANCHOR_NS,
      digest: `sha256:${"a".repeat(64)}`,
      byte_size: 1_749_739,
    },
  ],
};

const globe: GlobeFrameSetV1 = {
  schema_version: 1,
  window: { schema_version: 1, anchor_utc_ns: ANCHOR_NS, half_width_s: 60, sample_count: 5 },
  knot_utc_ns: KNOTS,
  quantum_km: 8000 / 32767,
  earth_radius_km: 6378.137,
  snapshot: {
    schema_version: 1,
    provider: "space-track",
    collected_utc_ns: ANCHOR_NS,
    digest: `sha256:${"a".repeat(64)}`,
    object_count: 4,
  },
  tracks: [0, 1, 2].map((index) => ({
    schema_version: 1 as const,
    catalog_number: 40_000 + index,
    object_name: `STARLINK-${index}`,
    positions: KNOTS.flatMap((_, knot) => [28_000 + knot, 1_000 * index, 500 * knot]),
  })),
  returned_object_count: 3,
  source_object_count: 4,
  truncated: true,
};

const dome: SkyViewFrameSetV1 = {
  schema_version: 1,
  observer: {
    schema_version: 1,
    latitude_deg: 37.858988,
    longitude_deg: -122.478103,
    altitude_m: -29,
    label: "Spinnaker, Sausalito",
  },
  window: { schema_version: 1, anchor_utc_ns: ANCHOR_NS, half_width_s: 60, sample_count: 5 },
  knot_utc_ns: KNOTS,
  horizon_mask_deg: 10,
  snapshot: globe.snapshot,
  tracks: [
    {
      schema_version: 1,
      catalog_number: 44_714,
      object_name: "STARLINK-HIGH",
      azimuth_deg: [350, 355, 0, 5, 10],
      elevation_deg: [40, 60, 80, 60, 40],
      range_km: [900, 700, 550, 700, 900],
      peak_elevation_deg: 80,
      predicted_doppler_rates: [
        { schema_version: 1, starlink_channel: 1, center_frequency_hz: 10_825_000_000, average_rate_hz_s: -5_100.25 },
        { schema_version: 1, starlink_channel: 8, center_frequency_hz: 12_575_000_000, average_rate_hz_s: -5_924.308 },
      ],
    },
    {
      schema_version: 1,
      catalog_number: 44_715,
      object_name: "STARLINK-LOW",
      azimuth_deg: [100, 105, 110, 115, 120],
      elevation_deg: [12, 13, 14, 13, 12],
      range_km: [1800, 1750, 1700, 1750, 1800],
      peak_elevation_deg: 14,
      predicted_doppler_rates: [
        { schema_version: 1, starlink_channel: 1, center_frequency_hz: 10_825_000_000, average_rate_hz_s: 850.25 },
        { schema_version: 1, starlink_channel: 8, center_frequency_hz: 12_575_000_000, average_rate_hz_s: 987.702 },
      ],
    },
  ],
  returned_object_count: 2,
  source_object_count: 2,
  truncated: false,
};

const objectDetail: SkyViewObjectDetailV1 = {
  schema_version: 1,
  observer: dome.observer,
  window: dome.window,
  knot_utc_ns: KNOTS,
  snapshot: globe.snapshot,
  catalog_number: 44_714,
  object_name: "STARLINK-HIGH",
  orbit: {
    schema_version: 1,
    element_epoch_utc_ns: ANCHOR_NS - 3_600_000_000_000,
    inclination_deg: 53.05,
    right_ascension_deg: 210.1,
    eccentricity: 0.00012,
    argument_of_perigee_deg: 74.2,
    mean_anomaly_deg: 285.8,
    mean_motion_rev_day: 15.06,
    period_minutes: 95.62,
    perigee_altitude_km: 541,
    apogee_altitude_km: 543,
  },
  downlink_frequency_hz: 11.7e9,
  range_rate_km_s: [-5, -3, 0, 3, 5],
  doppler_shift_hz: [195_000, 117_000, 0, -117_000, -195_000],
};

const tleComparison: SkyViewTleComparisonV1 = {
  schema_version: 1,
  observer: dome.observer,
  anchor_utc_ns: ANCHOR_NS,
  catalog_number: 44_714,
  object_name: "STARLINK-HIGH",
  view_snapshot: globe.snapshot,
  view_element_digest: `sha256:${"c".repeat(64)}`,
  view_element_epoch_utc_ns: ANCHOR_NS - 3_600_000_000_000,
  archive_snapshot_count: 9,
  searched_snapshot_count: 9,
  search_truncated: false,
  entries: [
    {
      schema_version: 1,
      provider: "space-track",
      source_label: "Space-Track",
      collected_utc_ns: ANCHOR_NS + 3_600_000_000_000,
      snapshot_digest: `sha256:${"d".repeat(64)}`,
      element_digest: `sha256:${"e".repeat(64)}`,
      element_epoch_utc_ns: ANCHOR_NS,
      is_view_element: false,
      position_ecef_km: [1_000, 2_000, 6_500],
      azimuth_deg: 1.234,
      elevation_deg: 79.876,
      range_km: 551.25,
      position_difference_km: 1.245,
      look_angle_difference_deg: 0.0123,
      range_difference_km: 1.25,
    },
    {
      schema_version: 1,
      provider: "huggingface",
      source_label: "Hugging Face · juliensimon/starlink-tle-latest",
      collected_utc_ns: ANCHOR_NS,
      snapshot_digest: globe.snapshot.digest,
      element_digest: `sha256:${"c".repeat(64)}`,
      element_epoch_utc_ns: ANCHOR_NS - 3_600_000_000_000,
      is_view_element: true,
      position_ecef_km: [999, 2_000, 6_500],
      azimuth_deg: 1.2,
      elevation_deg: 80,
      range_km: 550,
      position_difference_km: 0,
      look_angle_difference_deg: 0,
      range_difference_km: 0,
    },
  ],
};

function stubFetch(overrides: Partial<Record<string, unknown>> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const pick = (key: string, fallback: unknown) =>
        key in overrides ? overrides[key] : fallback;
      const body =
        url.includes("/sky/sites") ? pick("sites", sites)
        : url.includes("/sky/snapshots") ? pick("snapshots", snapshots)
        : url.includes("/sky/globe") ? pick("globe", globe)
        : url.includes("/sky/skyview/object/tle-comparison") ? pick("comparison", tleComparison)
        : url.includes("/sky/skyview/object") ? pick("object", objectDetail)
        : url.includes("/sky/skyview") ? pick("skyview", dome)
        : null;
      if (body === "unavailable") {
        return new Response(JSON.stringify({ detail: "no TLE snapshot is available" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

beforeEach(() => {
  // jsdom has no WebGL; the globe scene declines to build and the panel falls
  // back to its readout, which is what these tests assert against.
  stubFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Sky interface", () => {
  it("shows the element-set provenance rather than presenting the sky anonymously", async () => {
    render(<SkyInterface />);
    await waitFor(() =>
      expect(screen.getByLabelText("Element set provenance")).toHaveTextContent("space-track"),
    );
    expect(screen.getByLabelText("Element set provenance")).toHaveTextContent("2026-08-20");
  });

  it("reports how many objects are drawn and that the rest are not", async () => {
    render(<SkyInterface />);
    await waitFor(() =>
      expect(screen.getByLabelText("Rendered object count")).toHaveTextContent("3 objects"),
    );
    expect(screen.getByText(/the rest are not drawn/)).toBeInTheDocument();
  });

  it("states that the view is predicted, not observed", async () => {
    render(<SkyInterface />);
    await waitFor(() =>
      expect(
        screen.getAllByText(/Not a detection, attribution or identification/).length,
      ).toBeGreaterThan(0),
    );
  });

  it("centres a 120 second slider on the anchor and moves the displayed instant", async () => {
    render(<SkyInterface />);
    const slider = screen.getByLabelText("Time offset in seconds") as HTMLInputElement;
    expect(slider.min).toBe("-60");
    expect(slider.max).toBe("60");
    expect(slider.value).toBe("0");

    const before = screen.getByLabelText("Displayed instant").textContent;
    fireEvent.change(slider, { target: { value: "60" } });
    const after = screen.getByLabelText("Displayed instant").textContent;
    expect(after).not.toEqual(before);
  });

  it("refuses an unparsable anchor instead of silently keeping the old one", async () => {
    render(<SkyInterface />);
    const input = screen.getByLabelText("Anchor instant");
    fireEvent.change(input, { target: { value: "yesterday" } });
    fireEvent.blur(input);
    expect(await screen.findByText(/UTC instant such as/)).toBeInTheDocument();
  });

  it("requires a position before it will look up from one", async () => {
    render(<SkyInterface />);
    expect(screen.getByRole("button", { name: "Ground to sky" })).toBeDisabled();
  });

  it("rejects an out of range latitude", async () => {
    render(<SkyInterface />);
    fireEvent.change(screen.getByLabelText("Observer latitude"), { target: { value: "91" } });
    fireEvent.change(screen.getByLabelText("Observer longitude"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up from here" }));
    expect(await screen.findByText(/Latitude must be between/)).toBeInTheDocument();
  });

  it("switches to the sky view for a chosen reviewed site", async () => {
    render(<SkyInterface />);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    await waitFor(() => expect(screen.getByLabelText("All-sky chart")).toBeInTheDocument());
    expect(screen.getByLabelText("Observer position")).toHaveTextContent("Spinnaker, Sausalito");
  });

  it("clamps to the sampled window rather than extrapolating past it", async () => {
    render(<SkyInterface />);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    // The component's default anchor is now, far outside the fixture window,
    // so every track resolves to its terminal knot instead of an extrapolation.
    const table = await screen.findByLabelText("Visible objects");
    const elevations = [...table.querySelectorAll("tbody tr td:nth-child(3)")].map(
      (cell) => Number.parseFloat(cell.textContent ?? ""),
    );
    expect(elevations[0]).toBeCloseTo(40, 1);
  });

  it("draws only objects above the mask and lists them highest first", async () => {
    render(<SkyInterface />);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    const table = await screen.findByLabelText("Visible objects");
    const names = [...table.querySelectorAll("tbody tr td:first-child")].map((cell) => cell.textContent);
    expect(names).toEqual(["STARLINK-HIGH", "STARLINK-LOW"]);
    expect(screen.getByLabelText("Visible object count")).toHaveTextContent("2 above 10°");
  });

  it("lists full-window predicted Doppler rates at the CH1 and CH8 centers", async () => {
    render(<SkyInterface />);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    const table = await screen.findByLabelText("Visible objects");
    expect(table).toHaveTextContent("CH1 center · 10.825 GHz");
    expect(table).toHaveTextContent("CH8 center · 12.575 GHz");
    const firstRow = table.querySelector("tbody tr");
    expect(firstRow).toHaveTextContent("−5,100.3 Hz/s");
    expect(firstRow).toHaveTextContent("−5,924.3 Hz/s");
  });

  it("puts the zenith at the centre of the chart", async () => {
    render(<SkyInterface />);
    // The fixture's knots are centred on this instant; without setting it the
    // display time falls outside the window and correctly clamps to an end knot.
    const anchorInput = screen.getByLabelText("Anchor instant");
    fireEvent.change(anchorInput, { target: { value: "2026-08-20T15:03:17Z" } });
    fireEvent.blur(anchorInput);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    const chart = await screen.findByLabelText("All-sky chart");
    const marks = [...chart.querySelectorAll("circle.dome-object")];
    expect(marks).toHaveLength(2);
    // STARLINK-HIGH is at 80 degrees elevation at the anchor, so it sits near
    // the centre; 1 - 80/90 is about 0.11.
    const radii = marks.map((mark) =>
      Math.hypot(Number(mark.getAttribute("cx")), Number(mark.getAttribute("cy"))),
    );
    expect(Math.min(...radii)).toBeLessThan(0.2);
  });

  it("draws full-window trajectories and shows orbit and Doppler after selection", async () => {
    render(<SkyInterface />);
    const anchorInput = screen.getByLabelText("Anchor instant");
    fireEvent.change(anchorInput, { target: { value: "2026-08-20T15:03:17Z" } });
    fireEvent.blur(anchorInput);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    const chart = await screen.findByLabelText("All-sky chart");
    expect(chart.querySelectorAll("path.dome-trajectory").length).toBeGreaterThan(0);

    fireEvent.click(await screen.findByRole("button", { name: "Select STARLINK-HIGH" }));
    const details = await screen.findByLabelText("Selected satellite details");
    expect(details).toHaveTextContent("NORAD 44714");
    expect(details).toHaveTextContent("95.62 min");
    expect(screen.getByLabelText("Expected Doppler over 120 seconds")).toBeInTheDocument();
    expect(screen.getByLabelText("Current expected Doppler")).toHaveTextContent("11.700 GHz");
  });

  it("compares the latest unique TLE entries with the record used by the view", async () => {
    render(<SkyInterface />);
    const anchorInput = screen.getByLabelText("Anchor instant");
    fireEvent.change(anchorInput, { target: { value: "2026-08-20T15:03:17Z" } });
    fireEvent.blur(anchorInput);
    await waitFor(() => expect(screen.getByLabelText("Reviewed observer site")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Reviewed observer site"), {
      target: { value: "spinnaker-sausalito" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Select STARLINK-HIGH" }));

    const comparison = await screen.findByLabelText("Satellite TLE position comparison");
    expect(comparison).toHaveTextContent("Latest TLE records for STARLINK-HIGH");
    const table = screen.getByLabelText("Latest satellite TLE entries");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(table).toHaveTextContent("Used by view");
    expect(table).toHaveTextContent("1.245 km");
    expect(table).toHaveTextContent("0.0123°");
    expect(comparison).toHaveTextContent("Duplicate element sets from repeated downloads are shown once");
  });

  it("reports an unavailable archive rather than an empty sky", async () => {
    stubFetch({ globe: "unavailable" });
    render(<SkyInterface />);
    expect(await screen.findByText(/no TLE snapshot is available/)).toBeInTheDocument();
  });

  it("says so when no snapshot has been collected", async () => {
    stubFetch({ snapshots: { ...snapshots, snapshots: [], returned_count: 0, source_count: 0 } });
    render(<SkyInterface />);
    expect(
      await screen.findByText(/No element-set snapshot is available/),
    ).toBeInTheDocument();
  });
});

describe("Sky provenance", () => {
  it("names the snapshot the view used, not the newest in the archive", async () => {
    // The archive holds a newer snapshot than the one the globe resolved for
    // the selected anchor; the panel must attribute what is drawn to the one
    // actually used.
    stubFetch({
      snapshots: {
        ...snapshots,
        returned_count: 2,
        source_count: 2,
        snapshots: [
          snapshots.snapshots[0],
          {
            schema_version: 1 as const,
            provider: "huggingface" as const,
            collected_utc: "2026-08-21T09:00:00Z",
            collected_utc_ns: ANCHOR_NS + 80_000_000_000_000,
            digest: `sha256:${"b".repeat(64)}`,
            byte_size: 1_805_664,
          },
        ],
      },
    });
    render(<SkyInterface />);
    const provenance = await screen.findByLabelText("Element set provenance");
    // globe.snapshot is the space-track one; the newer huggingface entry must
    // not be presented as the source of the geometry.
    expect(provenance).toHaveTextContent("space-track");
    expect(provenance).not.toHaveTextContent("huggingface");
    expect(provenance).toHaveTextContent("aaaaaaaaaaaaaaa");
  });

  it("reports the object count of the snapshot it drew from", async () => {
    render(<SkyInterface />);
    const provenance = await screen.findByLabelText("Element set provenance");
    expect(provenance).toHaveTextContent("4 satellite records");
  });
});
