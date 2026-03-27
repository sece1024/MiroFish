"""
NarrativeSpace 数据结构与功能测试

验证：
1. 数据结构构造和序列化
2. 从模拟数据构造 SceneResult / StoryResult
3. _build_context 逻辑
"""

import os
import sys
import json
import types
import random

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 构建 mock 模块树
class _FakeConfig:
    LLM_API_KEY = "test-key"
    LLM_BASE_URL = "http://localhost"
    LLM_MODEL_NAME = "test-model"


_fake_logger = type(
    "L",
    (),
    {
        "info": lambda *a, **kw: None,
        "warning": lambda *a, **kw: None,
    },
)

_app = types.ModuleType("app")
_app.__path__ = [os.path.join(_backend_dir, "app")]
_app.__package__ = "app"
sys.modules["app"] = _app

_app_config = types.ModuleType("app.config")
_app_config.Config = _FakeConfig
sys.modules["app.config"] = _app_config

_app_utils = types.ModuleType("app.utils")
_app_utils.__path__ = [os.path.join(_backend_dir, "app", "utils")]
_app_utils.__package__ = "app.utils"
sys.modules["app.utils"] = _app_utils

_app_utils_logger = types.ModuleType("app.utils.logger")
_app_utils_logger.get_logger = lambda name: _fake_logger
sys.modules["app.utils.logger"] = _app_utils_logger

# mock LLMClient
_app_utils_llm = types.ModuleType("app.utils.llm_client")


class _FakeLLMClient:
    def __init__(self, **kwargs):
        pass

    def chat_json(self, messages, temperature=0.7, max_tokens=4096):
        return {
            "type": "speak",
            "content": "测试对话",
            "target": None,
            "emotion": "平静",
        }


_app_utils_llm.LLMClient = _FakeLLMClient
sys.modules["app.utils.llm_client"] = _app_utils_llm

_app_services = types.ModuleType("app.services")
_app_services.__path__ = [os.path.join(_backend_dir, "app", "services")]
_app_services.__package__ = "app.services"
sys.modules["app.services"] = _app_services

# 先加载 story_planner（narrative_space 依赖它）
import importlib.util

_story_planner_path = os.path.join(_backend_dir, "app", "services", "story_planner.py")
_story_spec = importlib.util.spec_from_file_location(
    "app.services.story_planner", _story_planner_path
)
_story_mod = importlib.util.module_from_spec(_story_spec)
_story_mod.__package__ = "app.services"
sys.modules["app.services.story_planner"] = _story_mod
_story_spec.loader.exec_module(_story_mod)

# 再加载 narrative_space
_ns_path = os.path.join(_backend_dir, "app", "services", "narrative_space.py")
_ns_spec = importlib.util.spec_from_file_location(
    "app.services.narrative_space", _ns_path
)
_ns_mod = importlib.util.module_from_spec(_ns_spec)
_ns_mod.__package__ = "app.services"
sys.modules["app.services.narrative_space"] = _ns_mod
_ns_spec.loader.exec_module(_ns_mod)

NarrativeAction = _ns_mod.NarrativeAction
SceneResult = _ns_mod.SceneResult
StoryResult = _ns_mod.StoryResult
NarrativeEnvironment = _ns_mod.NarrativeEnvironment

Scene = _story_mod.Scene
ChapterOutline = _story_mod.ChapterOutline
StoryPlan = _story_mod.StoryPlan


# ============================================================
# 测试函数
# ============================================================


def test_narrative_action_construction():
    """测试 NarrativeAction 构造和序列化"""
    print("=" * 60)
    print("NarrativeAction 构造测试")
    print("=" * 60)

    action = NarrativeAction(
        round_num=1,
        agent_name="林黛玉",
        action_type="speak",
        content="这位妹妹我曾见过的。",
        target_name="贾宝玉",
        emotion="惊喜",
    )

    d = action.to_dict()
    assert d["agent_name"] == "林黛玉"
    assert d["action_type"] == "speak"
    assert d["target_name"] == "贾宝玉"

    j = json.dumps(d, ensure_ascii=False)
    parsed = json.loads(j)
    assert parsed["content"] == "这位妹妹我曾见过的。"

    print("  [PASS] NarrativeAction 构造和序列化正常")


