import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TleInterface } from "./TleView";
import type { TleArchiveListV1 } from "./sky-contracts";

const archive: TleArchiveListV1 = {
  schema_version: 1,
  archive_root: "/var/lib/leo/tle",
  returned_count: 2,
  source_count: 2,
  truncated: false,
  snapshots: [
    {
      schema_version: 1,
      provider: "space-track",
      source_label: "Space-Track",
      source_url: "https://www.space-track.org/",
      collected_utc: "2026-08-23T15:04:46Z",
      collected_utc_ns: 1_787_497_486_000_000_000,
      digest: `sha256:${"a".repeat(64)}`,
      byte_size: 1_752_784,
      satellite_count: 8_842,
    },
    {
      schema_version: 1,
      provider: "huggingface",
      source_label: "Hugging Face · juliensimon/starlink-tle-latest",
      source_url: "https://huggingface.co/datasets/juliensimon/starlink-tle-latest",
      collected_utc: "2026-08-23T09:03:13Z",
      collected_utc_ns: 1_787_475_793_000_000_000,
      digest: `sha256:${"b".repeat(64)}`,
      byte_size: 1_804_992,
      satellite_count: 9_104,
    },
  ],
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(archive), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("TLE archive", () => {
  it("lists every local snapshot with update time, coverage and source", async () => {
    render(<TleInterface />);

    const table = await screen.findByLabelText("Local TLE snapshots");
    const rows = table.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("2026-08-23 15:04:46 UTC");
    expect(rows[0]).toHaveTextContent("8,842");
    expect(rows[0]).toHaveTextContent("Space-Track");
    expect(rows[1]).toHaveTextContent("9,104");
    expect(screen.getByLabelText("TLE archive summary")).toHaveTextContent("2 snapshots on disk");
    expect(screen.getByRole("link", { name: /juliensimon\/starlink-tle-latest/ })).toHaveAttribute(
      "href",
      "https://huggingface.co/datasets/juliensimon/starlink-tle-latest",
    );
  });

  it("reports archive unavailability instead of rendering an empty table", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "no TLE snapshot is available" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        })),
    );
    render(<TleInterface />);

    await waitFor(() =>
      expect(screen.getByText("no TLE snapshot is available")).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText("Local TLE snapshots")).not.toBeInTheDocument();
  });
});
