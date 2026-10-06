import { test, expect } from "@playwright/test";
test("six cameras, original intervals, collective playback and collapsible samples", async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem("sidebarCollapsed", "false"));
  await page.goto("/?clip=sample_01_seg01_sub01");
  await expect(page.locator(".camera-tile")).toHaveCount(1);
  await page.getByRole("button", {name:"展开全部相机"}).click();
  await expect(page.locator(".camera-tile")).toHaveCount(6);
  await expect(page.locator(".camera-tile h2")).toHaveText([
    "camera0",
    "camera1",
    "camera2",
    "camera3",
    "camera4",
    "camera5",
  ]);
  await page.getByRole("button", { name: "播放全部视频" }).click();
  await page.waitForFunction(() =>
    [
      ...document.querySelectorAll<HTMLVideoElement>(".camera-tile video"),
    ].every((v) => !v.paused),
  );
  await page.getByRole("button", { name: "暂停全部视频" }).click();
  await page.waitForFunction(() =>
    [
      ...document.querySelectorAll<HTMLVideoElement>(".camera-tile video"),
    ].every((v) => v.paused),
  );
  await page.getByRole("button", { name: "收起样本栏" }).click();
  await expect(page.locator("main")).toHaveClass(/sidebar-collapsed/);
  await page.getByRole("button", { name: "展开样本栏" }).click();
  await page.locator(".clip-chip").nth(1).click();
  await expect(page.locator(".clip-progress")).toHaveText("2 / 24");
  await page.getByText("详细 JSON 字段", { exact: true }).click();
  await expect(page.locator(".json-details pre")).toContainText(
    "segments_info",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 2,
    ),
  ).toBeTruthy();
});
test("model captions and review controls preserve camera identity", async ({
  page,
}) => {
  // Isolated browser fixture: never write synthetic captions to formal runs or cloud.
  await page.route("**/api/clips", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.runs = [
      {
        id: "TEST-ONLY",
        model_key: "qwen",
        model_label: "Qwen",
        model_name: "fixture",
        prompt_id: "baseline-v1",
      },
    ];
    data.results = [
      {
        task_id: "sample_01_seg01_sub01__camera1",
        clip_id: "sample_01_seg01_sub01",
        camera_id: "camera1",
        run_id: "TEST-ONLY",
        caption_status: "success",
        generated_caption: "Only camera1 sees this action.",
      },
    ];
    await route.fulfill({ json: data });
  });
  await page.goto("/?clip=sample_01_seg01_sub01&prompt=v1.camera1");
  await expect(page.getByLabel("Prompt 版本").locator("option")).toHaveCount(1);
  await expect(page.getByText("Only camera1 sees this action.")).toHaveCount(1);
  await page.getByRole("button", { name: "评价此结果" }).click();
  await expect(page.getByLabel("评价相机")).toHaveValue("camera1");
  await expect(page.locator(".review-collapse")).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "查看 camera0 结果" }).click();
  await expect(page.getByLabel("Prompt 版本")).toHaveValue("v1");
  await expect(page.locator(".selected-camera .camera-title")).toHaveText(
    "camera2",
  );
  await page.getByRole("button", {name:"展开全部相机"}).click();
  await page.locator(".camera-title").nth(1).click();
  await expect(page.getByText("Only camera1 sees this action.")).toHaveCount(0);
  await page.getByRole("button", {name:"查看 camera1 结果"}).click();
  await expect(page.getByText("Only camera1 sees this action.")).toHaveCount(1);
  await page.getByRole("button", { name: "查看 camera0 结果" }).click();
  await expect(page.getByText("Only camera1 sees this action.")).toHaveCount(0);
  await expect(page.locator(".sample-reference")).not.toHaveAttribute(
    "open",
    "",
  );
  await page.getByText("raw caption", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "整体 caption", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "片段caption", exact: true }),
  ).toBeVisible();
});