def test_scene_result_construction():
    """测试 SceneResult 构造"""
    print("\n" + "=" * 60)
    print("SceneResult 构造测试")
    print("=" * 60)

    scene = Scene(
        scene_id=1,
        chapter=1,
        title="初见",
        setting="贾府正厅",
        time_of_day="正午",
        participating_characters=["林黛玉", "贾宝玉"],
        conflict="初次见面的试探",
        emotional_arc="tension",
        narrative_hint="建立角色初印象",
    )

    actions = [
        NarrativeAction(1, "林黛玉", "observe", "打量着眼前这位公子", None, "好奇"),
        NarrativeAction(1, "贾宝玉", "speak", "这位妹妹我曾见过的", "林黛玉", "惊喜"),
        NarrativeAction(
            2, "林黛玉", "think", "这人好生奇怪，说话如此唐突", None, "困惑"
        ),
    ]

    result = SceneResult(
        scene=scene.to_dict(),
        actions=actions,
        summary="黛玉初入贾府，与宝玉一见如故。",
    )

    d = result.to_dict()
    assert d["scene"]["title"] == "初见"
    assert len(d["actions"]) == 3
    assert d["actions"][1]["action_type"] == "speak"

    j = result.to_json()
    parsed = json.loads(j)
    assert parsed["summary"] == "黛玉初入贾府，与宝玉一见如故。"

    print("  [PASS] SceneResult 构造和序列化正常")


def test_story_result_construction():
    """测试 StoryResult 构造"""
    print("\n" + "=" * 60)
    print("StoryResult 构造测试")
    print("=" * 60)

    scene1 = Scene(
        scene_id=1,
        chapter=1,
        title="场景一",
        setting="地点A",
        time_of_day="清晨",
        participating_characters=["角色A"],
        conflict="冲突1",
        emotional_arc="tension",
        narrative_hint="提示1",
    )
    scene2 = Scene(
        scene_id=2,
        chapter=1,
        title="场景二",
        setting="地点B",
        time_of_day="黄昏",
        participating_characters=["角色B"],
        conflict="冲突2",
        emotional_arc="climax",
        narrative_hint="提示2",
    )

    results = [
        SceneResult(
            scene=scene1.to_dict(),
            actions=[
                NarrativeAction(1, "角色A", "speak", "你好", None, "平静"),
                NarrativeAction(2, "角色A", "act", "转身离开", None, "冷漠"),
            ],
            summary="角色A在地点A说了你好后离开。",
        ),
        SceneResult(
            scene=scene2.to_dict(),
            actions=[
                NarrativeAction(1, "角色B", "think", "一切都结束了", None, "悲伤"),
            ],
            summary="角色B在黄昏中独自沉思。",
        ),
    ]

    story = StoryResult(
        story_title="测试小说",
        genre="现代",
        scene_results=results,
    )

    assert story.total_actions == 3
    assert story.story_title == "测试小说"

    d = story.to_dict()
    assert len(d["scene_results"]) == 2
    assert d["scene_results"][0]["summary"] == "角色A在地点A说了你好后离开。"

    print("  [PASS] StoryResult 构造和序列化正常")
    print(f"  [PASS] total_actions = {story.total_actions}")


