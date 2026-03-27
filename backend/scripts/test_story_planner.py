"""
StoryPlanner 数据结构与 JSON 序列化测试

验证：
1. 数据结构定义正确
2. JSON 序列化/反序列化正常
3. 从模拟 LLM 响应构造 StoryPlan 的逻辑正确
"""

import os
import sys
import json
import types

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 构建完整的 mock 模块树，使相对导入 (from ..config import Config) 正常工作
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

# app
_app = types.ModuleType("app")
_app.__path__ = [os.path.join(_backend_dir, "app")]
_app.__package__ = "app"
sys.modules["app"] = _app

# app.config
_app_config = types.ModuleType("app.config")
_app_config.Config = _FakeConfig
sys.modules["app.config"] = _app_config

# app.utils
_app_utils = types.ModuleType("app.utils")
_app_utils.__path__ = [os.path.join(_backend_dir, "app", "utils")]
_app_utils.__package__ = "app.utils"
sys.modules["app.utils"] = _app_utils

# app.utils.logger
_app_utils_logger = types.ModuleType("app.utils.logger")
_app_utils_logger.get_logger = lambda name: _fake_logger
sys.modules["app.utils.logger"] = _app_utils_logger

# app.services
_app_services = types.ModuleType("app.services")
_app_services.__path__ = [os.path.join(_backend_dir, "app", "services")]
_app_services.__package__ = "app.services"
sys.modules["app.services"] = _app_services

# 现在可以用 importlib 加载 story_planner，相对导入会正常解析
import importlib.util

_module_path = os.path.join(_backend_dir, "app", "services", "story_planner.py")
_spec = importlib.util.spec_from_file_location(
    "app.services.story_planner",
    _module_path,
    submodule_search_locations=[],
)
_mod = importlib.util.module_from_spec(_spec)
_mod.__package__ = "app.services"
sys.modules["app.services.story_planner"] = _mod
_spec.loader.exec_module(_mod)

StoryPlanner = _mod.StoryPlanner
StoryPlannerInput = _mod.StoryPlannerInput
StoryPlan = _mod.StoryPlan
ChapterOutline = _mod.ChapterOutline
Scene = _mod.Scene
CharacterInput = _mod.CharacterInput


def test_dataclass_construction():
    """测试数据结构构造"""
    print("=" * 60)
    print("数据结构构造测试")
    print("=" * 60)

    # 构造角色
    chars = [
        CharacterInput(name="林黛玉", description="才情出众、多愁善感的女子"),
        CharacterInput(name="贾宝玉", description="叛逆多情的贵族公子"),
    ]

    # 构造场景
    scene = Scene(
        scene_id=1,
        chapter=1,
        title="初入贾府",
        setting="贾府正厅，富丽堂皇",
        time_of_day="清晨",
        participating_characters=["林黛玉", "贾宝玉"],
        conflict="黛玉初来乍到，小心翼翼试探环境",
        emotional_arc="tension",
        narrative_hint="建立黛玉的谨慎性格和与宝玉的初次印象",
    )

    # 构造章节
    ch = ChapterOutline(
        chapter=1,
        title="序章：缘起",
        summary="黛玉初入贾府，与众人相见",
        scenes=[scene],
    )

    # 构造完整计划
    plan = StoryPlan(
        title="红楼梦续",
        genre="古典言情",
        total_chapters=1,
        characters=[{"name": c.name, "description": c.description} for c in chars],
        chapters=[ch],
        plot_threads=["主线：宝黛情感发展"],
    )

    # 验证序列化
    plan_dict = plan.to_dict()
    plan_json = plan.to_json()

    assert plan_dict["title"] == "红楼梦续"
    assert plan_dict["total_chapters"] == 1
    assert len(plan_dict["chapters"]) == 1
    assert len(plan_dict["chapters"][0]["scenes"]) == 1
    assert plan_dict["chapters"][0]["scenes"][0]["participating_characters"] == [
        "林黛玉",
        "贾宝玉",
    ]

    # 验证 JSON 可解析
    parsed = json.loads(plan_json)
    assert parsed["title"] == "红楼梦续"
    assert parsed["chapters"][0]["scenes"][0]["emotional_arc"] == "tension"

    print("  [PASS] 数据结构构造正常")
    print("  [PASS] JSON 序列化正常")
    print("  [PASS] JSON 反序列化正常")


