# StoryPlanner 实现计划

## 目标

新增 StoryPlanner 服务，作为小说创作流程的入口模块。用户输入小说大纲和角色设定，StoryPlanner 将其解析为结构化的场景序列（Scene Sequence），供后续 NarrativeSpace 推演使用。

## 设计原则

1. **复用现有基础设施**：复用 LLMClient、Config、Logger 等工具类
2. **数据驱动**：所有输出为 JSON 序列化的 dataclass，便于持久化和传递
3. **LLM 分步生成**：避免单次生成过长内容导致失败，采用「先拆章→再拆场景」两步策略
4. **与现有流程对齐**：输出格式对齐 `simulation_config_generator.py` 的配置风格

## 文件清单

| 文件 | 操作 |
|---|---|
| `backend/app/services/story_planner.py` | 新建 |
| `backend/tests/test_story_planner.py` | 新建 |

## 数据结构

### Scene（场景）
- `scene_id`: 场景唯一ID
- `chapter`: 所属章节号
- `title`: 场景标题
- `setting`: 场景环境描述（地点+氛围）
- `time_of_day`: 时间（清晨/正午/黄昏/深夜）
- `participating_agents`: 出场角色名称列表
- `conflict`: 本场景核心冲突/目标
- `emotional_arc`: 情绪走向（tension/rising/climax/falling/resolution）
- `narrative_prompt`: 给 Agent 的场景叙事指令摘要

### ChapterOutline（章节大纲）
- `chapter`: 章节号
- `title`: 章节标题
- `summary`: 章节摘要
- `scenes`: 该章节下的场景列表

### StoryPlan（完整故事编排）
- `title`: 小说标题
- `genre`: 风格（武侠/言情/悬疑/科幻/现代...）
- `total_chapters`: 总章节数
- `chapters`: 章节大纲列表
- `characters`: 角色信息列表（姓名+简要描述）
- `plot_threads`: 主线/支线标记

### StoryPlannerInput（输入）
- `outline`: 用户提供的大纲文本
- `characters`: 角色列表（姓名+描述）
- `genre`: 风格偏好
- `chapter_count`: 目标章节数
- `language`: 输出语言（默认中文）

## LLM 调用策略

### Step 1: 章节拆解
- 输入：完整大纲 + 角色列表
- 输出：章节标题 + 每章摘要（100字以内）
- 控制输出长度，降低失败率

### Step 2: 场景拆解（逐章）
- 输入：单章摘要 + 角色列表 + 上下文章节摘要
- 输出：该章下 2-4 个 Scene 定义
- 逐章调用，支持重试

## Prompt 设计要点

- 明确输出 JSON 格式，用 `json.loads` 解析
- 要求每个 Scene 有明确的 conflict 和 emotional_arc
- 强制参与角色必须在 characters 列表中
- emotional_arc 遵循「铺垫→上升→高潮→回落」节奏

## 测试策略

- 使用《红楼梦》片段作为测试输入（项目已有相关 demo）
- 验证输出 JSON 结构完整性
- 验证角色名称一致性
- 验证场景情绪弧线连贯性