def test_context_building():
    """测试 _build_context 逻辑（模拟）"""
    print("\n" + "=" * 60)
    print("上下文构建逻辑测试")
    print("=" * 60)

    # 模拟 _build_context 的核心逻辑
    actions = [
        NarrativeAction(
            1, "王熙凤", "speak", "天下真有这样标致的人物", "林黛玉", "赞叹"
        ),
        NarrativeAction(1, "贾母", "act", "拉着黛玉的手让她坐在身边", "林黛玉", "慈爱"),
        NarrativeAction(
            2, "林黛玉", "think", "这里规矩好多，须得处处小心", None, "紧张"
        ),
        NarrativeAction(2, "贾宝玉", "speak", "这个妹妹我曾见过的", "林黛玉", "惊喜"),
    ]

    def build_context(current_char, all_actions):
        lines = []
        for a in all_actions[-8:]:
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
        return "\n".join(lines)

    ctx = build_context("贾宝玉", actions)
    assert "王熙凤 说" in ctx
    assert "林黛玉 心想" in ctx
    assert "贾宝玉 说" in ctx

    print("  [PASS] 上下文构建逻辑正确")
    print(f"  生成的上下文：\n{ctx}")


def test_story_plan_integration():
    """测试与 StoryPlan 的集成"""
    print("\n" + "=" * 60)
    print("StoryPlan 集成测试")
    print("=" * 60)

    scene = Scene(
        scene_id=1,
        chapter=1,
        title="序章",
        setting="大观园怡红院",
        time_of_day="清晨",
        participating_characters=["贾宝玉", "林黛玉", "薛宝钗"],
        conflict="三人微妙的情感试探",
        emotional_arc="tension",
        narrative_hint="展现宝钗黛三人关系的复杂性",
    )

    chapter = ChapterOutline(
        chapter=1,
        title="三人行",
        summary="宝钗黛三人的初次微妙互动",
        scenes=[scene],
    )

    plan = StoryPlan(
        title="红楼梦续",
        genre="古典言情",
        total_chapters=1,
        characters=[
            {"name": "贾宝玉", "description": "叛逆多情"},
            {"name": "林黛玉", "description": "才情出众"},
            {"name": "薛宝钗", "description": "端庄大方"},
        ],
        chapters=[chapter],
    )

    # 验证可以从 plan 中提取场景
    all_scenes = []
    for ch in plan.chapters:
        all_scenes.extend(ch.scenes)

    assert len(all_scenes) == 1
    assert all_scenes[0].title == "序章"
    assert len(all_scenes[0].participating_characters) == 3

    # 验证可以构造角色 profile 映射
    profiles = {c["name"]: c["description"] for c in plan.characters}
    assert "贾宝玉" in profiles
    assert profiles["林黛玉"] == "才情出众"

    print("  [PASS] StoryPlan 集成正常")
    print(f"  场景数: {len(all_scenes)}, 角色数: {len(profiles)}")


def test_narrative_environment_mock():
    """测试 NarrativeEnvironment 的基本构造（用 mock LLM）"""
    print("\n" + "=" * 60)
    print("NarrativeEnvironment 构造测试")
    print("=" * 60)

    scene = Scene(
        scene_id=1,
        chapter=1,
        title="对话",
        setting="书房",
        time_of_day="深夜",
        participating_characters=["张三", "李四"],
        conflict="关于一封密信的争论",
        emotional_arc="tension",
        narrative_hint="通过对话揭示密信的秘密",
    )

    profiles = {
        "张三": "性格暴躁的武将",
        "李四": "冷静睿智的谋士",
    }

    env = NarrativeEnvironment(
        scene=scene,
        character_profiles=profiles,
        llm_client=_FakeLLMClient(),
        rounds_per_scene=2,
    )

    assert env.scene.title == "对话"
    assert len(env.character_profiles) == 2
    assert env.rounds == 2

    print("  [PASS] NarrativeEnvironment 构造正常")


if __name__ == "__main__":
    random.seed(42)  # 固定随机种子，确保测试可复现

    test_narrative_action_construction()
    test_scene_result_construction()
    test_story_result_construction()
    test_context_building()
    test_story_plan_integration()
    test_narrative_environment_mock()

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
