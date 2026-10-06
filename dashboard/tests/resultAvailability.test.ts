import { describe, it, expect } from "vitest";
import { availableClipIds, chooseRun } from "../src/resultAvailability";
import type { Clip, Data, Run, Result } from "../src/types";

const clip = (sample: string, part: string): Clip => ({clip_id:`${sample}_${part}`,sample_id:sample,domain:"test",scenario:"test",bold_mark:"",subtask_label:"",segment_label:"",clip_start_time_s:0,clip_end_time_s:1,clip_duration_s:1});
const a=clip("sample_01","seg01_sub01"),b=clip("sample_01","seg01_sub02"),c=clip("sample_02","seg01_sub01");
const run = (id: string, profile: string, sample="sample_01"): Run => ({id,model_key:"qwen",model_name:"fixture",model_label:"Qwen",prompt_id:"baseline-v2",sample,experiment_family:"official-qwen38-v2",official_profile:profile,seed_index:1});
const result = (run_id: string, clip: Clip, camera="camera2", status="success"): Result => ({task_id:`${clip.clip_id}__${camera}`,clip_id:clip.clip_id,camera_id:camera,run_id,caption_status:status,generated_caption:"Action"});
const fixture = (): Data => ({version:"mcap-v2",clips:[a,b,c],tasks:[],reviews:[],runs:[run("off","off"),run("low","low"),run("off-sample2","off","sample_02"),run("low-sample2","low","sample_02"),{...run("doubao",""),model_key:"doubao",experiment_family:undefined}, {...run("v1",""),prompt_id:"baseline-v1"}],results:[result("off",a),result("off",b,"camera2","failed"),result("off",b,"camera0"),result("low",b),result("low-sample2",c),result("doubao",b),result("v1",b)]});

describe("Result navigation uses actual successful output in the selected scope",()=>{
  it("does not mark failed/planned tasks, another mode, or another camera as available",()=>{
    expect([...availableClipIds(fixture(),"qwen","baseline-v2","camera2","")]).toEqual([a.clip_id]);
    expect([...availableClipIds(fixture(),"qwen","baseline-v2","camera0","")]).toEqual([b.clip_id]);
  });
  it("follows model and prompt changes",()=>{
    expect([...availableClipIds(fixture(),"doubao","baseline-v2","camera2","")]).toEqual([b.clip_id]);
    expect([...availableClipIds(fixture(),"qwen","baseline-v1","camera2","")]).toEqual([b.clip_id]);
  });
  it("preserves the selected official mode across sample-specific runs",()=>{
    expect(chooseRun(fixture().runs,"sample_02","low")?.id).toBe("low-sample2");
    expect([...availableClipIds(fixture(),"qwen","baseline-v2","camera2","low")]).toEqual([b.clip_id,c.clip_id]);
  });
  it("has no results when the selected camera has no output",()=>{
    expect(availableClipIds(fixture(),"qwen","baseline-v2","camera5","low").size).toBe(0);
  });
});
