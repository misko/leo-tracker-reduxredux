import {cleanup,render,screen,waitFor} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {FastStandardAnalysis} from "./FastStandardAnalysis";

afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const names=["ch1-4-all","ch5-8-all","ch1-4-unassociated","ch5-8-unassociated","ch1-4-residuals","ch5-8-residuals","track-rms","position"];
const arm={endpoint_latlon:[37.842403850242285,-122.49124137019581],associated_points:3000,
  associated_percent:75,tracks:90,satellites:20,residual_rms_hz:115,evaluation_error_m:883.504916};
const result={schema_version:1,state:"complete",model_version:"algo07-causal-guarded-reassociation-v1",
  selected_model:"algo04-causal-numerical-v1",decision:"ALGO06_fallback",glrt_points:4000,
  arms:{fitted_c:arm,c0:{...arm,evaluation_error_m:911.9615}},
  evaluation_reference:{latitude_deg:37.849061591561885,longitude_deg:-122.48574968092912},
  artifacts:names.map(name=>({name,sha256:"sha256:"+"a".repeat(64)}))};

it("shows the standard result, exact fallback and all eight versioned PNGs",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>result})));
  render(<FastStandardAnalysis runId="scan"/>);
  expect(await screen.findByText("883.5 m")).toBeInTheDocument();
  expect(screen.getByText("912.0 m")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Complete · retained ALGO04 solution");
  expect(screen.getAllByRole("img")).toHaveLength(8);
  for(const image of screen.getAllByRole("img"))expect(image.getAttribute("src")).toContain("?sha256=sha256%3A");
  expect(screen.getByText(/Evaluation reference: 37.84906159/)).toBeInTheDocument();
});

it("never presents an old or pending result as completed ALGO07",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({...result,model_version:"legacy"})})));
  render(<FastStandardAnalysis runId="scan"/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("another algorithm");
  expect(screen.queryByText("883.5 m")).not.toBeInTheDocument();
});

it("does not invent evaluation accuracy without a confirmed reference",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({...result,evaluation_reference:null,
    arms:{c0:{...arm,evaluation_error_m:null},fitted_c:{...arm,evaluation_error_m:null}}})})));
  render(<FastStandardAnalysis runId="scan"/>);
  await waitFor(()=>expect(screen.getAllByText("Reference unavailable")).toHaveLength(2));
});