test("v2 windows remain expandable inside the original task result", async ({
  page,
}) => {
  await page.route("**/api/clips", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.runs = [
      {
        id: "TEST-V2",
        model_key: "qwen",
        model_label: "Qwen",
        model_name: "fixture",
        prompt_id: "window-v2",
      },
    ];
    data.results = [
      {
        task_id: "sample_01_seg01_sub01__camera0",
        clip_id: "sample_01_seg01_sub01",
        camera_id: "camera0",
        run_id: "TEST-V2",
        caption_status: "success",
        generated_caption: "Aggregated visible operation.",
        windows: [
          {
            window_id: "sample_01_seg01_sub01__camera0__w0001",
            source_interval_s: [0, 5],
            parent_relative_interval_s: [0, 5],
            caption_status: "success",
            generated_caption: "Current window observation.",
            result_id: "WINDOW-R1",
            sampled_times_s: [0, 0.083333],
          },
        ],
      },
    ];
    await route.fulfill({ json: data });
  });
  await page.goto("/?clip=sample_01_seg01_sub01&prompt=window-v2.camera0");
  await expect(page.getByText("Aggregated visible operation.")).toBeVisible();
  await page.getByText("窗口结果与追溯（1）", { exact: true }).click();
  await expect(
    page.getByText("Current window observation.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("0.00 — 5.00 秒", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "评价此结果" }).click();
  await expect(page.getByLabel("评价相机")).toHaveValue("camera0");
});

test("baseline progress, plain captions and persisted sampling evidence", async ({
  page,
}) => {
  await page.route("**/api/clips", async (route) => {
    const data = await (await route.fetch()).json();
    data.runs = [
      {
        id: "EVIDENCE-TEST",
        model_key: "qwen",
        model_label: "Qwen test model",
        model_name: "Actual test checkpoint",
        prompt_id: "baseline-v1",
      },
    ];
    data.results = [
      {
        task_id: "sample_01_seg01_sub01__camera1",
        clip_id: "sample_01_seg01_sub01",
        camera_id: "camera1",
        run_id: "EVIDENCE-TEST",
        result_id: "RESULT1",
        caption_status: "success",
        generated_caption: "Visible movement.",
        annotation: { generated_caption: "Visible movement." },
      },
      {
        task_id: "sample_01_seg01_sub01__camera2",
        clip_id: "sample_01_seg01_sub01",
        camera_id: "camera2",
        run_id: "EVIDENCE-TEST",
        caption_status: "failed",
        generated_caption: "",
        error: "Test decode failure",
      },
    ];
    await route.fulfill({ json: data });
  });
  await page.route("**/api/sampling?**", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    expect(query.get("run")).toBe("EVIDENCE-TEST");
    if (query.get("task")?.endsWith("camera1")) {
      expect(query.get("result")).toBe("RESULT1");
      await route.fulfill({
        json: {
          status: "result",
          input_id: "INPUT1",
          frames: [
            {
              url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT5sAAAAASUVORK5CYII=",
              relative_time_s: 0.033,
              source_time_s: 47.033,
              requested_relative_time_s: 0,
              deviation_s: 0.033,
              processed_size: [768, 640],
            },
          ],
        },
      });
    } else
      await route.fulfill({
        json: {
          status: "missing",
          frames: [],
          message: "此任务尚无保存的采样输入",
        },
      });
  });
  await page.goto("/?clip=sample_01_seg01_sub01&prompt=v1.camera1");
  await expect(page.locator(".experiment-progress")).toHaveText(
    "sample_01：已生成 1／144，失败 1",
  );
  await expect(page.getByLabel("Prompt 版本").locator("option")).toHaveCount(1);
  await expect(page.locator(".model-choice button")).toHaveCount(1);
  await expect(page.locator(".model-caption h2")).toHaveText("Qwen test model");
  await expect(
    page.getByText("Actual test checkpoint", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("结构化结果", { exact: true })).toHaveCount(0);
  await expect(page.locator(".sampling-input")).not.toHaveAttribute("open", "");
  await page.getByText("采样输入", { exact: true }).click();
  await expect(
    page.getByText("帧 1 · 0.033 秒", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("模型输入 768×640", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "查看 camera0 结果" }).click();
  await page.getByText("采样输入", { exact: true }).click();
  await expect(
    page.getByText("此任务尚无保存的采样输入", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("帧 1 · 0.033 秒", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.locator(".experiment-progress")).toHaveText(
    "sample_01：已生成 1／144，失败 1",
  );
  await expect(page.locator(".clip-card")).toHaveCount(10);
});

test("camera2 v2 has 24-task progress and defaults to camera2", async ({ page }) => {
  await page.route("**/api/clips", async route => {
    const response = await route.fetch(); const data = await response.json();
    data.runs = [{id:"TEST-v1",model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v1",sample:"sample_01"},
      {id:"TEST-v2",model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",sampling_fps:6}];
    data.results = [{task_id:"sample_01_seg01_sub01__camera2",clip_id:"sample_01_seg01_sub01",camera_id:"camera2",run_id:"TEST-v2",caption_status:"success",generated_caption:"Repeated visible transfers."}];
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg01_sub01&prompt=v1.camera0");
  await page.getByLabel("Prompt 版本").selectOption("v2");
  await expect(page).toHaveURL(/prompt=v2.camera2/);
  await expect(page.getByText("Repeated visible transfers.")).toBeVisible();
  await expect(page.locator(".experiment-progress")).toContainText("1／24");
  await page.getByRole("button",{name:"查看 camera0 结果"}).click();
  await expect(page.getByText("此模型尚未生成该相机结果；请选择 camera2。")).toBeVisible();
});

test("five-task comparison separates experiment and full sample progress", async ({ page }) => {
  await page.route("**/api/clips", async route => {
    const response = await route.fetch(); const data = await response.json();
    const tasks=[1,2,10,11,12].map(i=>`sample_01_seg02_sub${String(i).padStart(2,"0")}__camera2`);
    data.runs=[{id:"TEST-B",model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",sampling_fps:6,input_mode:"video",frame_max_pixels:512000,comparison_group:"B",experiment_task_ids:tasks}];
    data.results=[{task_id:tasks[0],clip_id:"sample_01_seg02_sub01",camera_id:"camera2",run_id:"TEST-B",caption_status:"success",generated_caption:"Visible process."}];
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg02_sub01&prompt=v2.camera2");
  await expect(page.locator(".experiment-progress")).toContainText("本轮五段 已生成 1／5");
  await expect(page.locator(".experiment-progress")).toContainText("全样本 24 条");
  await expect(page.getByText("输入：视频序列 · 6 fps · 每帧像素预算 512000")).toBeVisible();
});

test("C and D compare descriptive quality, facts and measured resources independently",async({page})=>{
  await page.route("**/api/clips",async route=>{
    const response=await route.fetch();const data=await response.json();data.review_features=["quality_dimensions"];
    const task="sample_01_seg02_sub01__camera2";
    data.runs=["C","D"].map(g=>({id:`TEST-${g}`,model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",comparison_group:g,experiment_task_ids:[task],input_mode:g==="C"?"images":"video"}));
    data.results=["C","D"].map(g=>({task_id:task,clip_id:"sample_01_seg02_sub01",camera_id:"camera2",run_id:`TEST-${g}`,result_id:`RESULT-${g}`,caption_status:"success",generated_caption:`${g} visible process.`,generation_seconds:g==="C"?24:16,input_tokens:20000,generated_tokens:100,peak_gpu_allocated_bytes:{0:2**30},processed_sizes:[[768,640]]}));
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg02_sub01&prompt=v2.camera2");
  await expect(page.getByText("C visible process.",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"并排比较 C / D"}).click();
  await expect(page.getByRole("region",{name:"C 与 D 三维对照"})).toBeVisible();
  await expect(page.getByText("C visible process.",{exact:true})).toBeVisible();
  await expect(page.getByText("D visible process.",{exact:true})).toBeVisible();
  await expect(page.getByText("24.00 秒",{exact:true})).toBeVisible();
  await expect(page.getByText("16.00 秒",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"评价 D 结果"}).click();
  await expect(page.getByLabel("模型运行")).toHaveValue("TEST-D");
  await page.getByLabel("姓名").fill("TEST REVIEWER");
  await page.getByLabel("事实准确性（整体）").selectOption("incorrect");
  await page.getByLabel("关键操作覆盖（动作遗漏）").selectOption("none");
  await page.getByLabel("清楚与规范").selectOption("clear");
  await page.getByLabel("对象是否准确").selectOption("partial");
  await page.getByLabel("动作方向是否准确").selectOption("incorrect");
  await page.getByLabel("最终状态是否准确").selectOption("unknown");
  let captured:any;
  await page.route("**/api/reviews",async route=>{captured=route.request().postDataJSON();await route.fulfill({json:{saved:true}});});
  await page.getByRole("button",{name:"保存评价 →"}).click();
  await expect.poll(()=>captured?.clarity).toBe("clear");
  expect(captured.run_id).toBe("TEST-D");expect(captured.result_id).toBe("RESULT-D");expect(captured.direction_accuracy).toBe("incorrect");
});

test("camera2 only, lazy six-view expansion, retained playback and wider captions",async({page})=>{
  await page.setViewportSize({width:1600,height:1000});
  const mediaRequests:string[]=[];
  page.on("request",request=>{if(request.url().includes("/api/media/"))mediaRequests.push(request.url());});
  await page.goto("/?clip=sample_01_seg02_sub12&prompt=v2.camera2");
  await expect(page.locator(".camera-tile video")).toHaveCount(1);
  await expect(page.locator(".camera-tile h2")).toHaveText("camera2");
  await page.waitForFunction(()=>document.querySelector<HTMLVideoElement>('video[data-camera="camera2"]')!.readyState>=1);
  expect(mediaRequests.length).toBeGreaterThan(0);
  expect(mediaRequests.every(url=>url.includes("camera2"))).toBeTruthy();
  const width=await page.evaluate(()=>({video:document.querySelector(".viewer")!.getBoundingClientRect().width,caption:document.querySelector(".comparison")!.getBoundingClientRect().width}));
  expect(width.caption/width.video).toBeCloseTo(3,1);
  const position=await page.evaluate(()=>{
    const v=document.querySelector<HTMLVideoElement>('video[data-camera="camera2"]')!;
    (window as any).__mainVideo=v;
    v.pause();v.currentTime+=1;return v.currentTime;
  });
  await page.waitForFunction(t=>Math.abs(document.querySelector<HTMLVideoElement>('video[data-camera="camera2"]')!.currentTime-t)<.1,position);
  await page.getByRole("button",{name:"展开全部相机"}).click();
  await expect(page.locator(".camera-tile video")).toHaveCount(6);
  await expect(page.locator(".camera-tile h2")).toHaveText(["camera0","camera1","camera2","camera3","camera4","camera5"]);
  expect(await page.evaluate(()=>document.querySelector('video[data-camera="camera2"]')===(window as any).__mainVideo)).toBeTruthy();
  expect(await page.locator('video[data-camera="camera2"]').evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(position,1);
  await page.waitForFunction(()=>[...document.querySelectorAll<HTMLVideoElement>(".camera-tile video")].every(v=>v.readyState>=1));
  await page.locator(".camera-title").first().click();
  await expect(page).toHaveURL(/prompt=v2.camera2/);
  await page.getByRole("button",{name:"收起其他相机"}).click();
  await expect(page.locator(".camera-tile video")).toHaveCount(1);
  expect(await page.locator('video[data-camera="camera2"]').evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeCloseTo(position,1);
  await page.getByRole("button",{name:"播放视频",exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector<HTMLVideoElement>('video[data-camera="camera2"]')!.paused);
  await page.getByRole("button",{name:"展开全部相机"}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll<HTMLVideoElement>(".camera-tile video")].every(v=>!v.paused));
  await page.getByRole("button",{name:"收起其他相机"}).click();
  expect(await page.locator('video[data-camera="camera2"]').evaluate((v:HTMLVideoElement)=>v.paused)).toBeFalsy();
  await page.getByRole("button",{name:"暂停视频",exact:true}).click();
  await page.getByRole("button",{name:"展开全部相机"}).click();
  await page.locator(".clip-chip").first().click();
  await expect(page.locator(".camera-tile video")).toHaveCount(1);
  await expect(page.getByRole("button",{name:"展开全部相机"})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2)).toBeTruthy();
});

test("Ark video sampling and resources are marked provider-managed", async({page})=>{
  await page.route("**/api/clips",async route=>{
    const response=await route.fetch();const data=await response.json();
    data.runs=[{id:"TEST-ARK",model_key:"doubao",model_label:"豆包",model_name:"doubao-seed-2-1-lite-260915",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",input_mode:"video",sampling_fps:5}];
    data.results=[{task_id:"sample_01_seg02_sub10__camera2",clip_id:"sample_01_seg02_sub10",camera_id:"camera2",run_id:"TEST-ARK",result_id:"TEST-RESULT",caption_status:"success",generated_caption:"Pulls the hanger away.",generation_seconds:6,input_tokens:7000,generated_tokens:80,provider_sampling_known:false,provider_processed_dimensions_known:false,source_video_dimensions:[1600,1300]}];
    await route.fulfill({json:data});
  });
  await page.route("**/api/sampling?**",async route=>route.fulfill({json:{status:"result",frames:[],provider_sampling_known:false,requested_fps:5,video_export:{source_dimensions:[1600,1300],source_frame_count:45,audio:false,bytes:2000000}}}));
  await page.goto("/?clip=sample_01_seg02_sub10&prompt=v2.camera2");
  await page.getByRole("button",{name:"查看 豆包 结果",exact:true}).click();
  await expect(page.getByText("Pulls the hanger away.",{exact:true})).toBeVisible();
  await page.getByText("资源效率",{exact:true}).click();
  await expect(page.getByText("API 请求（含传输）",{exact:true})).toBeVisible();
  await expect(page.getByText("服务端不可见",{exact:true})).toBeVisible();
  await page.getByText("采样输入",{exact:true}).click();
  await expect(page.getByText(/服务端未返回实际抽帧与处理尺寸/)).toBeVisible();
});

test("thinking comparison exposes final captions and phase metrics only",async({page})=>{
  await page.route("**/api/clips",async route=>{
    const response=await route.fetch();const data=await response.json();const task="sample_01_seg02_sub10__camera2";
    data.runs=["off","on"].map(role=>({id:`TEST-THINK-${role}`,model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",thinking:role==="on",thinking_comparison_role:role,experiment_family:"official-qwen38-v2",official_profile:role==="off"?"off":"medium",seed_index:1,experiment_task_ids:[task]}));
    data.results=["off","on"].map(role=>({task_id:task,clip_id:"sample_01_seg02_sub10",camera_id:"camera2",run_id:`TEST-THINK-${role}`,caption_status:"success",generated_caption:`Final caption ${role}.`,generation_seconds:role==="on"?25:10,thinking_tokens:role==="on"?200:0,caption_tokens:90,thinking_seconds:role==="on"?15:0,thinking_decode_seconds:role==="on"?13:0,caption_seconds:10,first_token_seconds:2,thinking_complete:true,caption_complete:true}));
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg02_sub10&prompt=v2.camera2");
  await page.getByRole("button",{name:"并排",exact:true}).click();
  await expect(page.getByRole("region",{name:"thinking 开关对照"})).toBeVisible();
  await expect(page.getByText("Final caption on.",{exact:true})).toBeVisible();
  await expect(page.getByText("Final caption off.",{exact:true})).toBeVisible();
  await page.getByRole("region",{name:"thinking 开关对照"}).getByText("资源效率",{exact:true}).nth(0).click();
  await page.getByRole("region",{name:"thinking 开关对照"}).getByText("资源效率",{exact:true}).nth(1).click();
  await expect(page.getByText("200 / 90",{exact:true})).toBeVisible();
  await expect(page.getByText("0 / 90",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"评价思考结果"}).click();
  await expect(page.getByLabel("模型运行")).toHaveValue("TEST-THINK-on");
});

test("official selection keeps four seed-one modes and reviews the chosen result",async({page})=>{
  await page.addInitScript(()=>localStorage.setItem("sidebarCollapsed","true"));
  await page.route("**/api/clips",async route=>{
    const response=await route.fetch();const data=await response.json();const task="sample_01_seg02_sub10__camera2";
    const runs=[1,2].flatMap(seed=>["off","low","medium","xhigh"].map(profile=>({id:`TEST-${profile}-s${seed}`,model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",experiment_family:"official-qwen38-v2",official_profile:profile,seed_index:seed,reasoning_effort:profile==="off"?null:profile,thinking_comparison_role:profile==="off"?"off":"on",thinking:profile!=="off",experiment_task_ids:[task]})));
    data.runs=[...runs,{id:"LEGACY-on",model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",thinking_comparison_role:"on",experiment_family:"legacy-greedy"}];
    data.results=data.runs.map((run:any)=>({task_id:task,clip_id:"sample_01_seg02_sub10",camera_id:"camera2",run_id:run.id,result_id:`RESULT-${run.id}`,caption_status:"success",generated_caption:`caption ${run.id}`}));
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg02_sub10&prompt=v2.camera2");
  await expect(page.getByRole("group",{name:"思考模式",exact:true}).getByRole("button")).toHaveCount(4);
  await page.getByRole("button",{name:"选择思考模式 low",exact:true}).click();
  await expect(page.getByText("caption TEST-low-s1",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"并排",exact:true}).click();
  await expect(page.getByText("caption TEST-off-s1",{exact:true})).toBeVisible();
  await expect(page.getByText("caption TEST-low-s1",{exact:true})).toBeVisible();
  await expect(page.getByText("caption LEGACY-on",{exact:true})).toHaveCount(0);
  await expect(page.getByLabel("对照随机种子")).toHaveCount(0);
  await expect(page.getByLabel("对照实验批次")).toHaveCount(0);
  await page.getByRole("button",{name:"选择思考模式 xhigh",exact:true}).click();
  await expect(page.getByText("caption TEST-xhigh-s1",{exact:true})).toBeVisible();
  await expect(page.getByText("caption TEST-xhigh-s2",{exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"评价思考结果"}).click();
  await expect(page.getByLabel("模型运行")).toHaveValue("TEST-xhigh-s1");
  await expect(page.locator(".review .panel-title > span")).toBeVisible();
  expect(await page.getByRole("heading",{name:"人工评价"}).evaluate(node=>getComputedStyle(node).writingMode)).toBe("horizontal-tb");
});

test("mentor view fixes v2 while keeping Qwen modes and Doubao", async ({page}) => {
  await page.route("**/api/clips", async route => {
    const response=await route.fetch();const data=await response.json();const task="sample_01_seg02_sub10__camera2";
    data.presentation={mode:"mentor",fixed_prompt_id:"baseline-v2"};
    data.runs=["off","low","medium","xhigh"].map(profile=>({id:`MENTOR-${profile}`,model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",experiment_family:"official-qwen38-v2",official_profile:profile,seed_index:1,experiment_task_ids:[task]}));
    data.runs.push({id:"MENTOR-DOUBAO",model_key:"doubao",model_label:"豆包",model_name:"doubao-seed-2-1-lite-260915",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",experiment_task_ids:[task]});
    data.results=data.runs.map((run:any)=>({task_id:task,clip_id:"sample_01_seg02_sub10",camera_id:"camera2",run_id:run.id,result_id:`RESULT-${run.id}`,caption_status:"success",generated_caption:`caption ${run.id}`}));
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg02_sub10&prompt=v1.camera2");
  await expect(page.getByLabel("Prompt 版本")).toHaveCount(0);
  await expect(page.getByText(/六部分操作描述或其迭代/)).toHaveCount(0);
  await expect(page.getByRole("group",{name:"思考模式",exact:true}).getByRole("button")).toHaveCount(4);
  await expect(page.getByText("caption MENTOR-off",{exact:true})).toBeVisible();
  await expect(page.locator(".experiment-progress")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"查看 豆包 结果"})).toHaveText("doubao-seed-2-1");
  await page.getByRole("button",{name:"选择思考模式 low",exact:true}).click();
  await expect(page.getByText("caption MENTOR-low",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"并排",exact:true}).click();
  await expect(page.getByText("caption MENTOR-off",{exact:true})).toBeVisible();
  await expect(page.getByText("caption MENTOR-low",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"选择思考模式 xhigh",exact:true}).click();
  await expect(page.getByText("caption MENTOR-xhigh",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"评价思考结果"}).click();
  await expect(page.getByLabel("模型运行")).toHaveValue("MENTOR-xhigh");
  await page.getByRole("button",{name:"单组",exact:true}).click();
  await expect(page).toHaveURL(/prompt=v2.camera2/);
  await page.getByRole("button",{name:"查看 豆包 结果"}).click();
  await expect(page.getByText("caption MENTOR-DOUBAO",{exact:true})).toBeVisible();
});

test("mentor checkbox is centered below clips without navigation or card badges", async ({page}) => {
  await page.addInitScript(()=>localStorage.setItem("sidebarCollapsed","false"));
  await page.route("**/api/clips",async route=>{
    const response=await route.fetch();const data=await response.json();
    const ready=["sample_01_seg02_sub01","sample_01_seg02_sub11"];
    data.presentation={mode:"mentor",fixed_prompt_id:"baseline-v2"};
    data.runs=[{id:"FILTER-OFF",model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",experiment_family:"official-qwen38-v2",official_profile:"off",seed_index:1,experiment_task_ids:ready.map(id=>id+"__camera2")},
      {id:"FILTER-DB",model_key:"doubao",model_label:"豆包",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2"}];
    data.results=ready.map(id=>({task_id:id+"__camera2",clip_id:id,camera_id:"camera2",run_id:"FILTER-OFF",caption_status:"success",generated_caption:"Ready "+id}));
    data.results.push({task_id:"sample_01_seg02_sub10__camera2",clip_id:"sample_01_seg02_sub10",camera_id:"camera2",run_id:"FILTER-DB",caption_status:"success",generated_caption:"Doubao ready"});
    await route.fulfill({json:data});
  });
  await page.goto("/?clip=sample_01_seg01_sub01");
  await expect(page.locator(".clip-filter-footer").getByLabel("仅看有结果")).toBeVisible();
  const strip=await page.locator(".clip-strip").boundingBox(), filter=await page.locator(".clip-filter-footer label").boundingBox();
  expect(filter!.y).toBeGreaterThanOrEqual(strip!.y+strip!.height);
  expect(Math.abs(filter!.x+filter!.width/2-strip!.x-strip!.width/2)).toBeLessThan(3);
  await expect(page.getByLabel("快速选择有结果片段")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"跳到首个结果"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"查看已有结果片段"})).toHaveCount(0);
  await expect(page.locator(".result-badge")).toHaveCount(0);
  await expect(page.locator(".clip-chip")).toHaveCount(24);
  await page.getByLabel("仅看有结果").check();
  await expect(page.locator(".clip-chip")).toHaveCount(2);
  await expect(page.locator(".clip-progress")).toHaveText("4 / 24");
  await expect(page.getByText("Ready sample_01_seg02_sub01",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:/sample_01 家庭服务/})).toContainText("24 个片段");
  await expect(page.locator(".clip-card")).toHaveCount(10);
  await page.getByRole("button",{name:"查看 豆包 结果"}).click();
  await expect(page.getByText("Doubao ready",{exact:true})).toBeVisible();
  await expect(page.locator(".clip-chip")).toHaveCount(1);
  await page.getByRole("button",{name:"查看 camera0 结果"}).click();
  await expect(page.getByText("当前样本暂无此模型和相机的结果片段。",{exact:true})).toBeVisible();
  await expect(page.getByLabel("仅看有结果")).toBeVisible();
  await page.getByLabel("仅看有结果").uncheck();
  await expect(page.locator(".clip-chip")).toHaveCount(24);
  await page.getByRole("button",{name:"查看 camera2 结果"}).click();
  await page.getByLabel("仅看有结果").check();
  await page.getByRole("button",{name:/sample_02 家庭服务/}).click();
  await expect(page.getByText("当前样本暂无此模型和相机的结果片段。",{exact:true})).toBeVisible();
  await expect(page.locator(".clip-card")).toHaveCount(10);
  await page.getByLabel("仅看有结果").uncheck();
  await expect(page.locator(".clip-chip")).toHaveCount(8);
});

test("mentor sampling is concise and configuration stays inside equal-sized disclosure",async({page})=>{
  await page.route("**/api/clips",async route=>{
    const response=await route.fetch();const data=await response.json();const task="sample_01_seg02_sub01__camera2";
    data.presentation={mode:"mentor",fixed_prompt_id:"baseline-v2"};
    data.runs=[{id:"SAMPLE-UI",model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",experiment_family:"official-qwen38-v2",official_profile:"off",seed_index:1,input_mode:"video",sampling_fps:6,frame_max_pixels:512000}];
    data.results=[{task_id:task,clip_id:"sample_01_seg02_sub01",camera_id:"camera2",run_id:"SAMPLE-UI",result_id:"SAMPLE-RESULT",caption_status:"success",generated_caption:"Visible operation."}];
    await route.fulfill({json:data});
  });
  await page.route("**/api/sampling?**",async route=>route.fulfill({json:{status:"result",run_id:"SAMPLE-UI",task_id:"sample_01_seg02_sub01__camera2",input_id:"SAMPLE-INPUT",result_id:"SAMPLE-RESULT",display_profile:"jpeg640-v1",source_evidence:{run_id:"qwen-sample01-v2-video-r3"},temporal_evidence:{real_frame_count:42,padding_count:0,groups:[]},frames:Array.from({length:42},(_,i)=>({url:`/TEST-FRAME-${i}.png`,relative_time_s:i/6,source_time_s:18.5+i/6,requested_relative_time_s:i/6,deviation_s:0,processed_size:[768,640]}))}}));
  await page.route("**/TEST-FRAME-*.png",async route=>route.fulfill({contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT5sAAAAASUVORK5CYII=","base64")}));
  await page.goto("/?clip=sample_01_seg02_sub01");
  await expect(page.getByText("Visible operation.",{exact:true})).toBeVisible();
  const model=await page.getByRole("group",{name:"模型",exact:true}).boundingBox();
  const cameras=await page.getByRole("group",{name:"结果相机",exact:true}).boundingBox();
  expect(model!.y+model!.height).toBeLessThan(cameras!.y);
  await expect(page.getByText(/每帧像素预算 512000/)).toHaveCount(0);
  await expect(page.locator(".experiment-progress")).toHaveCount(0);
  const sampling=page.locator(".sampling-input > summary"),resources=page.locator(".caption-details > summary");
  expect(await sampling.evaluate(node=>getComputedStyle(node).fontSize)).toBe(await resources.evaluate(node=>getComputedStyle(node).fontSize));
  await sampling.click();
  await expect(page.locator(".sampling-input .input-configuration")).toContainText("输入：视频序列 · 6 fps · 每帧像素预算 512000");
  await expect(page.getByText(/共 42 帧；时间相对当前原始片段起点/)).toBeVisible();
  await expect(page.getByText(/采样证据复用自：/)).toHaveCount(0);
  await expect(page.getByText(/视频输入时间映射：/)).toHaveCount(0);
  await expect(page.locator(".sampling-grid img")).toHaveCount(42);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2)).toBeTruthy();
});

test("local view keeps experiments with shared controls and concise high-resolution sampling",async({page})=>{
  await page.route("**/api/clips",async route=>{
    const data=await(await route.fetch()).json();delete data.presentation;const task="sample_01_seg02_sub01__camera2";
    data.runs=["off","low","medium","xhigh"].map(profile=>({id:`LOCAL-${profile}`,model_key:"qwen",model_label:"Qwen",model_name:"fixture",prompt_id:"baseline-v2",sample:"sample_01",camera:"camera2",experiment_family:"official-qwen38-v2",official_profile:profile,seed_index:1,input_mode:"video",sampling_fps:6,frame_max_pixels:512000,experiment_task_ids:[task]}));
    data.results=data.runs.map((run:any)=>({task_id:task,clip_id:"sample_01_seg02_sub01",camera_id:"camera2",run_id:run.id,result_id:`RESULT-${run.id}`,caption_status:"success",generated_caption:`Caption ${run.id}`}));
    await route.fulfill({json:data});
  });
  await page.route("**/api/sampling?**",async route=>route.fulfill({json:{status:"result",input_id:"LOCAL-INPUT",source_evidence:{run_id:"old-source"},temporal_evidence:{real_frame_count:1,padding_count:1,groups:[]},frames:[{url:"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT5sAAAAASUVORK5CYII=",relative_time_s:.033,source_time_s:18.533,requested_relative_time_s:0,deviation_s:.033}]}}));
  await page.goto("/?clip=sample_01_seg02_sub01&prompt=v2.camera2");
  await expect(page.getByLabel("Prompt 版本").locator("option")).toHaveCount(2);
  await expect(page.locator(".experiment-progress")).toContainText("已生成 1／1");
  const model=await page.getByRole("group",{name:"模型",exact:true}).boundingBox(),camera=await page.getByRole("group",{name:"结果相机",exact:true}).boundingBox();
  expect(model!.y+model!.height).toBeLessThan(camera!.y);
  await expect(page.locator(".clip-filter-footer").getByLabel("仅看有结果")).toBeVisible();
  await page.getByRole("button",{name:"选择思考模式 low",exact:true}).click();
  await expect(page.getByText("Caption LOCAL-low",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"并排",exact:true}).click();
  await expect(page.getByText("Caption LOCAL-off",{exact:true})).toBeVisible();
  await expect(page.getByText("Caption LOCAL-low",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"单组",exact:true}).click();
  const input=page.locator(".sampling-input > summary"),resource=page.locator(".caption-details > summary");
  expect(await input.evaluate(e=>getComputedStyle(e).fontSize)).toBe(await resource.evaluate(e=>getComputedStyle(e).fontSize));
  await input.click();
  await expect(page.getByText(/图片为保存的高清抽帧/)).toBeVisible();
  await expect(page.getByText("帧 1 · 0.033 秒",{exact:true})).toBeVisible();
  await expect(page.getByText(/采样证据复用自：|视频输入时间映射：/)).toHaveCount(0);
});
