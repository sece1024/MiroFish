# NarrativeSpace 实现计划

## 目标

创建小说叙事空间环境，替代 OASIS 的 Twitter/Reddit 平台。在每个 Scene 中，让角色 Agent 以小说身份进行交互，产出叙事动作（对话、内心独白、行为等）。

## 设计思路

**不依赖 OASIS 引擎**，而是实现一个轻量级的叙事循环：
- OASIS 是为社交媒体模拟设计的（post/comment/like/follow）
- 小说叙事需要不同的动作空间（speak/think/act/react/observe）
- 核心机制相同：LLM + Agent Persona + 上下文 → 生成行为

## 数据结构

### NarrativeAction（叙事动作）
- `agent_id`: 角色ID
- `agent_name`: 角色名称
- `action_type`: speak/think/act/react/observe
- `content`: 动作内容（对话文本/内心独白/动作描述）
- `target_name`: 动作对象（可选）
- `emotion`: 情绪标签（可选）

### SceneResult（场景推演结果）
- `scene`: Scene 信息
- `actions`: List[NarrativeAction]
- `summary`: 场景摘要（LLM 生成）

## 核心类：NarrativeEnvironment

### 输入
- `scene`: StoryPlanner 的 Scene 对象
- `character_profiles`: Dict[角色名 → persona 文本]
- `llm_client`: LLMClient 实例
- `rounds_per_scene`: 每场景轮数（默认 4）
- `genre`: 小说风格

### 执行流程
```
for round in rounds:
    for character in scene.participating_characters:
        context = build_context(character, scene, previous_actions)
        action = llm_generate_action(character.persona, context)
        actions.append(action)
return SceneResult(scene, actions, summary)
```

## LLM Prompt 策略

### Agent 行为生成 Prompt
- System: 角色完整 persona
- User: 场景信息 + 此前交互 + 指令
- 输出: JSON {type, content, target, emotion}

### 场景摘要 Prompt
- 在场景结束后，调用 LLM 生成一句话摘要
- 用于跨场景的上下文传递

## 文件清单

| 文件 | 操作 |
|---|---|
| `backend/app/services/narrative_space.py` | 新建 |
| `backend/scripts/test_narrative_space.py` | 新建 |
| `doc/narrative_space_plan.md` | 新建（本文件） |
