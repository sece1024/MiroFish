"""
叙事空间 (NarrativeSpace)

替代 OASIS 的 Twitter/Reddit 平台，为小说创作提供叙事环境。
在每个 Scene 中，让角色 Agent 以小说身份进行交互，产出叙事动作。
"""

import json
import re
import time
import random
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .story_planner import Scene, StoryPlan

logger = get_logger("mirofish.narrative_space")


# ============================================================
# 数据结构
# ============================================================


@dataclass
class NarrativeAction:
    """单个叙事动作"""

    round_num: int
    agent_name: str
    action_type: str  # speak / think / act / react / observe
    content: str
    target_name: Optional[str] = None
    emotion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SceneResult:
    """单个场景的推演结果"""

    scene: Dict[str, Any]  # Scene.to_dict()
    actions: List[NarrativeAction]
    summary: str  # LLM 生成的场景摘要

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene": self.scene,
            "actions": [a.to_dict() for a in self.actions],
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class StoryResult:
    """完整小说推演结果"""

    story_title: str
    genre: str
    scene_results: List[SceneResult]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "story_title": self.story_title,
            "genre": self.genre,
            "scene_results": [sr.to_dict() for sr in self.scene_results],
            "generated_at": self.generated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @property
    def total_actions(self) -> int:
        return sum(len(sr.actions) for sr in self.scene_results)


# ============================================================
# Prompt 模板
# ============================================================

ACTION_SYSTEM_PROMPT = """你是「{character_name}」。以下是你完整的人设信息：
{persona}

你必须完全按照这个角色的性格、说话风格和行为模式来行动。"""

ACTION_USER_PROMPT = """【当前场景】
地点：{setting}
时间：{time_of_day}
核心冲突：{conflict}
情绪氛围：{emotional_arc}
叙事目标：{narrative_hint}

【此前发生的事情】
{context}

现在是第 {round_num} 轮互动。

请以「{character_name}」的身份做出反应。你可以选择以下行为之一：
- speak: 说一句话（直接引语，用角色特有的说话方式）
- think: 内心独白（角色的想法和感受）
- act: 执行一个动作（肢体行为、表情、姿态）
- react: 对他人的言行做出即时反应
- observe: 观察环境或他人，为后续行为铺垫

输出严格 JSON 格式：
{{"type": "speak", "content": "角色说的话或做的事", "target": "对话对象名或null", "emotion": "当前情绪"}}"""

SUMMARY_SYSTEM_PROMPT = "你是一位专业的小说编辑，擅长用简洁的语言概括场景。"

SUMMARY_USER_PROMPT = """请根据以下场景中的角色交互记录，生成一句话场景摘要（30字以内）。

场景：{setting}
核心冲突：{conflict}

交互记录：
{action_log}

输出格式：{{"summary": "一句话摘要"}}"""


# ============================================================
# NarrativeEnvironment — 单场景推演引擎
# ============================================================


class NarrativeEnvironment:
    """
    叙事环境

    为单个 Scene 创建叙事空间，管理在场角色的交互。
    不依赖 OASIS，直接用 LLM 驱动角色行为。
    """

    def __init__(
        self,
        scene: Scene,
        character_profiles: Dict[str, str],  # name → persona
        llm_client: LLMClient,
        rounds_per_scene: int = 4,
    ):
        self.scene = scene
        self.character_profiles = character_profiles
        self.llm = llm_client
        self.rounds = rounds_per_scene
        self.actions: List[NarrativeAction] = []

    async def run(self) -> SceneResult:
        """
        运行场景推演。

        每轮遍历所有出场角色，让每个角色生成一个叙事动作。
        """
        logger.info(
            f"开始场景推演: [{self.scene.title}] "
            f"角色={self.scene.participating_characters} "
            f"轮数={self.rounds}"
        )

        for round_num in range(1, self.rounds + 1):
            # 每轮打乱角色顺序，增加叙事随机性
            characters = list(self.scene.participating_characters)
            random.shuffle(characters)

            for char_name in characters:
                persona = self.character_profiles.get(char_name, "")
                if not persona:
                    logger.warning(f"角色 {char_name} 缺少 persona，跳过")
                    continue

                action = self._generate_action(char_name, persona, round_num)
                if action:
                    self.actions.append(action)

        # 生成场景摘要
        summary = self._generate_summary()

        logger.info(f"场景推演完成: [{self.scene.title}] {len(self.actions)} 个动作")

        return SceneResult(
            scene=self.scene.to_dict(),
            actions=self.actions,
            summary=summary,
        )

    def _generate_action(
        self, char_name: str, persona: str, round_num: int
    ) -> Optional[NarrativeAction]:
        """让单个角色在当前场景中做出行为"""
        context = self._build_context(char_name)

        system = ACTION_SYSTEM_PROMPT.format(
            character_name=char_name,
            persona=persona,
        )
        user = ACTION_USER_PROMPT.format(
            setting=self.scene.setting,
            time_of_day=self.scene.time_of_day,
            conflict=self.scene.conflict,
            emotional_arc=self.scene.emotional_arc,
            narrative_hint=self.scene.narrative_hint,
            context=context,
            round_num=round_num,
            character_name=char_name,
        )

        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.8,
                max_tokens=1024,
            )
        except Exception as e:
            logger.warning(f"角色 {char_name} 第{round_num}轮动作生成失败: {e}")
            return None

        action_type = result.get("type", "speak")
        content = result.get("content", "")
        target = result.get("target")
        emotion = result.get("emotion")

        if not content:
            return None

        return NarrativeAction(
            round_num=round_num,
            agent_name=char_name,
            action_type=action_type,
            content=content,
            target_name=target,
            emotion=emotion,
        )

    def _build_context(self, current_char: str) -> str:
        """
        构建当前角色的上下文。
        将此前的动作序列化为可读文本。
        """
        if not self.actions:
            return "（场景刚刚开始，还没有发生任何事情）"

        lines = []
        for a in self.actions[-8:]:  # 只取最近 8 条，避免上下文过长
            prefix = f"第{a.round_num}轮 | {a.agent_name}"
            if a.action_type == "speak":
                target_str = f" 对 {a.target_name}" if a.target_name else ""
                emotion_str = f"（{a.emotion}）" if a.emotion else ""
                lines.append(f"{prefix} 说{target_str}{emotion_str}：「{a.content}」")
            elif a.action_type == "think":
                lines.append(f"{prefix} 心想：{a.content}")
            elif a.action_type == "act":
                emotion_str = f"（{a.emotion}）" if a.emotion else ""
                lines.append(f"{prefix}{emotion_str}：{a.content}")
            elif a.action_type == "react":
                target_str = f"（对 {a.target_name}）" if a.target_name else ""
                lines.append(f"{prefix} 反应{target_str}：{a.content}")
            elif a.action_type == "observe":
                lines.append(f"{prefix} 观察到：{a.content}")
            else:
                lines.append(f"{prefix}：{a.content}")

        return "\n".join(lines)

    def _generate_summary(self) -> str:
        """生成场景摘要"""
        if not self.actions:
            return f"{self.scene.setting}中，一切静悄悄的。"

        action_log = "\n".join(
            f"- {a.agent_name}[{a.action_type}]: {a.content[:80]}" for a in self.actions
        )

        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": SUMMARY_USER_PROMPT.format(
                            setting=self.scene.setting,
                            conflict=self.scene.conflict,
                            action_log=action_log,
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=256,
            )
            return result.get("summary", "")
        except Exception as e:
            logger.warning(f"场景摘要生成失败: {e}")
            return f"{self.scene.setting}中，{len(self.actions)}件事发生。"