def test_from_simulated_llm_response():
    """测试从模拟 LLM 响应构造 StoryPlan"""
    print("\n" + "=" * 60)
    print("模拟 LLM 响应构造测试")
    print("=" * 60)

    # 模拟 Step 1（章节拆解）的 LLM 响应
    chapter_response = {
        "title": "红楼梦失传结局推演",
        "chapters": [
            {
                "chapter": 1,
                "title": "风雨欲来",
                "summary": "贾府暗流涌动，各方势力蠢蠢欲动",
            },
            {"chapter": 2, "title": "大厦将倾", "summary": "抄家消息传来，众人四散"},
            {"chapter": 3, "title": "落花流水", "summary": "众人各有归宿，黛玉病重"},
        ],
        "plot_threads": ["主线：贾府兴衰", "支线：宝黛之情"],
    }

    # 模拟 Step 2（场景拆解）的 LLM 响应
    scene_responses = [
        {
            "scenes": [
                {
                    "scene_id": 1,
                    "chapter": 1,
                    "title": "王熙凤的忧虑",
                    "setting": "王熙凤房中，烛光摇曳",
                    "time_of_day": "深夜",
                    "participating_characters": ["王熙凤", "平儿"],
                    "conflict": "凤姐察觉府中财务危机",
                    "emotional_arc": "tension",
                    "narrative_hint": "通过凤姐的视角揭示贾府经济困境",
                },
                {
                    "scene_id": 2,
                    "chapter": 1,
                    "title": "宝玉的春愁",
                    "setting": "大观园怡红院",
                    "time_of_day": "清晨",
                    "participating_characters": ["贾宝玉", "林黛玉"],
                    "conflict": "宝玉对未来的迷茫与对黛玉的担忧",
                    "emotional_arc": "rising",
                    "narrative_hint": "宝黛对话中暗示命运的无常",
                },
            ]
        },
        {
            "scenes": [
                {
                    "scene_id": 3,
                    "chapter": 2,
                    "title": "抄家令到",
                    "setting": "贾府大门前",
                    "time_of_day": "正午",
                    "participating_characters": ["贾政", "贾赦", "王夫人"],
                    "conflict": "官兵围府，抄家令宣读",
                    "emotional_arc": "climax",
                    "narrative_hint": "贾府命运的转折点，众人反应各异",
                },
            ]
        },
        {
            "scenes": [
                {
                    "scene_id": 4,
                    "chapter": 3,
                    "title": "黛玉焚稿",
                    "setting": "潇湘馆，秋风萧瑟",
                    "time_of_day": "黄昏",
                    "participating_characters": ["林黛玉", "紫鹃"],
                    "conflict": "黛玉心灰意冷，焚毁诗稿",
                    "emotional_arc": "falling",
                    "narrative_hint": "悲剧高潮，黛玉对命运的最后控诉",
                },
            ]
        },
    ]

    # 构造 StoryPlan（模拟 planner.plan() 的逻辑）
    characters = [
        {"name": "林黛玉", "description": "才情出众、多愁善感"},
        {"name": "贾宝玉", "description": "叛逆多情的贵族公子"},
        {"name": "王熙凤", "description": "精明强干的管家"},
        {"name": "平儿", "description": "凤姐的贴身丫鬟"},
        {"name": "贾政", "description": "贾府家长，严肃古板"},
        {"name": "贾赦", "description": "贾府大老爷，贪婪好色"},
        {"name": "王夫人", "description": "宝玉之母，信佛"},
        {"name": "紫鹃", "description": "黛玉贴身丫鬟"},
    ]

    chapters = []
    scene_id = 1
    for idx, ch_raw in enumerate(chapter_response["chapters"]):
        scenes_raw = scene_responses[idx]["scenes"]
        scenes = []
        for s in scenes_raw:
            s["scene_id"] = scene_id
            scenes.append(
                Scene(**{k: s[k] for k in Scene.__dataclass_fields__ if k in s})
            )
            scene_id += 1
        chapters.append(
            ChapterOutline(
                chapter=ch_raw["chapter"],
                title=ch_raw["title"],
                summary=ch_raw["summary"],
                scenes=scenes,
            )
        )

    plan = StoryPlan(
        title=chapter_response["title"],
        genre="古典言情",
        total_chapters=len(chapters),
        characters=characters,
        chapters=chapters,
        plot_threads=chapter_response["plot_threads"],
    )

    # 验证
    assert plan.total_chapters == 3
    assert len(plan.chapters) == 3
    assert sum(len(ch.scenes) for ch in plan.chapters) == 4
    assert plan.chapters[0].scenes[0].participating_characters == ["王熙凤", "平儿"]
    assert plan.chapters[2].scenes[0].emotional_arc == "falling"

    # 验证完整 JSON 输出
    plan_json = plan.to_json()
    parsed = json.loads(plan_json)
    assert parsed["plot_threads"] == ["主线：贾府兴衰", "支线：宝黛之情"]

    print("  [PASS] 章节拆解数据构造正常")
    print("  [PASS] 场景拆解数据构造正常")
    print("  [PASS] 完整 StoryPlan 构造正常")
    print("  [PASS] JSON 序列化完整且可解析")


def test_story_planner_input():
    """测试 StoryPlannerInput"""
    print("\n" + "=" * 60)
    print("StoryPlannerInput 测试")
    print("=" * 60)

    inp = StoryPlannerInput(
        outline="一个关于古代宫廷权谋的故事...",
        characters=[
            CharacterInput(name="皇帝", description="年轻有为但受制于权臣"),
            CharacterInput(name="皇后", description="聪慧隐忍"),
        ],
        genre="宫廷权谋",
        chapter_count=8,
    )

    assert inp.genre == "宫廷权谋"
    assert inp.chapter_count == 8
    assert len(inp.characters) == 2
    assert inp.characters[0].name == "皇帝"

    print("  [PASS] StoryPlannerInput 构造正常")


if __name__ == "__main__":
    test_dataclass_construction()
    test_from_simulated_llm_response()
    test_story_planner_input()
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
