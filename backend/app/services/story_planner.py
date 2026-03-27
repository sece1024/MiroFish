"""
故事编排器 (Story Planner)

将用户输入的小说大纲和角色设定，解析为结构化的场景序列。
采用两步策略：
1. 章节拆解：将大纲拆为 N 个章节的大纲
2. 场景拆解：逐章将章节拆为 2-4 个具体场景

输出 StoryPlan 供后续 NarrativeSpace 推演使用。
"""

import json
import re
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.story_planner")


# ============================================================
# 数据结构
# ============================================================


@dataclass
class CharacterInput:
    """用户输入的单个角色"""

    name: str
    description: str  # 角色简要描述


@dataclass
class Scene:
    """单个场景定义"""

    scene_id: int
    chapter: int
    title: str
    setting: str  # 地点 + 氛围
    time_of_day: str  # 清晨/正午/黄昏/深夜
    participating_characters: List[str]  # 出场角色名称
    conflict: str  # 核心冲突/目标
    emotional_arc: str  # tension/rising/climax/falling/resolution
    narrative_hint: str  # 给 Agent 的叙事指令摘要

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChapterOutline:
    """章节大纲"""

    chapter: int
    title: str
    summary: str
    scenes: List[Scene] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scenes"] = [s.to_dict() if isinstance(s, Scene) else s for s in self.scenes]
        return d


@dataclass
class StoryPlan:
    """完整故事编排"""

    title: str
    genre: str
    total_chapters: int
    characters: List[Dict[str, str]]  # [{name, description}, ...]
    chapters: List[ChapterOutline]
    plot_threads: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "genre": self.genre,
            "total_chapters": self.total_chapters,
            "characters": self.characters,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "plot_threads": self.plot_threads,
            "generated_at": self.generated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class StoryPlannerInput:
    """故事编排器输入"""

    outline: str
    characters: List[CharacterInput]
    genre: str = "现代"
    chapter_count: int = 5
    language: str = "中文"


# ============================================================
# Prompt 模板
# ============================================================

CHAPTER_DECOMPOSE_SYSTEM = """你是一位专业的小说编剧和故事架构师。
你的任务是将粗略的大纲拆解为结构化的章节大纲。

输出要求：
- 严格输出 JSON 格式
- 每个章节有明确的标题和 100 字以内的摘要
- 章节之间要有起承转合的节奏感
- 最后一个章节要有收束感"""

CHAPTER_DECOMPOSE_USER = """请将以下小说大纲拆解为 {chapter_count} 个章节。

【小说风格】{genre}

【大纲】
{outline}

【角色列表】
{characters_desc}

请输出严格 JSON 格式：
{{
  "title": "小说标题（基于大纲推断一个合适的标题）",
  "chapters": [
    {{
      "chapter": 1,
      "title": "第一章标题",
      "summary": "本章摘要（100字以内，描述主要事件和出场角色）"
    }}
  ],
  "plot_threads": ["主线：...", "支线：..."]
}}"""

SCENE_DECOMPOSE_SYSTEM = """你是一位专业的小说场景设计师。
你的任务是将章节大纲拆解为具体的小说场景。

要求：
- 每章 2-4 个场景
- 每个场景必须有明确的核心冲突
- 情绪弧线遵循：铺垫→上升→高潮→回落 的节奏
- 出场角色必须在给定的角色列表中
- 输出严格 JSON"""

SCENE_DECOMPOSE_USER = """请将第 {chapter_num} 章拆解为具体场景。

【第 {chapter_num} 章：{chapter_title}】
{chapter_summary}

【上一章概要】
{prev_chapter_summary}

【可出场角色】
{characters_desc}

请输出严格 JSON 格式：
{{
  "scenes": [
    {{
      "scene_id": {scene_start_id},
      "chapter": {chapter_num},
      "title": "场景标题",
      "setting": "地点描述，包含环境氛围",
      "time_of_day": "清晨/正午/黄昏/深夜",
      "participating_characters": ["角色名1", "角色名2"],
      "conflict": "本场景核心冲突或要推进的事件",
      "emotional_arc": "tension/rising/climax/falling/resolution",
      "narrative_hint": "一句话描述本场景的叙事目标，给 Agent 参考"
    }}
  ]
}}"""


# ============================================================
# StoryPlanner 类
# ============================================================


