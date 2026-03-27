"""
章节小说生成器 (ChapterWriter)

将 NarrativeSpace 产出的角色交互日志（StoryResult）转化为优美的小说章节文本。
一个章节的所有场景合并为一次 LLM 调用，输出完整的小说正文。
"""

import json
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .narrative_space import StoryResult, SceneResult, NarrativeAction
from .story_planner import StoryPlan

logger = get_logger("mirofish.chapter_writer")


# ============================================================
# 数据结构
# ============================================================


@dataclass
class ChapterNovel:
    """单章小说"""

    chapter: int
    title: str
    content: str
    word_count: int = 0

    def __post_init__(self):
        if self.word_count == 0:
            self.word_count = len(self.content)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        return f"## 第{self.chapter}章 {self.title}\n\n{self.content}\n"


@dataclass
class NovelResult:
    """完整小说"""

    title: str
    genre: str
    chapters: List[ChapterNovel]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_word_count(self) -> int:
        return sum(ch.word_count for ch in self.chapters)

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "genre": self.genre,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "total_word_count": self.total_word_count,
            "total_chapters": self.total_chapters,
            "generated_at": self.generated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        """输出完整 Markdown 格式小说"""
        lines = [
            f"# {self.title}\n",
            f"*{self.genre}* | 共{self.total_chapters}章 | 约{self.total_word_count}字\n",
            "---\n",
        ]
        for ch in self.chapters:
            lines.append(ch.to_markdown())
            lines.append("---\n")
        return "\n".join(lines)


# ============================================================
# Prompt 模板
# ============================================================

CHAPTER_SYSTEM_PROMPT = """你是一位专业的小说作者，擅长「{genre}」风格的写作。

你的任务是将角色交互记录转化为优美的小说章节。

写作要求：
1. 使用第三人称叙述
2. 对话用中文引号「」标注，配合动作描写和心理描写
3. 保留每个角色独特的说话风格和性格特征
4. 目标字数：{target_words}字左右
5. 章节开头要有场景氛围的描写
6. 章末留有悬念或转折，吸引读者继续阅读
7. 段落之间自然过渡，节奏有张有弛

⚠️ 绝对禁止：
- 出现"Agent"、"模拟"、"角色"、"回合"、"轮"等元信息
- 出现"以下是..."、"本章讲述了..."等解说性语言
- 使用 Markdown 标题（#、##等）
- 直接复制粘贴交互记录，必须重新创作"""

CHAPTER_USER_PROMPT = """【小说标题】{story_title}

【第{chapter_num}章】{chapter_title}
章节大纲摘要：{chapter_summary}

【场景信息】
{scene_descriptions}

【角色设定】
{character_profiles}

【角色交互记录】
{action_log}

请将以上交互记录转化为小说正文。
直接输出小说内容，不要加任何解释或标题。"""


# ============================================================
# ChapterWriter 类
# ============================================================


