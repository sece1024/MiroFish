"""
Novel API 路由
提供小说创作生成、查询、下载等接口

流程：StoryPlanner → NarrativeSpace → ChapterWriter
"""

import os
import json
import uuid
import traceback
import threading
from datetime import datetime
from flask import request, jsonify, send_file

from . import novel_bp
from ..config import Config
from ..services.story_planner import (
    StoryPlanner,
    StoryPlannerInput,
    CharacterInput,
    StoryPlan,
)
from ..services.narrative_space import NarrativeSpace, StoryResult
from ..services.chapter_writer import ChapterWriter, NovelResult
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.novel")

# 小说文件存储根目录
NOVELS_DIR = os.path.join(Config.UPLOAD_FOLDER, "novels")


# ============================================================
# 工具函数
# ============================================================


def _get_novel_dir(novel_id: str) -> str:
    """获取小说存储目录"""
    return os.path.join(NOVELS_DIR, novel_id)


def _save_novel_meta(novel_id: str, meta: dict):
    """保存小说元信息"""
    novel_dir = _get_novel_dir(novel_id)
    os.makedirs(novel_dir, exist_ok=True)
    with open(os.path.join(novel_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_novel_meta(novel_id: str) -> dict | None:
    """加载小说元信息"""
    meta_path = os.path.join(_get_novel_dir(novel_id), "meta.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _list_novels() -> list:
    """列出所有已生成的小说"""
    if not os.path.exists(NOVELS_DIR):
        return []

    novels = []
    for name in sorted(os.listdir(NOVELS_DIR), reverse=True):
        meta = _load_novel_meta(name)
        if meta:
            novels.append(meta)
    return novels


# ============================================================
# API 路由
# ============================================================


@novel_bp.route("/generate", methods=["POST"])
def generate_novel():
    """
    启动小说生成任务（异步）

    请求（JSON）：
        {
            "outline": "小说大纲文本...",
            "characters": [
                {"name": "角色A", "description": "角色描述"},
                {"name": "角色B", "description": "角色描述"}
            ],
            "genre": "古典言情",            // 可选，默认"现代"
            "chapter_count": 5,             // 可选，默认5
            "rounds_per_scene": 4,          // 可选，默认4
            "target_words_per_chapter": 2500 // 可选，默认2500
        }

    返回：
        {
            "success": true,
            "data": {
                "novel_id": "novel_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "小说生成任务已启动"
            }
        }
    """
    try:
        data = request.get_json() or {}

        # 参数校验
        outline = data.get("outline", "").strip()
        if not outline:
            return jsonify({"success": False, "error": "请提供小说大纲 (outline)"}), 400

        characters_raw = data.get("characters", [])
        if not characters_raw or not isinstance(characters_raw, list):
            return jsonify(
                {"success": False, "error": "请提供角色列表 (characters)"}
            ), 400

        for c in characters_raw:
            if not c.get("name"):
                return jsonify(
                    {"success": False, "error": "每个角色必须包含 name 字段"}
                ), 400

        genre = data.get("genre", "现代")
        chapter_count = int(data.get("chapter_count", 5))
        rounds_per_scene = int(data.get("rounds_per_scene", 4))
        target_words = int(data.get("target_words_per_chapter", 2500))

        # 生成 ID
        novel_id = f"novel_{uuid.uuid4().hex[:12]}"
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="novel_generate", metadata={"novel_id": novel_id}
        )

        # 保存初始元信息
        _save_novel_meta(
            novel_id,
            {
                "novel_id": novel_id,
                "task_id": task_id,
                "status": "generating",
                "title": "",
                "genre": genre,
                "chapter_count": chapter_count,
                "total_word_count": 0,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        )

        # 构造输入
        story_input = StoryPlannerInput(
            outline=outline,
            characters=[
                CharacterInput(name=c["name"], description=c.get("description", ""))
                for c in characters_raw
            ],
            genre=genre,
            chapter_count=chapter_count,
        )

        # 后台任务
        def run_generate():
            try:
                # ========== Step 1: StoryPlanner ==========
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=5,
                    message="[1/3] 故事编排中...",
                )

                planner = StoryPlanner()

                def planner_progress(current, total, msg):
                    pct = 5 + int(current / total * 25)
                    task_manager.update_task(
                        task_id, progress=pct, message=f"[1/3] {msg}"
                    )

                story_plan = planner.plan(
                    story_input, progress_callback=planner_progress
                )

                # 保存 story_plan
                novel_dir = _get_novel_dir(novel_id)
                with open(
                    os.path.join(novel_dir, "story_plan.json"), "w", encoding="utf-8"
                ) as f:
                    json.dump(story_plan.to_dict(), f, ensure_ascii=False, indent=2)

                # ========== Step 2: NarrativeSpace ==========
                task_manager.update_task(
                    task_id, progress=30, message="[2/3] 场景推演中..."
                )

                # 构造角色 persona（使用用户提供的描述，后续可接入 OasisProfileGenerator 扩展）
                character_profiles = {
                    c["name"]: c["description"] for c in story_plan.characters
                }

                narrative = NarrativeSpace(rounds_per_scene=rounds_per_scene)

                def narrative_progress(current, total, msg):
                    pct = 30 + int(current / total * 35)
                    task_manager.update_task(
                        task_id, progress=pct, message=f"[2/3] {msg}"
                    )

                story_result = narrative.run_story(
                    story_plan=story_plan,
                    character_profiles=character_profiles,
                    progress_callback=narrative_progress,
                )

                # 保存 story_result
                with open(
                    os.path.join(novel_dir, "story_result.json"), "w", encoding="utf-8"
                ) as f:
                    json.dump(story_result.to_dict(), f, ensure_ascii=False, indent=2)

                # ========== Step 3: ChapterWriter ==========
                task_manager.update_task(
                    task_id, progress=65, message="[3/3] 章节撰写中..."
                )

                writer = ChapterWriter(target_words_per_chapter=target_words)

                def writer_progress(current, total, msg):
                    pct = 65 + int(current / total * 35)
                    task_manager.update_task(
                        task_id, progress=pct, message=f"[3/3] {msg}"
                    )

                novel_result = writer.write_novel(
                    story_result=story_result,
                    story_plan=story_plan,
                    character_profiles=character_profiles,
                    progress_callback=writer_progress,
                )

                # 保存 novel_result
                with open(
                    os.path.join(novel_dir, "novel.json"), "w", encoding="utf-8"
                ) as f:
                    json.dump(novel_result.to_dict(), f, ensure_ascii=False, indent=2)

                # 保存 Markdown
                md_content = novel_result.to_markdown()
                with open(
                    os.path.join(novel_dir, "novel.md"), "w", encoding="utf-8"
                ) as f:
                    f.write(md_content)

                # 更新元信息
                _save_novel_meta(
                    novel_id,
                    {
                        "novel_id": novel_id,
                        "task_id": task_id,
                        "status": "completed",
                        "title": novel_result.title,
                        "genre": novel_result.genre,
                        "chapter_count": novel_result.total_chapters,
                        "total_word_count": novel_result.total_word_count,
                        "created_at": _load_novel_meta(novel_id).get("created_at", ""),
                        "updated_at": datetime.now().isoformat(),
                    },
                )

                task_manager.complete_task(
                    task_id,
                    {
                        "novel_id": novel_id,
                        "title": novel_result.title,
                        "chapter_count": novel_result.total_chapters,
                        "total_word_count": novel_result.total_word_count,
                    },
                )

                logger.info(
                    f"小说生成完成: {novel_id}, {novel_result.total_chapters}章, "
                    f"{novel_result.total_word_count}字"
                )

            except Exception as e:
                logger.error(f"小说生成失败: {e}\n{traceback.format_exc()}")
                task_manager.fail_task(task_id, str(e))

                # 更新元信息
                meta = _load_novel_meta(novel_id) or {}
                meta["status"] = "failed"
                meta["error"] = str(e)
                meta["updated_at"] = datetime.now().isoformat()
                _save_novel_meta(novel_id, meta)

        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "novel_id": novel_id,
                    "task_id": task_id,
                    "status": "generating",
                    "message": "小说生成任务已启动，请通过 /api/novel/generate/status 查询进度",
                },
            }
        )

    except Exception as e:
        logger.error(f"启动小说生成任务失败: {e}\n{traceback.format_exc()}")
        return jsonify(
            {
                "success": False,
                "error": str(e),
            }
        ), 500