# ============================================================
# NarrativeSpace — 完整故事推演编排器
# ============================================================


class NarrativeSpace:
    """
    叙事空间编排器

    接收 StoryPlan，按顺序执行所有场景的推演，产出 StoryResult。
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        rounds_per_scene: int = 4,
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
        self.rounds_per_scene = rounds_per_scene

    def run_story(
        self,
        story_plan: StoryPlan,
        character_profiles: Dict[str, str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> StoryResult:
        """
        运行完整故事推演。

        Args:
            story_plan: StoryPlanner 生成的故事编排
            character_profiles: 角色名 → persona 文本的映射
            progress_callback: 进度回调 (current, total, message)

        Returns:
            StoryResult: 完整推演结果
        """
        # 收集所有场景
        all_scenes: List[Scene] = []
        for ch in story_plan.chapters:
            all_scenes.extend(ch.scenes)

        total = len(all_scenes)
        logger.info(f"开始故事推演: {story_plan.title}, {total} 个场景")

        scene_results: List[SceneResult] = []
        accumulated_context: List[str] = []  # 跨场景摘要累积

        for idx, scene in enumerate(all_scenes):
            current = idx + 1
            msg = f"推演场景 {current}/{total}: {scene.title}"
            if progress_callback:
                progress_callback(current, total, msg)
            logger.info(msg)

            # 将前序场景摘要注入 persona（作为角色的"已知信息"）
            enriched_profiles = self._enrich_profiles(
                character_profiles, scene, accumulated_context
            )

            env = NarrativeEnvironment(
                scene=scene,
                character_profiles=enriched_profiles,
                llm_client=self.llm,
                rounds_per_scene=self.rounds_per_scene,
            )

            # 同步运行单个场景
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(env.run())
            scene_results.append(result)

            # 累积摘要
            if result.summary:
                accumulated_context.append(
                    f"第{scene.chapter}章「{scene.title}」：{result.summary}"
                )

        story_result = StoryResult(
            story_title=story_plan.title,
            genre=story_plan.genre,
            scene_results=scene_results,
        )

        logger.info(
            f"故事推演完成: {story_result.total_actions} 个动作, "
            f"{len(scene_results)} 个场景"
        )
        return story_result

    def _enrich_profiles(
        self,
        base_profiles: Dict[str, str],
        scene: Scene,
        accumulated_context: List[str],
    ) -> Dict[str, str]:
        """
        为角色 persona 注入前序场景的上下文。
        让角色"知道"之前发生了什么。
        """
        if not accumulated_context:
            return base_profiles

        # 只取最近 3 个场景的摘要
        recent = accumulated_context[-3:]
        context_block = "\n".join(f"- {c}" for c in recent)

        enriched = {}
        for name, persona in base_profiles.items():
            if name in scene.participating_characters:
                enriched[name] = (
                    f"{persona}\n\n【此前已发生的重要事件】\n{context_block}"
                )
            else:
                enriched[name] = persona

        return enriched
