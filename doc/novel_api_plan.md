# Novel API 实现计划

## 目标

将 StoryPlanner → NarrativeSpace → ChapterWriter 串联为一个 `/api/novel/generate` 接口，
支持异步生成、进度查询、结果获取和下载。

## API 设计

### POST /api/novel/generate
启动小说生成任务（异步）。

请求：
```json
{
  "outline": "小说大纲文本...",
  "characters": [
    {"name": "角色A", "description": "角色描述"},
    {"name": "角色B", "description": "角色描述"}
  ],
  "genre": "古典言情",
  "chapter_count": 5,
  "rounds_per_scene": 4,
  "target_words_per_chapter": 2500
}
```

返回：
```json
{
  "success": true,
  "data": {
    "novel_id": "novel_xxxx",
    "task_id": "task_xxxx",
    "status": "generating"
  }
}
```

### POST /api/novel/generate/status
查询生成进度。

请求：`{"task_id": "task_xxxx"}` 或 `{"novel_id": "novel_xxxx"}`

### GET /api/novel/<novel_id>
获取小说内容（JSON）。

### GET /api/novel/<novel_id>/download
下载 Markdown 文件。

### GET /api/novel/list
列出所有已生成的小说。

## 文件持久化

```
uploads/novels/<novel_id>/
  meta.json          # 元信息（标题、状态、章节数等）
  story_plan.json    # StoryPlanner 输出
  story_result.json  # NarrativeSpace 输出
  novel.json         # ChapterWriter 完整输出
  novel.md           # Markdown 格式小说
```

## 文件清单

| 文件 | 操作 |
|---|---|
| `backend/app/api/novel.py` | 新建 |
| `backend/app/api/__init__.py` | 修改（注册 blueprint） |
| `backend/app/__init__.py` | 修改（注册 URL prefix） |
