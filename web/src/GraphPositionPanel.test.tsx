import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GraphPositionPanel } from "./GraphPositionPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows selected ALGO03 and its original ALGO02 comparator", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({
    state: "complete", selected_model: "algo03-causal-predictive-v1", decision: "ALGO03_single", fallback: false,
    baseline: { model_version: "algo02-causal-family-v1", position: { latitude_deg: 37.9, longitude_deg: -122.5 } },
    selected: { model_version: "algo03-causal-predictive-v1", position: { latitude_deg: 37.91, longitude_deg: -122.51 } },
  }) })));
  render(<GraphPositionPanel runId="scan" />);
  expect(await screen.findByRole("heading", { name: "Graph localization · ALGO03" })).toBeInTheDocument();
  expect(screen.getByText("37.910000°, -122.510000°")).toBeInTheDocument();
  expect(screen.getByText("37.900000°, -122.500000°")).toBeInTheDocument();
});

it("labels ALGO02 fallback when v2 is missing", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({
    state: "complete", selected_model: "algo03-causal-predictive-v1", decision: "ALGO02_fallback", fallback: true,
    reason: "Awaiting qualified ALGO03 result", selected: { model_version: "algo02-causal-family-v1", position: null },
  }) })));
  render(<GraphPositionPanel runId="scan" />);
  expect(await screen.findByText(/ALGO02 fallback · Awaiting qualified ALGO03/)).toBeInTheDocument();
  expect(screen.getByText("algo02-causal-family-v1")).toBeInTheDocument();
});
