# Caption 执行系统工程契约

本文描述执行系统身份、输入、续跑和存储约束，不定义实验 Prompt 版本。当前 sample_01 v1 见 sample01-experiments.md；执行操作见 harness-usage.md。Qwen 路径已做过工程验证，旧试跑结果已删除；闭源 API 实际端点未验收。执行保守串行，多窗口汇总属于可选能力，跨片段样本摘要、多视角融合及可调并发尚未接入。以下设计字段与后续能力不表示都已实现。

## 范围

按原始 sub_segments_info 区间，对全部六路相机分别生成 caption。不额外拆分，不按 is_success、时间或帧有效性过滤任务。解码失败记录为失败任务。无自动视觉核查；格式校验不证明内容正确。单相机样本摘要是片段描述汇总，多视角摘要暂缓。

## 身份与数据契约

所有记录包含 schema_version。时间单位为秒，原始区间采用源视频时间，帧同时保存片段相对时间和源时间。禁止混用。内容哈希统一 SHA-256。

| 记录 | 必需信息 |
| --- | --- |
| Task | task_id、clip_id、sample_id、camera_id、data_version、原始 start/end、视频身份、源标注引用 |
| Run | run_id、完整配置、代码版本/内容哈希、模型实际身份、Prompt 模块内容与哈希、组装顺序 |
| InputBundle | input_id、task_id、run_id、视觉证据、背景、历史结果、时间关系、最终请求文本与生成参数 |
| Result | result_id、attempt_id、task_id、run_id、input_id、input_fingerprint、状态、原始输出、解析输出或错误、耗时 |
| Review | review_id、task_id、run_id、result_id、评价目标类型、署名、时间、整体准确性、遗漏、分类问题和备注 |
| Summary | summary_id、run_id、sample_id、camera_id、输入 result_id 顺序、覆盖区间/缺失任务、文本、summary_kind=caption_aggregation |

task_id 表示稳定的子片段与相机身份；数据修改由 data_version 和内容身份区分。result_id/attempt_id 使用唯一 ID，不由任务 ID 替代。source_subtask_id 保留到原始标注的映射。

## 输入包

视觉证据保存视频内容哈希、采样器版本、请求采样配置、实际帧时间、帧内容哈希及不可变存储引用。哈希不能恢复文件，复现保留期内必须保留帧或视频及确定的采样实现。缺失解码信息作为诊断，不删任务。

背景模式：none / sample / sample_and_fine_label。分别保存实际背景文本和原始标注版本。fine_label 模式标记为标注辅助实验；不能用同一 fine_label 的匹配程度单独证明视觉正确性。

历史保存原始前驱 task_id、使用的 result_id、实际文本及状态：disabled / first_task / available / missing / failed。前驱有结果但版本不符合策略时不得静默替换。单相机历史不借用其他相机。

时间关系保存 previous/current 原始区间及 gap_s=current_start-previous_end；正值为间隔，负值为重叠。邻接容差需在配置中显式定义，不能根据编号或浮点舍入臆定连续。

input_fingerprint 对最终模型输入做规范化序列化后哈希，覆盖实际有序帧内容与时间、背景、历史 result_id 与文本、最终 Prompt、模型版本、生成参数和处理器版本。不包含提交时间、attempt_id 等非语义字段。内容完全相同仍不能保证远端模型输出确定。

## Prompt 与请求组装

按 observation_scope → context_boundary → continuity → output 顺序组合模块。模型指令与数据区分开；结构化编码任务背景和历史数据，禁止把标注当附加指令。保存实际发送给模型的请求内容/不可变引用，并移除凭据。后端记录 resize 等实际预处理参数。

## 上下文调度

同一样本、同一路相机、同一次运行形成序列。先在完整运行任务域定义前驱，再应用本次执行筛选，避免 limit/局部重跑改变前驱。排序键为原始 start、end、source_subtask_id、task_id；相同时间使用稳定辅助键，不按字符串编号推断时间。

context_missing_policy=continue_without_context 或 wait_for_predecessor；推荐第一版 continue_without_context。前驱失败/未完成时明示缺失，绝不回退更早结果。每条上下文链顺序执行，不同链可并行；无历史实验独立调度。

## 状态、续跑与版本

attempt 状态：pending → running → success / failed；中断可记 interrupted。重启时检查未完成 attempt，不能把 running 当成功。质量未知、上下文变化是独立标记。

相同 input_fingerprint 存在成功结果且所需产物完整时复用；失败尝试保留，重试产生新 attempt/result。run 配置不可变，模型/Prompt/采样/背景模式变化建立新 run。局部重跑保留旧结果，新结果通过显式的 active result 索引选用，不能依赖文件最后一行。

依赖边为 child result_id → parent result_id。前驱活动版本变化后，直接与传递依赖的旧结果标记 context_changed，不覆盖它们。默认只标记；显式 cascade 操作才按顺序重跑后续链。保存标记原因与触发结果。旧评价继续关联旧结果。

一次任务尝试先保存输入，再提交请求，最后提交结果；采用原子写入/事务与任务领取机制避免并发重复执行。网络超时可能已经产生 API 费用，记录 unknown_remote_outcome；不承诺远端 exactly-once，不自动无限重试。设置并发、调用数、重试数和预算上限。

## 输出与格式验证

当前基线输出纯英文文本；执行器包装为 generated_caption。结构化实验可输出 generated_caption、actions、state_changes、uncertainties，后三者允许为空列表。actions 为对象，包含 actor、operation、target、details；state_changes 包含 object、before、after；未知可用 null。动作数组有序，不要求精确动作边界。所有自然语言字段英文，长度预算单独配置，不固定一句话。身份、时间和配置由系统填写，不让模型生成。

格式校验：JSON 类型、必需字段、非空 caption、数组项字段及长度预算；不做语义成功认证。失败保留原始响应和错误，不生成占位成功文本。

## 存储

runs/<run_id>/ 保留 config.json、tasks.jsonl、results.jsonl、metrics.json、run.log；增加 inputs/<input_id>.json、artifacts/、events.jsonl、summaries.jsonl。versions/ 保存结果历史；active.json 选择活动结果，results.jsonl 是其投影，events.jsonl 保存事件。summaries.jsonl 是设计字段，不是当前基线产物。运行索引可重建。大视频仍由配置引用 CFS，不搬迁。API 凭据不进运行记录。

## 人工评价

保持原始标注评价与生成结果评价分开。模型评价必须关联具体 result_id；原始标注评价关联 annotation version。整体准确性、遗漏、备注与姓名，加可多选问题：object_identity、operation、spatial_relation、action_order、unsupported_state_or_outcome、invented_intent_or_causality。各类允许备注。未选表示未报告，不表示通过。页面展示相机、模型、Prompt、背景模式、历史使用和 context_changed。评价不可随文本更新转移。

## 实施与验收顺序

1. 实现 schema、输入包与哈希；固定输入哈希可复现，任何语义输入变化会改变哈希。
2. 实现前驱与缺失策略；覆盖间隔、重叠、相同时间、相机隔离、执行子集不改变前驱。
3. 实现追加版本、任务领取、续跑；覆盖失败、中断、重复启动及局部重跑。
4. 实现依赖变化标记；覆盖直接/传递依赖，确认未自动触发 API 调用。
5. 接入三个模型与看板；评价刷新持久化，旧评价只属于旧结果。
6. 添加单相机文字汇总；保存确切输入版本、缺失区间，不能声称视频核查。

先固定同一模型和视觉证据，对比无背景、sample 背景、sample+fine_label，再独立比较历史上下文。所有条件都不增加自动视觉核查。
