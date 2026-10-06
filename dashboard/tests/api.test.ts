import { describe, it, expect } from "vitest";
import { validateReview, csvCell, visibleRunIds } from "../functions/api/[[path]]";
const review = {
  version: "mcap-v2",
  task_id: "sample_01_seg01_sub01__camera0",
  clip_id: "sample_01_seg01_sub01",
  camera_id: "camera0",
  target: "model",
  run_id: "run",
  reviewer: "A",
  accuracy: "accurate",
  omission: "none",
  notes: "",
};
describe("Task identity and public input validation", () => {
  it("accepts camera-specific target", () =>
    expect(validateReview(review)).toBeNull());
  it("rejects different camera for same task", () =>
    expect(validateReview({ ...review, camera_id: "camera1" })).not.toBeNull());
  it("rejects unnamed reviewer", () =>
    expect(validateReview({ ...review, reviewer: " " })).not.toBeNull());
  it("rejects invalid camera", () =>
    expect(validateReview({ ...review, camera_id: "camera6" })).not.toBeNull());
  it("rejects model-less evaluation", () =>
    expect(validateReview({ ...review, run_id: "" })).not.toBeNull());
  it("protects CSV formulas", () => expect(csvCell(" =1+1")).toBe('"\' =1+1"'));
});

import { onRequest } from "../functions/api/[[path]]";
function cloudFixture(mentor = false) {
  const current = {
    task_id: review.task_id,
    result_id: "CURRENT",
    caption_status: "success",
    generated_caption: "Visible action.",
  };
  const evidence = {
    status: "result",
    run_id: "run",
    task_id: review.task_id,
    result_id: "CURRENT",
    input_id: "INPUT",
    display_profile: "jpeg640-v1",
    frames: [
      {
        object_key: "sampling/jpeg640-v1/" + "a".repeat(64) + ".jpg",
        relative_time_s: 0.033,
      },
    ],
  };
  const writes: unknown[][] = [];
  const DB = {
    prepare(sql: string) {
      let params: unknown[] = [];
      return {
        bind(...values: unknown[]) {
          params = values;
          return this;
        },
        async first() {
          if (sql.includes("cs_datasets")) return { ready: 1 };
          if (sql.includes("cs_dashboard"))
            return {
              data: JSON.stringify({
                run_ids: ["run"],
                experiment: { sample: "sample_01" },
                ...(mentor ? { presentation: { mode: "mentor", fixed_prompt_id: "baseline-v2", run_ids: ["run"] }, run_ids: ["run", "OLD"] } : {}),
              }),
            };
          if (sql.includes("cs_sampling"))
            return { data: JSON.stringify(evidence) };
          if (sql.includes("cs_results"))
            return { data: JSON.stringify(current) };
          if (sql.includes("cs_tasks")) return { task_id: review.task_id };
          if (sql.includes("cs_rate_limits")) return { count: 1 };
          return null;
        },
        async all() {
          if (sql.includes("cs_runs"))
            return {
              results: [
                {
                  id: "run",
                  config: JSON.stringify({ prompt_id: mentor ? "baseline-v2" : "baseline-v1" }),
                },
                {
                  id: "OLD",
                  config: JSON.stringify({ prompt_id: "window-v2" }),
                },
              ],
            };
          if (sql.includes("cs_results"))
            return {
              results: [
                { run_id: "run", data: JSON.stringify(current) },
                { run_id: "OLD", data: JSON.stringify(current) },
              ],
            };
          return { results: [] };
        },
        async run() {
          if (sql.includes("INSERT INTO cs_reviews")) writes.push(params);
          return { success: true };
        },
      };
    },
  };
  const VIDEOS = {
    async get() {
      return {
        body: new Uint8Array([255, 216, 255]),
        size: 3,
        httpEtag: '"jpeg"',
      };
    },
  };
  return { env: { DB, VIDEOS }, writes };
}
async function invoke(
  path: string,
  fixture: ReturnType<typeof cloudFixture>,
  body?: unknown,
) {
  const request = new Request(
    "https://example.pages.dev/api/" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            Origin: "https://example.pages.dev",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        },
  );
  return await (onRequest as any)({ request, env: fixture.env });
}
describe("Published v1 cloud interfaces", () => {
  it("hides old runs without deleting them", async () => {
    const response = await invoke("clips", cloudFixture());
    const data = await response.json();
    expect(data.runs.map((r: any) => r.id)).toEqual(["run"]);
    expect(data.results).toHaveLength(1);
    expect(data.experiment.sample).toBe("sample_01");
  });
  it("serves only matching result evidence and JPEG frames", async () => {
    const fixture = cloudFixture();
    const suffix = `run=run&task=${review.task_id}&result=CURRENT`;
    const response = await invoke("sampling?" + suffix, fixture);
    const data = await response.json();
    expect(data.frames[0].object_key).toBeUndefined();
    expect(data.frames[0].url).toContain("input=INPUT");
    const image = await invoke(data.frames[0].url.slice(5), fixture);
    expect(image.status).toBe(200);
    expect(image.headers.get("Content-Type")).toBe("image/jpeg");
    expect(
      (await invoke("sampling?run=OLD&task=" + review.task_id, fixture)).status,
    ).toBe(404);
    expect(
      (await invoke("sampling?" + suffix.replace("CURRENT", "STALE"), fixture))
        .status,
    ).toBe(404);
    expect(
      (
        await invoke(
          `sampling/frame?run=run&task=${review.task_id}&input=OTHER&frame=0`,
          fixture,
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await invoke(
          `sampling/frame?run=run&task=${review.task_id}&input=INPUT&frame=-1`,
          fixture,
        )
      ).status,
    ).toBe(404);
  });
  it("persists independent reviews against exact result versions", async () => {
    const fixture = cloudFixture();
    expect(
      (await invoke("reviews", fixture, { ...review, result_id: "STALE" }))
        .status,
    ).toBe(409);
    expect(fixture.writes).toHaveLength(0);
    for (const reviewer of ["Reviewer A", "Reviewer B"])
      expect(
        (
          await invoke("reviews", fixture, {
            ...review,
            reviewer,
            result_id: "CURRENT",
          })
        ).status,
      ).toBe(201);
    expect(fixture.writes).toHaveLength(2);
    expect(fixture.writes[0][10]).toBe("CURRENT");
  });
  it("mentor visibility hides retained v1 data and rejects its reviews", async () => {
    const fixture = cloudFixture(true);
    const response = await invoke("clips", fixture);
    const data = await response.json();
    expect(data.runs.map((r: any) => r.id)).toEqual(["run"]);
    expect(data.presentation).toEqual({ mode: "mentor", fixed_prompt_id: "baseline-v2" });
    expect(data.review_features).toContain("quality_dimensions");
    expect((await invoke("reviews", fixture, { ...review, run_id: "OLD", result_id: "CURRENT" })).status).toBe(400);
    expect((await invoke(`sampling?run=OLD&task=${review.task_id}`, fixture)).status).toBe(404);
    expect(visibleRunIds({ run_ids: ["run", "OLD"], experiment: {}, presentation: {mode:"mentor", fixed_prompt_id:"baseline-v2", run_ids:["run","UNPUBLISHED"]} })).toEqual(["run"]);
  });
  it("persists model quality dimensions and validates their values", async () => {
    const fixture = cloudFixture(true);
    const response = await invoke("reviews", fixture, { ...review, result_id: "CURRENT", clarity: "clear", object_accuracy: "partial", direction_accuracy: "incorrect", outcome_accuracy: "unknown" });
    expect(response.status).toBe(201);
    expect(fixture.writes[0].slice(-4)).toEqual(["clear", "partial", "incorrect", "unknown"]);
    expect(validateReview({...review, clarity:"unsupported"})).not.toBeNull();
    expect(validateReview({...review, object_accuracy:123})).not.toBeNull();
    const exported = await (await invoke("reviews/export",fixture)).text();
    expect(exported).toContain('"direction_accuracy"');
    expect(exported).toContain('"result_id"');
  });
});