@novel_bp.route("/generate/status", methods=["POST"])
def get_generate_status():
    """
    查询小说生成任务进度

    请求（JSON）：
        {
            "task_id": "task_xxxx"    // 可选
        }
        或
        {
            "novel_id": "novel_xxxx"  // 可选
        }

    返回：
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "novel_id": "novel_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "...",
                "result": { ... }  // 仅在 completed 时返回
            }
        }
    """
    try:
        data = request.get_json() or {}
        task_id = data.get("task_id")
        novel_id = data.get("novel_id")

        # 如果传了 novel_id，从 meta 中查 task_id
        if novel_id and not task_id:
            meta = _load_novel_meta(novel_id)
            if meta:
                task_id = meta.get("task_id")

                # 如果已完成，直接返回 meta
                if meta.get("status") == "completed":
                    return jsonify(
                        {
                            "success": True,
                            "data": {
                                "task_id": task_id,
                                "novel_id": novel_id,
                                "status": "completed",
                                "progress": 100,
                                "message": "小说已生成",
                                "result": {
                                    "novel_id": novel_id,
                                    "title": meta.get("title"),
                                    "chapter_count": meta.get("chapter_count"),
                                    "total_word_count": meta.get("total_word_count"),
                                },
                            },
                        }
                    )

                if meta.get("status") == "failed":
                    return jsonify(
                        {
                            "success": True,
                            "data": {
                                "task_id": task_id,
                                "novel_id": novel_id,
                                "status": "failed",
                                "progress": 0,
                                "message": meta.get("error", "生成失败"),
                            },
                        }
                    )

        if not task_id:
            return jsonify(
                {"success": False, "error": "请提供 task_id 或 novel_id"}
            ), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)

        if not task:
            return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

        return jsonify({"success": True, "data": task.to_dict()})

    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return jsonify(
            {
                "success": False,
                "error": str(e),
            }
        ), 500


