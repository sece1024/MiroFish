# ChapterWriter 实现计划

## 目标

将 NarrativeSpace 产出的 StoryResult（角色交互日志）转化为优美的小说章节文本。

## 输入

- `StoryResult`: 包含所有场景的交互日志和摘要
- `StoryPlan`: 包含章节结构和角色信息
- `genre`: 小说风格（影响写作 prompt）

## 输出

- `ChapterNovel`: 单章小说文本
  - `chapter`: 章节号
  - `title`: 章节标题
  - `content`: 小说正文（2000-4000 字）
  - `word_count`: 字数
- `NovelResult`: 完整小说
  - `title`: 小说标题
  - `chapters`: List[ChapterNovel]
  - `total_word_count`: 总字数
  - `to_markdown()`: 输出完整 Markdown

## LLM 策略

- 将同章节的多个 Scene 的 actions 合并为一个 action log
- 一个章节 = 一次 LLM 调用
- Prompt 强调：第三人称、对话引号、动作描写、心理描写
- 禁止出现 Agent/模拟等元信息

## 文件清单

| 文件 | 操作 |
|---|---|
| `backend/app/services/chapter_writer.py` | 新建 |
| `backend/scripts/test_chapter_writer.py` | 新建 |
| `doc/chapter_writer_plan.md` | 本文件 |