class StoryPlanner:
    """
    故事编排器

    将用户输入的大纲和角色设定，解析为结构化的场景序列（StoryPlan）。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    # ----------------------------------------------------------
    # 公开接口
    # ----------------------------------------------------------

    def plan(
        self,
        story_input: StoryPlannerInput,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> StoryPlan:
        """
        根据输入生成完整的故事编排。

        Args:
            story_input: 大纲 + 角色 + 风格等输入
            progress_callback: 进度回调 (current, total, message)

        Returns:
            StoryPlan: 完整的故事编排
        """
        logger.info(
            f"开始故事编排: 风格={story_input.genre}, 章节数={story_input.chapter_count}"
        )

        total_steps = 1 + story_input.chapter_count  # 1 步章节拆解 + N 步场景拆解
        current_step = 0

        def report(msg: str):
            nonlocal current_step
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, msg)
            logger.info(f"[{current_step}/{total_steps}] {msg}")

        characters_desc = self._format_characters(story_input.characters)

        # Step 1: 章节拆解
        report("拆解章节结构...")
        chapter_result = self._decompose_chapters(
            outline=story_input.outline,
            characters_desc=characters_desc,
            genre=story_input.genre,
            chapter_count=story_input.chapter_count,
        )

        title = chapter_result.get("title", "未命名小说")
        raw_chapters = chapter_result.get("chapters", [])
        plot_threads = chapter_result.get("plot_threads", [])

        # Step 2: 逐章场景拆解
        chapters: List[ChapterOutline] = []
        scene_id_counter = 1

        for idx, raw_ch in enumerate(raw_chapters):
            ch_num = raw_ch.get("chapter", idx + 1)
            ch_title = raw_ch.get("title", f"第{ch_num}章")
            ch_summary = raw_ch.get("summary", "")

            prev_summary = ""
            if idx > 0:
                prev_summary = raw_chapters[idx - 1].get("summary", "")

            report(f"拆解第{ch_num}章场景: {ch_title}")

            scene_result = self._decompose_scenes(
                chapter_num=ch_num,
                chapter_title=ch_title,
                chapter_summary=ch_summary,
                prev_chapter_summary=prev_summary,
                characters_desc=characters_desc,
                scene_start_id=scene_id_counter,
            )

            raw_scenes = scene_result.get("scenes", [])
            scenes = []
            for s in raw_scenes:
                s["scene_id"] = scene_id_counter
                scenes.append(
                    Scene(**{k: s.get(k) for k in Scene.__dataclass_fields__ if k in s})
                )
                # 用构造后的 scene_id（确保一致）
                scenes[-1].scene_id = scene_id_counter
                scene_id_counter += 1

            chapters.append(
                ChapterOutline(
                    chapter=ch_num,
                    title=ch_title,
                    summary=ch_summary,
                    scenes=scenes,
                )
            )

        plan = StoryPlan(
            title=title,
            genre=story_input.genre,
            total_chapters=len(chapters),
            characters=[
                {"name": c.name, "description": c.description}
                for c in story_input.characters
            ],
            chapters=chapters,
            plot_threads=plot_threads,
        )

        logger.info(
            f"故事编排完成: {plan.total_chapters}章, "
            f"{sum(len(ch.scenes) for ch in plan.chapters)}个场景"
        )
        return plan

    # ----------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------

    def _decompose_chapters(
        self,
        outline: str,
        characters_desc: str,
        genre: str,
        chapter_count: int,
    ) -> Dict[str, Any]:
        """Step 1: 将大纲拆解为章节"""
        prompt = CHAPTER_DECOMPOSE_USER.format(
            chapter_count=chapter_count,
            genre=genre,
            outline=outline,
            characters_desc=characters_desc,
        )
        return self._call_llm_with_retry(
            prompt=prompt,
            system_prompt=CHAPTER_DECOMPOSE_SYSTEM,
        )

    def _decompose_scenes(
        self,
        chapter_num: int,
        chapter_title: str,
        chapter_summary: str,
        prev_chapter_summary: str,
        characters_desc: str,
        scene_start_id: int,
    ) -> Dict[str, Any]:
        """Step 2: 将单章拆解为场景"""
        prompt = SCENE_DECOMPOSE_USER.format(
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            chapter_summary=chapter_summary,
            prev_chapter_summary=prev_chapter_summary or "（无，这是第一章）",
            characters_desc=characters_desc,
            scene_start_id=scene_start_id,
        )
        return self._call_llm_with_retry(
            prompt=prompt,
            system_prompt=SCENE_DECOMPOSE_SYSTEM,
        )

    def _format_characters(self, characters: List[CharacterInput]) -> str:
        """格式化角色列表为文本"""
        lines = []
        for c in characters:
            lines.append(f"- {c.name}：{c.description}")
        return "\n".join(lines) if lines else "（无角色信息）"

    # ----------------------------------------------------------
    # LLM 调用（带重试 + JSON 修复）
    # ----------------------------------------------------------

    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """
        带重试的 LLM 调用，包含 JSON 修复逻辑。
        沿用 simulation_config_generator 的模式。
        """
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1),
                    max_tokens=4096,
                )

                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

                if finish_reason == "length":
                    logger.warning(f"LLM输出被截断 (attempt {attempt + 1})")
                    content = self._fix_truncated_json(content)

                # 清理 think 标签（部分推理模型会输出）
                content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"JSON解析失败 (attempt {attempt + 1}): {str(e)[:80]}"
                    )
                    fixed = self._try_fix_json(content)
                    if fixed:
                        return fixed
                    last_error = e

            except Exception as e:
                logger.warning(f"LLM调用失败 (attempt {attempt + 1}): {str(e)[:80]}")
                last_error = e
                time.sleep(2 * (attempt + 1))

        raise last_error or Exception("LLM调用失败")

    def _fix_truncated_json(self, content: str) -> str:
        """修复被截断的 JSON"""
        content = content.strip()

        open_braces = content.count("{") - content.count("}")
        open_brackets = content.count("[") - content.count("]")

        if content and content[-1] not in '",}]':
            content += '"'

        content += "]" * open_brackets
        content += "}" * open_braces

        return content

    def _try_fix_json(self, content: str) -> Optional[Dict[str, Any]]:
        """尝试修复 JSON"""
        content = self._fix_truncated_json(content)

        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            json_str = json_match.group()

            # 移除字符串中的换行符
            def fix_string(match):
                s = match.group(0)
                s = s.replace("\n", " ").replace("\r", " ")
                s = re.sub(r"\s+", " ", s)
                return s

            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)

            try:
                return json.loads(json_str)
            except Exception:
                json_str = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", json_str)
                json_str = re.sub(r"\s+", " ", json_str)
                try:
                    return json.loads(json_str)
                except Exception:
                    pass

        return None