class ChapterWriter:
    """
    章节小说生成器

    将 StoryResult 中的角色交互日志转化为小说章节文本。
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        target_words_per_chapter: int = 2500,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        if llm_client:
            self.llm = llm_client
        else:
            self.llm = LLMClient(
                api_key=api_key or Config.LLM_API_KEY,
                base_url=base_url or Config.LLM_BASE_URL,
                model=model_name or Config.LLM_MODEL_NAME,
            )
        self.target_words = target_words_per_chapter

    def write_novel(
        self,
        story_result: StoryResult,
        story_plan: StoryPlan,
        character_profiles: Dict[str, str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> NovelResult:
        """
        将 StoryResult 转化为完整小说。

        Args:
            story_result: NarrativeSpace 的推演结果
            story_plan: StoryPlanner 的故事编排
            character_profiles: 角色名 → persona 文本
            progress_callback: 进度回调

        Returns:
            NovelResult: 完整小说
        """
        # 按章节分组 SceneResult
        chapters_scenes = self._group_scenes_by_chapter(story_result, story_plan)

        total = len(chapters_scenes)
        logger.info(f"开始小说生成: {story_result.story_title}, {total} 章")

        chapters: List[ChapterNovel] = []

        for idx, (ch_outline, scene_results) in enumerate(chapters_scenes):
            current = idx + 1
            msg = f"撰写第{ch_outline.chapter}章: {ch_outline.title}"
            if progress_callback:
                progress_callback(current, total, msg)
            logger.info(msg)

            content = self._write_chapter(
                story_title=story_result.story_title,
                genre=story_result.genre,
                chapter_outline=ch_outline,
                scene_results=scene_results,
                character_profiles=character_profiles,
                prev_chapter_summary=(chapters[-1].content[:200] if chapters else ""),
            )

            chapters.append(
                ChapterNovel(
                    chapter=ch_outline.chapter,
                    title=ch_outline.title,
                    content=content,
                )
            )

        novel = NovelResult(
            title=story_result.story_title,
            genre=story_result.genre,
            chapters=chapters,
        )

        logger.info(
            f"小说生成完成: {novel.total_chapters} 章, 约 {novel.total_word_count} 字"
        )
        return novel

    # ----------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------

    def _group_scenes_by_chapter(
        self,
        story_result: StoryResult,
        story_plan: StoryPlan,
    ) -> List[tuple]:
        """
        将 SceneResult 按章节分组。

        Returns:
            List[(ChapterOutline, List[SceneResult])]
        """
        # 构建 scene_id → chapter 的映射
        scene_to_chapter: Dict[int, tuple] = {}
        for ch in story_plan.chapters:
            for s in ch.scenes:
                scene_to_chapter[s.scene_id] = ch

        # 按章节分组
        grouped: Dict[int, Dict[str, Any]] = {}
        for sr in story_result.scene_results:
            scene_id = sr.scene.get("scene_id", 0)
            ch_outline = scene_to_chapter.get(scene_id)
            if ch_outline is None:
                # 回退：用 scene 中的 chapter 字段
                ch_num = sr.scene.get("chapter", 1)
                # 找到对应的 chapter outline
                ch_outline = next(
                    (ch for ch in story_plan.chapters if ch.chapter == ch_num),
                    story_plan.chapters[0] if story_plan.chapters else None,
                )
            if ch_outline is None:
                continue
            key = ch_outline.chapter
            if key not in grouped:
                grouped[key] = {"outline": ch_outline, "scenes": []}
            grouped[key]["scenes"].append(sr)

        # 按章节号排序
        result = []
        for ch_num in sorted(grouped.keys()):
            g = grouped[ch_num]
            result.append((g["outline"], g["scenes"]))
        return result

    def _write_chapter(
        self,
        story_title: str,
        genre: str,
        chapter_outline,
        scene_results: List[SceneResult],
        character_profiles: Dict[str, str],
        prev_chapter_summary: str,
    ) -> str:
        """撰写单章小说"""
        # 1. 构建场景描述
        scene_descriptions = self._format_scene_descriptions(scene_results)

        # 2. 构建角色设定（只取本章出场角色）
        involved_chars = set()
        for sr in scene_results:
            involved_chars.update(sr.scene.get("participating_characters", []))
        char_profiles_text = self._format_character_profiles(
            involved_chars, character_profiles
        )

        # 3. 构建交互日志
        action_log = self._format_action_log(scene_results)

        # 4. 调用 LLM
        system = CHAPTER_SYSTEM_PROMPT.format(
            genre=genre,
            target_words=self.target_words,
        )
        user = CHAPTER_USER_PROMPT.format(
            story_title=story_title,
            chapter_num=chapter_outline.chapter,
            chapter_title=chapter_outline.title,
            chapter_summary=chapter_outline.summary,
            scene_descriptions=scene_descriptions,
            character_profiles=char_profiles_text,
            action_log=action_log,
        )

        try:
            content = self.llm.chat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.8,
                max_tokens=4096,
            )
            content = self._clean_content(content)
        except Exception as e:
            logger.warning(f"第{chapter_outline.chapter}章生成失败: {e}")
            content = f"（第{chapter_outline.chapter}章生成失败：{e}）"

        return content

    def _format_scene_descriptions(self, scene_results: List[SceneResult]) -> str:
        """格式化场景描述"""
        lines = []
        for idx, sr in enumerate(scene_results):
            scene = sr.scene
            lines.append(
                f"场景{idx + 1}「{scene.get('title', '')}」："
                f"{scene.get('setting', '')}，{scene.get('time_of_day', '')}。"
                f"核心冲突：{scene.get('conflict', '')}"
            )
            if sr.summary:
                lines.append(f"  → 摘要：{sr.summary}")
        return "\n".join(lines)

    def _format_character_profiles(
        self, char_names: set, profiles: Dict[str, str]
    ) -> str:
        """格式化角色设定（截断到 300 字以内）"""
        lines = []
        for name in char_names:
            persona = profiles.get(name, "（无详细设定）")
            # 截断过长的 persona
            if len(persona) > 300:
                persona = persona[:300] + "..."
            lines.append(f"- {name}：{persona}")
        return "\n".join(lines) if lines else "（无角色信息）"

    def _format_action_log(self, scene_results: List[SceneResult]) -> str:
        """格式化交互日志"""
        lines = []
        for sr in scene_results:
            scene_title = sr.scene.get("title", "场景")
            lines.append(f"【{scene_title}】")
            for a in sr.actions:
                if a.action_type == "speak":
                    target = f" 对 {a.target_name}" if a.target_name else ""
                    emotion = f"（{a.emotion}）" if a.emotion else ""
                    lines.append(
                        f"  {a.agent_name} 说{target}{emotion}：「{a.content}」"
                    )
                elif a.action_type == "think":
                    lines.append(f"  {a.agent_name} 心想：{a.content}")
                elif a.action_type == "act":
                    emotion = f"（{a.emotion}）" if a.emotion else ""
                    lines.append(f"  {a.agent_name}{emotion}：{a.content}")
                elif a.action_type == "react":
                    target = f"（对 {a.target_name}）" if a.target_name else ""
                    lines.append(f"  {a.agent_name} 反应{target}：{a.content}")
                elif a.action_type == "observe":
                    lines.append(f"  {a.agent_name} 观察：{a.content}")
                else:
                    lines.append(f"  {a.agent_name}：{a.content}")
            lines.append("")
        return "\n".join(lines)

    def _clean_content(self, content: str) -> str:
        """清理 LLM 输出中的多余格式"""
        # 移除 think 标签
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        # 移除可能的 Markdown 标题
        content = re.sub(r"^#{1,4}\s+.*\n?", "", content, flags=re.MULTILINE)
        # 移除开头的空行
        content = content.lstrip("\n")
        return content