@novel_bp.route("/<novel_id>", methods=["GET"])
def get_novel(novel_id):
    """
    获取小说内容（JSON）

    返回：
        {
            "success": true,
            "data": {
                "novel_id": "novel_xxxx",
                "title": "小说标题",
                "genre": "古典言情",
                "chapters": [ ... ],
                "total_word_count": 12500,
                ...
            }
        }
    """
    try:
        novel_dir = _get_novel_dir(novel_id)
        novel_path = os.path.join(novel_dir, "novel.json")

        if not os.path.exists(novel_path):
            return jsonify(
                {"success": False, "error": f"小说不存在或尚未生成完成: {novel_id}"}
            ), 404

        with open(novel_path, "r", encoding="utf-8") as f:
            novel_data = json.load(f)

        return jsonify({"success": True, "data": novel_data})

    except Exception as e:
        logger.error(f"获取小说失败: {e}")
        return jsonify(
            {
                "success": False,
                "error": str(e),
            }
        ), 500


@novel_bp.route("/<novel_id>/download", methods=["GET"])
def download_novel(novel_id):
    """
    下载小说 Markdown 文件
    """
    try:
        md_path = os.path.join(_get_novel_dir(novel_id), "novel.md")

        if not os.path.exists(md_path):
            return jsonify(
                {"success": False, "error": f"小说 Markdown 文件不存在: {novel_id}"}
            ), 404

        meta = _load_novel_meta(novel_id)
        title = meta.get("title", "novel") if meta else "novel"
        safe_title = (
            "".join(c for c in title if c.isalnum() or c in ("_", "-", " ")).strip()
            or "novel"
        )

        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{safe_title}.md",
            mimetype="text/markdown",
        )

    except Exception as e:
        logger.error(f"下载小说失败: {e}")
        return jsonify(
            {
                "success": False,
                "error": str(e),
            }
        ), 500


@novel_bp.route("/list", methods=["GET"])
def list_novels():
    """
    列出所有已生成的小说

    返回：
        {
            "success": true,
            "data": {
                "novels": [
                    {
                        "novel_id": "novel_xxxx",
                        "title": "小说标题",
                        "status": "completed",
                        "chapter_count": 5,
                        "total_word_count": 12500,
                        "created_at": "..."
                    }
                ]
            }
        }
    """
    try:
        novels = _list_novels()
        return jsonify({"success": True, "data": {"novels": novels}})
    except Exception as e:
        logger.error(f"列出小说失败: {e}")
        return jsonify(
            {
                "success": False,
                "error": str(e),
            }
        ), 500
