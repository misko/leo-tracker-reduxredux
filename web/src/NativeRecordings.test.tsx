import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NativeRecordings } from "./NativeRecordings";
import type { NativeRecordingDetail, NativeRecordingSummary } from "./nativeRecordingsApi";

const summary: NativeRecordingSummary = {
  bundle_id: "a".repeat(64), serial: "winbond-db620818a328172c", boot_id: "boot-a",
  fit_sha256: "b".repeat(64), visit: 123, epoch: 7, episode_index: 0,
  runtime_result: -5, owner_status: "acquisition_not_qualified", source_rate_hz: 60000000,
  pilot_samples: 79200, head_count: 201, supported_count: 200, rejected_count: 1,
  observed_start_span_s: 0.267, supported_cfo_min_hz: 120, supported_cfo_max_hz: 125,
  frequency_reference: "receiver_relative_uncalibrated",
  evidence_mode: "retrospective_retained_owner_correspondence", acquisition_verified: false,
  original_native_iq_verified: false, physical_precision_qualified: false,
};

function detail(): NativeRecordingDetail {
  return { schema_version: 1, summary, cursor: 0, next_cursor: 200, rows: [
    { measurement: { sequence: 1, frame: 0, native_start_sample: "9007199254740993",
      delay_s: 1e-9, cfo_hz: 120, coherence: .9, supported: true, rejection: 0, hardware_fault: 0 },
      coarse_relative_scheduled_start_s: .125, coarse_relative_refined_start_s: .125000001 },
    { measurement: { sequence: 2, frame: 1, native_start_sample: "9007199254820993",
      delay_s: 4e-9, cfo_hz: 99999, coherence: .1, supported: false, rejection: 4, hardware_fault: 0 },
      coarse_relative_scheduled_start_s: .126333333, coarse_relative_refined_start_s: .126333337 },
  ] };
}

function serve(resolver?: (url: string) => Response | Promise<Response>) {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (resolver) return resolver(url);
    return Response.json(url.includes(`/${summary.bundle_id}?`)
      ? detail() : { schema_version: 1, total: 1, next_cursor: null,
        items: [{ bundle_id: summary.bundle_id, summary, error: null }] });
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

afterEach(() => vi.unstubAllGlobals());

describe("native recording review", () => {
  it("preserves failed outcomes, exact counters and rejected fits without plotting them", async () => {
    serve();
    render(<NativeRecordings />);
    fireEvent.click(await screen.findByRole("button", { name: /Visit 123/ }));
    const table = await screen.findByRole("table", { name: "Native measurements" });
    expect(within(table).getByText("9007199254740993")).toBeInTheDocument();
    expect(within(table).getByText("99999.00")).toBeInTheDocument();
    expect(within(table).getByText("Rejected (mask 4, fault 0)")).toBeInTheDocument();
    expect(screen.getByText(/Run outcome: acquisition not qualified/)).toBeInTheDocument();
    expect(screen.getByText(/have not qualified physical precision/)).toBeInTheDocument();
    const plot = screen.getByRole("img", { name: /Supported CFO versus time/ });
    expect(plot.querySelectorAll("circle")).toHaveLength(1);
    expect(plot.textContent).not.toContain("99999");
    expect(plot.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it("clears measurements when a refreshed recording fails integrity", async () => {
    const fetcher = serve();
    render(<NativeRecordings />);
    fireEvent.click(await screen.findByRole("button", { name: /Visit 123/ }));
    await screen.findByRole("table");
    fetcher.mockImplementation(async () => new Response("", { status: 409 }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh recordings" }));
    await waitFor(() => expect(screen.queryByRole("table")).not.toBeInTheDocument());
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("integrity check failed");
  });

  it("fetches the next measurement page and excludes stale responses", async () => {
    let resolvePage: (response: Response) => void = () => {};
    const fetcher = serve((url) => {
      if (url.includes("cursor=200")) return new Promise((resolve) => { resolvePage = resolve; });
      if (url.includes(`/${summary.bundle_id}?`)) return Response.json(detail());
      return Response.json({ schema_version: 1, total: 1, next_cursor: null,
        items: [{ bundle_id: summary.bundle_id, summary, error: null }] });
    });
    render(<NativeRecordings />);
    fireEvent.click(await screen.findByRole("button", { name: /Visit 123/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Next measurements" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining("cursor=200"), expect.objectContaining({ method: "GET" }),
    ));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    resolvePage(Response.json({ ...detail(), cursor: 200, next_cursor: null, rows: [] }));
    expect(await screen.findByText("No supported CFO measurements on this page.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next measurements" })).toBeDisabled();
  });

  it("distinguishes empty registrations from damaged recordings", async () => {
    const fetcher = serve(() => Response.json({ schema_version: 1, total: 0, next_cursor: null, items: [] }));
    render(<NativeRecordings />);
    expect(await screen.findByText("No native recordings have been registered.")).toBeInTheDocument();
    fetcher.mockImplementation(async () => Response.json({ schema_version: 1, total: 1, next_cursor: null,
      items: [{ bundle_id: summary.bundle_id, summary: null, error: "integrity_unavailable" }] }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh recordings" }));
    expect(await screen.findByText(/Recording aaaaaaaaaaaa: integrity unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Visit/ })).not.toBeInTheDocument();
  });
});
