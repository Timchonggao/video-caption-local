interface Env {
  DB: D1Database;
  VIDEOS: R2Bucket;
}
const VERSION = "mcap-v2";
type Publication = {
  experiment: Record<string, unknown>;
  run_ids: string[];
  presentation?: { mode: "mentor"; fixed_prompt_id: string; run_ids: string[] };
};
async function publication(db: D1Database) {
  const row = await db
    .prepare("SELECT data FROM cs_dashboard WHERE version=?")
    .bind(VERSION)
    .first<{ data: string }>();
  return row
    ? (JSON.parse(row.data) as Publication)
    : null;
}
export function visibleRunIds(state: Publication): string[] {
  return state.presentation?.mode === "mentor"
    ? state.presentation.run_ids.filter((id) => state.run_ids.includes(id))
    : state.run_ids;
}
async function samplingRow(db: D1Database, url: URL, frame: boolean) {
  const run = url.searchParams.get("run") || "",
    task = url.searchParams.get("task") || "";
  const state = await publication(db);
  if (!state || !visibleRunIds(state).includes(run)) return null;
  const result = await db
    .prepare(
      "SELECT data FROM cs_results WHERE version=? AND run_id=? AND task_id=?",
    )
    .bind(VERSION, run, task)
    .first<{ data: string }>();
  if (!result) return null;
  const current = JSON.parse(result.data);
  if (
    url.searchParams.get("result") &&
    url.searchParams.get("result") !== current.result_id
  )
    return null;
  const row = await db
    .prepare(
      "SELECT data FROM cs_sampling WHERE version=? AND run_id=? AND task_id=? AND result_id=?",
    )
    .bind(VERSION, run, task, current.result_id)
    .first<{ data: string }>();
  if (!row) return null;
  const evidence = JSON.parse(row.data);
  if (frame && url.searchParams.get("input") !== evidence.input_id) return null;
  return evidence;
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
export function validateReview(b: any) {
  if (!b || typeof b !== "object") return "无效提交";
  for (const [key, max] of Object.entries({
    version: 100,
    task_id: 200,
    clip_id: 160,
    camera_id: 16,
    run_id: 100,
    reviewer: 80,
    notes: 2000,
  }))
    if (typeof b[key] !== "string" || b[key].length > max) return "字段无效";
  if (
    b.version !== VERSION ||
    !/^camera[0-5]$/.test(b.camera_id) ||
    b.task_id !== `${b.clip_id}__${b.camera_id}` ||
    !b.clip_id ||
    !b.reviewer.trim()
  )
    return "任务或姓名无效";
  if (
    !["original", "model"].includes(b.target) ||
    !["accurate", "partial", "incorrect", "unknown"].includes(b.accuracy) ||
    !["none", "yes", "unknown"].includes(b.omission)
  )
    return "选项无效";
  if (
    (b.target === "original" && b.run_id) ||
    (b.target === "model" && !b.run_id)
  )
    return "评价目标无效";
  for (const key of ["clarity", "object_accuracy", "direction_accuracy", "outcome_accuracy"]) {
    const allowed = key === "clarity" ? ["", "clear", "partial", "unclear", "unknown"] : ["", "accurate", "partial", "incorrect", "unknown"];
    if (typeof (b[key] ?? "") !== "string" || !allowed.includes(b[key] ?? ""))
      return "评价维度无效";
  }
  return null;
}
export function csvCell(v: unknown) {
  let s = String(v ?? "");
  if (/^\s*[=+@-]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
export const onRequest: PagesFunction<Env> = async ({ request, env }) => {
  try {
    const url = new URL(request.url),
      path = decodeURIComponent(url.pathname.slice(5));
    if (request.method === "GET" && path === "clips") {
      const state = await env.DB.prepare(
        "SELECT ready FROM cs_datasets WHERE version=?",
      )
        .bind(VERSION)
        .first<{ ready: number }>();
      if (!state?.ready) return json({ error: "新版数据尚未完成发布" }, 409);
      const clips = (
        await env.DB.prepare(
          "SELECT data FROM cs_clips WHERE version=? ORDER BY id",
        )
          .bind(VERSION)
          .all<{ data: string }>()
      ).results.map((r) => JSON.parse(r.data));
      const tasks = (
        await env.DB.prepare(
          "SELECT data FROM cs_tasks WHERE version=? ORDER BY task_id",
        )
          .bind(VERSION)
          .all<{ data: string }>()
      ).results.map((r) => JSON.parse(r.data));
      const published = await publication(env.DB);
      if (!published) return json({ error: "实验尚未完成发布" }, 409);
      const visible = visibleRunIds(published);
      const runs = (
        await env.DB.prepare("SELECT id,config FROM cs_runs ORDER BY id").all<{
          id: string;
          config: string;
        }>()
      ).results
        .filter((r) => visible.includes(r.id))
        .map((r) => ({ id: r.id, ...JSON.parse(r.config) }));
      const results = (
        await env.DB.prepare(
          "SELECT run_id,data FROM cs_results WHERE version=?",
        )
          .bind(VERSION)
          .all<{ run_id: string; data: string }>()
      ).results
        .filter((r) => visible.includes(r.run_id))
        .map((r) => ({ ...JSON.parse(r.data), run_id: r.run_id }));
      const reviews = (
        await env.DB.prepare(
          "SELECT task_id,clip_id,camera_id,target,run_id,result_id,COUNT(*) AS count FROM cs_reviews WHERE version=? GROUP BY task_id,clip_id,camera_id,target,run_id,result_id",
        )
          .bind(VERSION)
          .all()
      ).results;
      return json({
        version: VERSION,
        clips,
        tasks,
        runs,
        results,
        reviews: reviews.filter(
          (r) =>
            r.target === "original" ||
            visible.includes(String(r.run_id)),
        ),
        experiment: published.experiment,
        presentation: published.presentation ? { mode: published.presentation.mode, fixed_prompt_id: published.presentation.fixed_prompt_id } : null,
        review_features: ["quality_dimensions"],
      });
    }
    if (request.method === "GET" && path === "sampling") {
      const evidence = await samplingRow(env.DB, url, false);
      if (!evidence) return json({ error: "此任务尚无发布的采样输入" }, 404);
      return json({
        ...evidence,
        frames: evidence.frames.map((frame: any, i: number) => {
          const { object_key, ...info } = frame;
          return {
            ...info,
            url:
              "/api/sampling/frame?" +
              new URLSearchParams({
                run: evidence.run_id,
                task: evidence.task_id,
                input: evidence.input_id,
                frame: String(i),
              }),
          };
        }),
      });
    }
    if (["GET", "HEAD"].includes(request.method) && path === "sampling/frame") {
      const evidence = await samplingRow(env.DB, url, true);
      const index = url.searchParams.get("frame") || "";
      if (!/^\d{1,3}$/.test(index)) return json({ error: "采样帧不存在" }, 404);
      const frame = evidence?.frames[Number(index)];
      if (
        !frame ||
        !/^sampling\/jpeg640-v1\/[a-f0-9]{64}\.jpg$/.test(frame.object_key)
      )
        return json({ error: "采样帧不存在" }, 404);
      const object =
        request.method === "HEAD"
          ? await env.VIDEOS.head(frame.object_key)
          : await env.VIDEOS.get(frame.object_key);
      if (!object) return json({ error: "采样帧尚未上传" }, 404);
      return new Response(
        request.method === "HEAD" ? null : (object as R2ObjectBody).body,
        {
          headers: {
            "Content-Type": "image/jpeg",
            "Content-Length": String(object.size),
            ETag: object.httpEtag,
            "Cache-Control": "public,max-age=86400,immutable",
          },
        },
      );
    }
    if (
      request.method === "GET" &&
      (path.startsWith("annotations/") || path.startsWith("sample-details/"))
    ) {
      const annotation = path.startsWith("annotations/"),
        sid = path.slice(annotation ? 12 : 15);
      const row = await env.DB.prepare(
        "SELECT annotation_json,inventory_json FROM cs_samples WHERE version=? AND sample_id=?",
      )
        .bind(VERSION, sid)
        .first<{ annotation_json: string; inventory_json: string }>();
      return row
        ? json(
            JSON.parse(annotation ? row.annotation_json : row.inventory_json),
          )
        : json({ error: "样本不存在" }, 404);
    }
    if (["GET", "HEAD"].includes(request.method) && path.startsWith("media/")) {
      const row = await env.DB.prepare(
        "SELECT object_key FROM cs_media WHERE version=? AND id=?",
      )
        .bind(VERSION, path.slice(6))
        .first<{ object_key: string }>();
      if (!row) return json({ error: "视频不存在" }, 404);
      const meta = await env.VIDEOS.head(row.object_key);
      if (!meta) return json({ error: "视频尚未上传" }, 404);
      let offset = 0,
        length = meta.size,
        status = 200;
      const range = request.headers.get("Range");
      if (range) {
        const match = /^bytes=(\d*)-(\d*)$/.exec(range);
        if (!match || (!match[1] && !match[2]))
          return new Response(null, {
            status: 416,
            headers: { "Content-Range": `bytes */${meta.size}` },
          });
        if (match[1]) {
          offset = Number(match[1]);
          length =
            (match[2]
              ? Math.min(Number(match[2]), meta.size - 1)
              : meta.size - 1) -
            offset +
            1;
        } else {
          length = Math.min(Number(match[2]), meta.size);
          offset = meta.size - length;
        }
        if (
          !Number.isSafeInteger(offset) ||
          !Number.isSafeInteger(length) ||
          length <= 0 ||
          offset >= meta.size
        )
          return new Response(null, {
            status: 416,
            headers: { "Content-Range": `bytes */${meta.size}` },
          });
        status = 206;
      }
      const headers = new Headers({
        "Content-Type": "video/mp4",
        "Content-Length": String(length),
        "Accept-Ranges": "bytes",
        "Cache-Control": "public,max-age=3600",
        ETag: meta.httpEtag,
      });
      if (status === 206)
        headers.set(
          "Content-Range",
          `bytes ${offset}-${offset + length - 1}/${meta.size}`,
        );
      if (request.method === "HEAD")
        return new Response(null, { status, headers });
      const object = await env.VIDEOS.get(row.object_key, {
        range: { offset, length },
      });
      return object
        ? new Response(object.body, { status, headers })
        : json({ error: "视频不存在" }, 404);
    }
    if (request.method === "POST" && path === "reviews") {
      if (request.headers.get("Origin") !== url.origin)
        return json({ error: "来源无效" }, 403);
      const raw = await request.text();
      if (raw.length > 12000) return json({ error: "内容过长" }, 413);
      let b;
      try {
        b = JSON.parse(raw);
      } catch {
        return json({ error: "无效 JSON" }, 400);
      }
      const error = validateReview(b);
      if (error) return json({ error }, 400);
      if (
        !(await env.DB.prepare(
          "SELECT task_id FROM cs_tasks WHERE version=? AND task_id=? AND clip_id=? AND camera_id=?",
        )
          .bind(VERSION, b.task_id, b.clip_id, b.camera_id)
          .first())
      )
        return json({ error: "任务不存在" }, 404);
      let resultId = "";
      if (b.target === "model") {
        const r = await env.DB.prepare(
          "SELECT data FROM cs_results WHERE version=? AND task_id=? AND run_id=?",
        )
          .bind(VERSION, b.task_id, b.run_id)
          .first<{ data: string }>();
        const current = r ? JSON.parse(r.data) : null;
        const published = await publication(env.DB);
        if (!published || !visibleRunIds(published).includes(b.run_id))
          return json({ error: "该实验未公开展示" }, 400);
        if (!current || current.caption_status !== "success")
          return json({ error: "没有成功结果" }, 400);
        if (current.result_id !== b.result_id)
          return json({ error: "结果已更新，请刷新页面后评价" }, 409);
        resultId = current.result_id;
      }
      const now = Math.floor(Date.now() / 1000),
        key =
          (request.headers.get("CF-Connecting-IP") || "local") +
          ":" +
          Math.floor(now / 60);
      const limit = await env.DB.prepare(
        "INSERT INTO cs_rate_limits(key,count,expires) VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1 RETURNING count",
      )
        .bind(key, now + 120)
        .first<{ count: number }>();
      if ((limit?.count || 0) > 10) return json({ error: "提交过于频繁" }, 429);
      await env.DB.prepare("DELETE FROM cs_rate_limits WHERE expires<?")
        .bind(now)
        .run();
      await env.DB.prepare(
        "INSERT INTO cs_reviews(version,task_id,clip_id,camera_id,target,run_id,reviewer,accuracy,omission,notes,result_id,clarity,object_accuracy,direction_accuracy,outcome_accuracy) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      )
        .bind(
          VERSION,
          b.task_id,
          b.clip_id,
          b.camera_id,
          b.target,
          b.run_id,
          b.reviewer.trim(),
          b.accuracy,
          b.omission,
          b.notes,
          resultId,
          ...["clarity", "object_accuracy", "direction_accuracy", "outcome_accuracy"].map(key => b.target === "model" ? b[key] || "" : ""),
        )
        .run();
      return json({ saved: true }, 201);
    }
    if (request.method === "GET" && path === "reviews/export") {
      const rows = (
        await env.DB.prepare(
          "SELECT * FROM cs_reviews WHERE version=? ORDER BY id",
        )
          .bind(VERSION)
          .all()
      ).results;
      const keys = [
        "id",
        "version",
        "task_id",
        "clip_id",
        "camera_id",
        "target",
        "run_id",
        "reviewer",
        "accuracy",
        "omission",
        "notes",
        "created_at",
        "result_id",
        "clarity",
        "object_accuracy",
        "direction_accuracy",
        "outcome_accuracy",
      ];
      return new Response(
        "\ufeff" +
          [
            keys.map(csvCell).join(","),
            ...rows.map((r) => keys.map((k) => csvCell(r[k])).join(",")),
          ].join("\r\n"),
        {
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": 'attachment; filename="reviews.csv"',
          },
        },
      );
    }
    return json({ error: "接口不存在" }, 404);
  } catch (e) {
    console.error(e);
    return json({ error: "服务暂不可用" }, 500);
  }
};
