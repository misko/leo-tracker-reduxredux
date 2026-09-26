import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdaptiveHopBrowser, AdaptiveHopDetail } from "./AdaptiveHopPanel";
import { getAdaptiveSession, getAdaptiveSessions } from "./adaptive-api";
import { adaptiveDetailFixture, adaptivePageFixture, hostAdaptiveDetailFixture, multirateAdaptiveDetailFixture } from "./adaptive-fixtures";

const respond = (value: unknown, status = 200) => ({ ok: status === 200, status, json: async () => value }) as Response;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("adaptive actual-visit presentation", () => {
  it("accepts the schema-8 page and schema-9 four-rate adaptive detail", async () => {
    const legacy = adaptiveDetailFixture("four-rate-test", 3);
    const origin = BigInt(legacy.source_origin_counter!);
    const scale = (counter: string) => String(origin + (BigInt(counter) - origin) * 3n);
    const visits = legacy.visits.map(visit => ({
      ...visit,
      proposed_target_index: visit.target_index,
      active_mask: visit.active_mask & 15,
      quiet_mask: visit.quiet_mask & 15,
      valid_start_counter: scale(visit.valid_start_counter),
      valid_end_counter: visit.valid_end_counter === null ? null : scale(visit.valid_end_counter),
      decision_counter: scale(visit.decision_counter),
    }));
    const capture = {
      ...legacy.capture,
      schema_version: 9 as const,
      mode: "adaptive" as const,
      nominal_duration_seconds: 20,
      sample_rate_hz: 7500000 as const,
      bandwidth_hz: 7500000 as const,
      analysis_state: "separate_product" as const,
      radio_serial: "10400056f695001322002d0010ad1719f2",
      selected_edge: "lower" as const,
      allowed_target_mask: 15 as const,
      active_dwell_ms: 120 as const,
      recorded_gain_mode: "manual" as const,
      recorded_manual_gain_db: 40,
    };
    const page = {
      schema_version: 8 as const, kind: "adaptive_hop_history_page" as const,
      cursor: 0, limit: 10, total: 1, next_cursor: null, items: [capture],
    };
    const detail = {
      ...legacy, schema_version: 9 as const, capture, visits,
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(respond(page)).mockResolvedValue(respond(detail)));

    await expect(getAdaptiveSessions(0)).resolves.toEqual(page);
    await expect(getAdaptiveSession("four-rate-test")).resolves.toEqual(detail);
  });

  it("admits only the declared feature-104 schema-7 rates and page major", async () => {
    const legacy = adaptiveDetailFixture("feature104-test", 3);
    const origin = BigInt(legacy.source_origin_counter!);
    const scale = (counter: string) => String(origin + (BigInt(counter) - origin) * 6n);
    const capture = {
      ...legacy.capture, schema_version: 7 as const, sample_rate_hz: 15000000 as const,
      bandwidth_hz: 15000000 as const, analysis_state: "separate_product" as const,
      radio_serial: "10400056f695001322002d0010ad1719f2", selected_edge: "lower" as const,
      allowed_target_mask: 15 as const,
    };
    const detail = {
      ...legacy, schema_version: 7 as const, capture,
      visits: legacy.visits.map(v => ({
        ...v, proposed_target_index: v.target_index, valid_start_counter: scale(v.valid_start_counter),
        valid_end_counter: v.valid_end_counter === null ? null : scale(v.valid_end_counter),
        decision_counter: scale(v.decision_counter),
      })),
    };
    const page = { schema_version: 6, kind: "adaptive_hop_history_page", items: [capture], cursor: 0, limit: 10, total: 1, next_cursor: null };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(respond(page)).mockResolvedValue(respond(detail)));
    await expect(getAdaptiveSessions(0)).resolves.toEqual(page);
    await expect(getAdaptiveSession("feature104-test")).resolves.toEqual(detail);

    Object.assign(capture, { sample_rate_hz: 5000000, bandwidth_hz: 5000000 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(page)));
    await expect(getAdaptiveSessions(0)).rejects.toThrow("capture evidence");
  });
  it("accepts feature-104 retained visits after a transport gap", async () => {
    const legacy = adaptiveDetailFixture("feature104-sparse", 3);
    const origin = BigInt(legacy.source_origin_counter!);
    const scale = (counter: string) => String(origin + (BigInt(counter) - origin) * 6n);
    const visits = legacy.visits.map(v => ({
      ...v,
      proposed_target_index: v.target_index,
      valid_start_counter: scale(v.valid_start_counter),
      valid_end_counter: v.valid_end_counter === null ? null : scale(v.valid_end_counter),
      decision_counter: scale(v.decision_counter),
    }));
    Object.assign(visits[0], { retained: false, valid_end_counter: null, valid_end_seconds: null });
    Object.assign(visits[2], {
      retained: true,
      valid_end_counter: String(BigInt(visits[2].valid_start_counter) + 1_800_000n),
      valid_end_seconds: visits[2].valid_start_seconds + .12,
    });
    const capture = {
      ...legacy.capture,
      schema_version: 7 as const,
      sample_rate_hz: 15000000 as const,
      bandwidth_hz: 15000000 as const,
      analysis_state: "separate_product" as const,
      radio_serial: "10400056f695001322002d0010ad1719f2",
      selected_edge: "lower" as const,
      allowed_target_mask: 15 as const,
      target_coverage: legacy.capture.target_coverage.map(row => ({
        ...row,
        retained_visits: row.target_index === 0 ? 0 : row.target_index === 2 ? 1 : row.retained_visits,
      })),
    };
    const detail = { ...legacy, schema_version: 7 as const, capture, visits };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(detail)));
    await expect(getAdaptiveSession("feature104-sparse")).resolves.toEqual(detail);

    capture.retained_visits = 1;
    capture.target_coverage[2].retained_visits = 0;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(detail)));
    await expect(getAdaptiveSession("feature104-sparse")).rejects.toThrow(
      "retained visit inventory differs",
    );
  });
  it("keeps legacy retained visits prefix-bound", async () => {
    const detail = adaptiveDetailFixture("legacy-sparse", 3);
    Object.assign(detail.visits[0], {
      retained: false,
      valid_end_counter: null,
      valid_end_seconds: null,
    });
    Object.assign(detail.visits[2], {
      retained: true,
      valid_end_counter: String(BigInt(detail.visits[2].valid_start_counter) + 300_000n),
      valid_end_seconds: detail.visits[2].valid_start_seconds + .12,
    });
    detail.capture.target_coverage[0].retained_visits = 0;
    detail.capture.target_coverage[2].retained_visits = 1;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(detail)));
    await expect(getAdaptiveSession("legacy-sparse")).rejects.toThrow(
      "visit evidence is invalid",
    );
  });
  it("admits new dual RX history and preserves zero-gap visit timing", async () => {
    const detail = adaptiveDetailFixture("feature103-test", 3);
    const capture = { ...detail.capture, schema_version: 6, analysis_state: "separate_product", radio_serial: "test", selected_edge: "lower", allowed_target_mask: 15 };
    const value = { ...detail, schema_version: 6, capture,
      visits: detail.visits.map(v => ({ ...v, proposed_target_index: v.target_index, invalid_start_seconds: v.valid_start_seconds })) };
    capture.mode = "adaptive";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    await expect(getAdaptiveSession("feature103-test")).resolves.toEqual(value);
    const page = { schema_version: 5, kind: "adaptive_hop_history_page", items: [capture], cursor: 0, limit: 10, total: 1, next_cursor: null };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(page)));
    await expect(getAdaptiveSessions(0)).resolves.toEqual(page);
  });
  it.each([15000000, 20000000] as const)("validates and shows RX0 at %s S/s", async rate => {
    const detail = multirateAdaptiveDetailFixture(rate);
    expect(detail.host_decisions![0].schema_version).toBe(2);
    expect(detail.host_decisions![0].numerics?.supported_start).toBe(rate === 15000000 ? 34 : 32);
    expect(detail.host_decisions!.map(d => d.visit_index)).toEqual(detail.visits.filter(v => v.retained).map(v => v.visit_index));
    expect(detail.host_decisions!.some((d, i) => d.visit_index !== i)).toBe(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(detail)));
    render(<AdaptiveHopDetail sessionId="adaptive-test" />);
    await screen.findByRole("heading", { name: "Host decisions · RX0" });
    expect(screen.getByText(`${rate / 1e6} MS/s recording · 2.5 MS/s decimated decisions`)).toBeInTheDocument();
    await expect(getAdaptiveSession("adaptive-test")).resolves.toEqual(detail);
  });
  it.each([0, 1] as const)("shows native RX%s and host delivery separately from policy", async receiver => {
    const detail = hostAdaptiveDetailFixture(receiver);
    const fetcher = vi.fn(async (path: string) => path === "/api/v2/scanner/adaptive-sessions/adaptive-test" ? respond(detail) : respond(null, 404));
    vi.stubGlobal("fetch", fetcher);
    render(<AdaptiveHopDetail sessionId="adaptive-test" />);
    await screen.findByRole("heading", { name: `Host decisions · RX${receiver}` });
    expect(screen.getByText("10 MS/s recording · 2.5 MS/s decimated decisions")).toBeInTheDocument();
    expect(screen.queryByText(/both receivers retained/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Selected host decision")).toHaveTextContent("delivery accepted");
    expect(fetcher.mock.calls.some(([path]) => path.endsWith("/glrt"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Next visits" }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect visit 52" }));
    expect(screen.getByLabelText("Selected host decision")).toHaveTextContent("queue_overflow · forwarded verdict unknown · delivery source_ended");
  });

  it.each([
    ["manual", 40, "Manual · 40 dB"],
    ["slow_attack", null, "Slow attack"],
    [null, null, "Unknown"],
  ] as const)("shows persisted %s gain evidence", async (mode, gain, label) => {
    const legacy = adaptiveDetailFixture();
    const visits = legacy.visits.map(visit => ({
      ...visit,
      target_index: visit.target_index % 4,
      proposed_target_index: visit.target_index % 4,
      active_mask: visit.active_mask & 15,
      quiet_mask: visit.quiet_mask & 15,
    }));
    const longVisit = visits.find(visit => visit.retained)!;
    longVisit.valid_end_counter = (
      BigInt(longVisit.valid_start_counter) + BigInt(2500000 * 360 / 1000)
    ).toString();
    longVisit.valid_end_seconds = Number(
      BigInt(longVisit.valid_end_counter) - BigInt(legacy.source_origin_counter!)
    ) / 2500000;
    const coverage = legacy.capture.target_coverage.map(row => {
      const retained = row.target_index < 4
        ? visits.filter(visit => visit.retained && visit.target_index === row.target_index)
        : [];
      return {
        ...row,
        retained_visits: retained.length,
        valid_seconds: retained.reduce(
          (total, visit) => total + visit.valid_end_seconds! - visit.valid_start_seconds,
          0,
        ),
        allocation_ppm: retained.length ? row.allocation_ppm : 0,
      };
    });
    const detail = { ...legacy, schema_version: 8, visits, capture: {
      ...legacy.capture,
      schema_version: 8,
      mode: "adaptive",
      nominal_duration_seconds: 20,
      sample_rate_hz: 2500000,
      bandwidth_hz: 2500000,
      analysis_state: "separate_product",
      radio_serial: "synthetic",
      selected_edge: "lower",
      allowed_target_mask: 15,
      active_dwell_ms: 360,
      recorded_gain_mode: mode,
      recorded_manual_gain_db: gain,
      retained_visits: coverage.reduce((total, row) => total + row.retained_visits, 0),
      target_coverage: coverage,
    } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(detail)));
    render(<AdaptiveHopDetail sessionId="adaptive-test" />);
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByText("120 ms quiet / 360 ms active dwell · both receivers retained")).toBeInTheDocument();
    expect(screen.getByText("360 ms retained")).toBeInTheDocument();
  });

  it.each(["receiver", "rate", "inventory", "missing-decision", "rounded-counter"])("rejects invalid native %s", async fault => {
    const detail = hostAdaptiveDetailFixture();
    if (fault === "receiver") Object.assign(detail.capture, { physical_receiver: 2 });
    if (fault === "rate") Object.assign(detail.capture, { sample_rate_hz: 2500000 });
    if (fault === "inventory") detail.capture.host_feedback.accepted--;
    if (fault === "missing-decision") detail.host_decisions!.pop();
    if (fault === "rounded-counter") Object.assign(detail.visits[0], { valid_start_counter: Number(detail.visits[0].valid_start_counter) });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(detail)));
    await expect(getAdaptiveSession("adaptive-test")).rejects.toThrow();
  });
  it("shows retained inventory, source time, shadow proposals and cooldown without claiming absence", async () => {
    const detail = adaptiveDetailFixture();
    const fetcher = vi.fn(async (path: string) => path.endsWith("/glrt") || path.includes("/analysis?") ? respond(null, 404) : respond(detail));
    vi.stubGlobal("fetch", fetcher);
    render(<AdaptiveHopDetail sessionId="adaptive-test" />);
    await screen.findByRole("heading", { name: "Actual channel visits" });
    expect(screen.getByText("53 / 54")).toBeInTheDocument();
    expect(screen.getByText(/Proposals did not change/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Actual retained visits/ })).toBeInTheDocument();
    expect(await screen.findByText(/It is not queued here/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect visit 25" }));
    const choice = screen.getByLabelText("Selected hop decision");
    expect(choice).toHaveTextContent("actual CH2L; proposed CH1U");
    expect(choice).toHaveTextContent("2 consecutive misses · 1.500 s cooldown remaining");
    expect(choice).toHaveTextContent(detail.visits[25].valid_start_counter);
    fireEvent.click(screen.getByRole("button", { name: "Next visits" }));
    expect(screen.getByRole("table", { name: "Adaptive visit decisions" })).toHaveTextContent("Incomplete; not retained");
    expect(within(screen.getByRole("table", { name: "Adaptive visit decisions" })).getAllByRole("row")).toHaveLength(5);
    await screen.findByText(/No on-radio GLRT evidence was recorded/);
    expect(fetcher.mock.calls.some(([path]) => path === "/api/v1/scanner/adaptive-sessions/adaptive-test/glrt")).toBe(true);
    expect(screen.queryByText("No signal")).not.toBeInTheDocument();
  });

  it("keeps empty cancellation time and duty unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => path.endsWith("/glrt") || path.includes("/analysis?") ? respond(null, 404) : respond(adaptiveDetailFixture("empty", 0))));
    render(<AdaptiveHopDetail sessionId="empty" />);
    await screen.findByText("No hop was started.");
    expect(screen.getByText(/No attested device-time span/)).toBeInTheDocument();
    expect(screen.getByText("Source-counter duty").parentElement).toHaveTextContent("Unavailable");
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument();
  });

  it("keeps read errors explicit and separate from detector results", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 409)));
    render(<AdaptiveHopDetail sessionId="corrupt" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("409");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("selects a capture and paginates history", async () => {
    const page = adaptivePageFixture();
    page.total = 11; page.next_cursor = 10;
    const fetcher = vi.fn().mockResolvedValueOnce(respond(page)).mockResolvedValue(respond({ ...page, cursor: 10, next_cursor: null }));
    vi.stubGlobal("fetch", fetcher);
    const onSelect = vi.fn();
    render(<AdaptiveHopBrowser selectedId={null} onSelect={onSelect} />);
    fireEvent.click(await screen.findByRole("button", { name: /adaptive-test/ }));
    expect(onSelect).toHaveBeenCalledWith("adaptive-test");
    expect(fetcher.mock.calls[0][0]).toContain("limit=10");
    fireEvent.click(screen.getByRole("button", { name: "Next adaptive captures" }));
    await screen.findByText("11–11 of 11");
    expect(fetcher.mock.calls[1][0]).toContain("cursor=10");
  });

  it("renders all ten captures in the adaptive page without the legacy inner scroller", async () => {
    const page = adaptivePageFixture();
    page.total = 10;
    page.items = Array.from({ length: 10 }, (_, index) => ({
      ...page.items[0],
      session_id: `adaptive-test-${index}`,
    }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(page)));
    render(<AdaptiveHopBrowser selectedId={null} onSelect={() => {}} />);

    const table = await screen.findByRole("table", { name: "Adaptive capture history" });
    expect(within(table).getAllByRole("button")).toHaveLength(10);
    expect(table.parentElement).toHaveClass("adaptive-history-scroll");
  });

  it("distinguishes old-server support from an empty successful history", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(null, 404)));
    render(<AdaptiveHopBrowser selectedId={null} onSelect={() => {}} />);
    await screen.findByText("Adaptive history is not available on this server.");
    expect(screen.queryByText(/No adaptive or shadow capture has been published/)).not.toBeInTheDocument();
  });

  it("ignores a late response from the previously selected scan", async () => {
    let finishOld: (value: Response) => void = () => {};
    const old = new Promise<Response>(resolve => { finishOld = resolve; });
    vi.stubGlobal("fetch", vi.fn((path: string) => path.endsWith("/glrt") || path.includes("/analysis?") ? Promise.resolve(respond(null, 404))
      : path.endsWith("/old") ? old : Promise.resolve(respond(adaptiveDetailFixture("new")))));
    const view = render(<AdaptiveHopDetail sessionId="old" />);
    view.rerender(<AdaptiveHopDetail sessionId="new" />);
    await screen.findByText("new");
    await act(async () => { finishOld(respond(adaptiveDetailFixture("old"))); });
    expect(screen.queryByText("old")).not.toBeInTheDocument();
  });

  it("does not overlap slow history polls and aborts when unmounted", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetcher);
    const view = render(<AdaptiveHopBrowser selectedId={null} onSelect={() => {}} />);
    await act(async () => { vi.advanceTimersByTime(90000); });
    expect(fetcher).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it.each(["rounded", "wrong-session", "wrong-source-time", "retained-tail", "shadow-target", "overlap-masks"])("rejects malformed %s evidence", async fault => {
    const value = adaptiveDetailFixture();
    if (fault === "rounded") Object.assign(value.visits[0], { valid_start_counter: Number(value.visits[0].valid_start_counter) });
    if (fault === "wrong-session") value.capture.session_id = "wrong";
    if (fault === "wrong-source-time") value.visits[0].valid_start_seconds += .001;
    if (fault === "retained-tail") value.visits.at(-1)!.retained = true;
    if (fault === "shadow-target") value.visits[25].target_index = 2;
    if (fault === "overlap-masks") value.visits[25].quiet_mask = 13;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(value)));
    await expect(getAdaptiveSession("adaptive-test")).rejects.toThrow();
  });

  it("rejects legacy fixed history on the adaptive route", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond({ schema_version: 3, items: [] })));
    await expect(getAdaptiveSessions(0)).rejects.toThrow(/invalid/);
  });
});
