"""
ChapterWriter 数据结构与功能测试

验证：
1. ChapterNovel / NovelResult 构造和序列化
2. Markdown 输出格式
3. _group_scenes_by_chapter 分组逻辑
4. _format_action_log 格式化
5. 端到端 mock 写作流程
"""

import os
import sys
import json
import types

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ========== mock 模块树 ==========


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

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        return (
            "暮色四合，怡红院中灯火初上。\n\n"
            "宝玉坐在窗前，手中把玩着那块通灵宝玉，心绪却早已飘到了潇湘馆。\n\n"
            "「也不知林妹妹今日可好些了？」他喃喃自语。\n\n"
            "袭人端了茶进来，见他发呆，不禁笑道：「二爷又在想什么呢？茶都凉了。」\n\n"
            "宝玉接过茶盏，却只是怔怔地望着窗外那一弯新月。"
        )

    def chat_json(self, messages, temperature=0.7, max_tokens=4096):
        return {"summary": "宝玉独自在怡红院思念黛玉。"}


_app_utils_llm.LLMClient = _FakeLLMClient
sys.modules["app.utils.llm_client"] = _app_utils_llm

_app_services = types.ModuleType("app.services")
_app_services.__path__ = [os.path.join(_backend_dir, "app", "services")]
_app_services.__package__ = "app.services"
sys.modules["app.services"] = _app_services

# 加载 story_planner
import importlib.util

_sp_path = os.path.join(_backend_dir, "app", "services", "story_planner.py")
_sp_spec = importlib.util.spec_from_file_location(
    "app.services.story_planner", _sp_path
)
_sp_mod = importlib.util.module_from_spec(_sp_spec)
_sp_mod.__package__ = "app.services"
sys.modules["app.services.story_planner"] = _sp_mod
_sp_spec.loader.exec_module(_sp_mod)

# 加载 narrative_space
_ns_path = os.path.join(_backend_dir, "app", "services", "narrative_space.py")
_ns_spec = importlib.util.spec_from_file_location(
    "app.services.narrative_space", _ns_path
)
_ns_mod = importlib.util.module_from_spec(_ns_spec)
_ns_mod.__package__ = "app.services"
sys.modules["app.services.narrative_space"] = _ns_mod
_ns_spec.loader.exec_module(_ns_mod)

# 加载 chapter_writer
_cw_path = os.path.join(_backend_dir, "app", "services", "chapter_writer.py")
_cw_spec = importlib.util.spec_from_file_location(
    "app.services.chapter_writer", _cw_path
)
_cw_mod = importlib.util.module_from_spec(_cw_spec)
_cw_mod.__package__ = "app.services"
sys.modules["app.services.chapter_writer"] = _cw_mod
_cw_spec.loader.exec_module(_cw_mod)

# 导出
ChapterNovel = _cw_mod.ChapterNovel
NovelResult = _cw_mod.NovelResult
ChapterWriter = _cw_mod.ChapterWriter

Scene = _sp_mod.Scene
ChapterOutline = _sp_mod.ChapterOutline
StoryPlan = _sp_mod.StoryPlan

NarrativeAction = _ns_mod.NarrativeAction
SceneResult = _ns_mod.SceneResult
StoryResult = _ns_mod.StoryResult


# ============================================================
# 测试数据
# ============================================================


def _make_test_data():
    """构造测试用的 StoryPlan + StoryResult"""
    scene1 = Scene(
        scene_id=1,
        chapter=1,
        title="怡红夜思",
        setting="怡红院内室",
        time_of_day="黄昏",
        participating_characters=["贾宝玉", "袭人"],
        conflict="宝玉思念黛玉",
        emotional_arc="tension",
        narrative_hint="展现宝玉对黛玉的牵挂",
    )
    scene2 = Scene(
        scene_id=2,
        chapter=1,
        title="潇湘对月",
        setting="潇湘馆窗前",
        time_of_day="深夜",
        participating_characters=["林黛玉", "紫鹃"],
        conflict="黛玉感叹身世",
        emotional_arc="falling",
        narrative_hint="通过黛玉独白展现其孤独感",
    )
    scene3 = Scene(
        scene_id=3,
        chapter=2,
        title="宝钗来访",
        setting="怡红院正厅",
        time_of_day="清晨",
        participating_characters=["贾宝玉", "薛宝钗"],
        conflict="宝钗试探宝玉心意",
        emotional_arc="tension",
        narrative_hint="宝钗的端庄与宝玉的敷衍形成对比",
    )

    plan = StoryPlan(
        title="红楼梦续",
        genre="古典言情",
        total_chapters=2,
        characters=[
            {"name": "贾宝玉", "description": "叛逆多情的贵族公子"},
            {"name": "林黛玉", "description": "才情出众、多愁善感"},
            {"name": "袭人", "description": "宝玉贴身丫鬟，温柔体贴"},
            {"name": "紫鹃", "description": "黛玉贴身丫鬟，忠心耿耿"},
            {"name": "薛宝钗", "description": "端庄大方，城府极深"},
        ],
        chapters=[
            ChapterOutline(
                chapter=1,
                title="月下相思",
                summary="宝黛各自思念",
                scenes=[scene1, scene2],
            ),
            ChapterOutline(
                chapter=2, title="晨间试探", summary="宝钗来访试探宝玉", scenes=[scene3]
            ),
        ],
    )

    sr1 = SceneResult(
        scene=scene1.to_dict(),
        actions=[
            NarrativeAction(
                1, "贾宝玉", "think", "也不知林妹妹今日可好些了", None, "牵挂"
            ),
            NarrativeAction(
                1, "袭人", "speak", "二爷又在想什么呢？茶都凉了", "贾宝玉", "关切"
            ),
            NarrativeAction(2, "贾宝玉", "speak", "你不懂", "袭人", "落寞"),
        ],
        summary="宝玉独自思念黛玉，对袭人敷衍。",
    )
    sr2 = SceneResult(
        scene=scene2.to_dict(),
        actions=[
            NarrativeAction(
                1, "林黛玉", "observe", "月光如水，照得窗纱一片银白", None, "惆怅"
            ),
            NarrativeAction(
                1, "紫鹃", "speak", "姑娘，夜深了，该歇息了", "林黛玉", "担忧"
            ),
            NarrativeAction(
                2,
                "林黛玉",
                "think",
                "我这般寄人篱下，纵有千般心事，又能与谁说呢",
                None,
                "悲伤",
            ),
        ],
        summary="黛玉对月感怀身世。",
    )
    sr3 = SceneResult(
        scene=scene3.to_dict(),
        actions=[
            NarrativeAction(
                1, "薛宝钗", "speak", "宝兄弟，昨夜可睡得好？", "贾宝玉", "温和"
            ),
            NarrativeAction(1, "贾宝玉", "speak", "还好，还好", "薛宝钗", "敷衍"),
            NarrativeAction(
                2, "薛宝钗", "think", "他这态度，分明是心不在焉", None, "了然"
            ),
        ],
        summary="宝钗来访，宝玉心不在焉。",
    )

    story_result = StoryResult(
        story_title="红楼梦续",
        genre="古典言情",
        scene_results=[sr1, sr2, sr3],
    )

    return plan, story_result


# ============================================================
# 测试函数
# ============================================================


def test_chapter_novel():
    """测试 ChapterNovel 构造和序列化"""
    print("=" * 60)
    print("ChapterNovel 测试")
    print("=" * 60)

    ch = ChapterNovel(
        chapter=1,
        title="月下相思",
        content="暮色四合，怡红院中灯火初上。宝玉坐在窗前...",
    )

    assert ch.chapter == 1
    assert ch.title == "月下相思"
    assert ch.word_count > 0

    d = ch.to_dict()
    assert d["chapter"] == 1

    md = ch.to_markdown()
    assert "## 第1章 月下相思" in md
    assert "暮色四合" in md

    print("  [PASS] ChapterNovel 构造和序列化正常")


def test_novel_result():
    """测试 NovelResult 构造"""
    print("\n" + "=" * 60)
    print("NovelResult 测试")
    print("=" * 60)

    chapters = [
        ChapterNovel(chapter=1, title="第一章", content="第一章内容" * 100),
        ChapterNovel(chapter=2, title="第二章", content="第二章内容" * 200),
    ]

    novel = NovelResult(
        title="测试小说",
        genre="现代",
        chapters=chapters,
    )

    assert novel.total_chapters == 2
    assert novel.total_word_count == chapters[0].word_count + chapters[1].word_count

    md = novel.to_markdown()
    assert "# 测试小说" in md
    assert "## 第1章 第一章" in md
    assert "## 第2章 第二章" in md

    d = novel.to_dict()
    assert d["total_chapters"] == 2

    print(f"  [PASS] NovelResult: {novel.total_chapters}章, {novel.total_word_count}字")
    print("  [PASS] Markdown 输出格式正确")


def test_group_scenes_by_chapter():
    """测试 _group_scenes_by_chapter 分组逻辑"""
    print("\n" + "=" * 60)
    print("场景分组测试")
    print("=" * 60)

    plan, story_result = _make_test_data()

    writer = ChapterWriter(llm_client=_FakeLLMClient())
    grouped = writer._group_scenes_by_chapter(story_result, plan)

    assert len(grouped) == 2  # 2 个章节
    assert grouped[0][0].chapter == 1
    assert len(grouped[0][1]) == 2  # 第1章有2个场景
    assert grouped[1][0].chapter == 2
    assert len(grouped[1][1]) == 1  # 第2章有1个场景

    print(
        f"  [PASS] 分组正确: 第1章{len(grouped[0][1])}场景, 第2章{len(grouped[1][1])}场景"
    )


def test_format_action_log():
    """测试 _format_action_log 格式化"""
    print("\n" + "=" * 60)
    print("交互日志格式化测试")
    print("=" * 60)

    _, story_result = _make_test_data()
    writer = ChapterWriter(llm_client=_FakeLLMClient())

    log = writer._format_action_log(story_result.scene_results[:1])

    assert "【怡红夜思】" in log
    assert "贾宝玉 心想" in log
    assert "袭人 说 对 贾宝玉（关切）" in log
    assert "「二爷又在想什么呢" in log

    print("  [PASS] 交互日志格式化正确")
    print(f"  日志片段:\n{log[:200]}")


def test_end_to_end_mock():
    """端到端 mock 写作流程"""
    print("\n" + "=" * 60)
    print("端到端 mock 写作测试")
    print("=" * 60)

    plan, story_result = _make_test_data()
    profiles = {c["name"]: c["description"] for c in plan.characters}

    writer = ChapterWriter(llm_client=_FakeLLMClient(), target_words_per_chapter=500)
    novel = writer.write_novel(story_result, plan, profiles)

    assert novel.title == "红楼梦续"
    assert novel.total_chapters == 2
    assert novel.total_word_count > 0
    assert "暮色四合" in novel.chapters[0].content
    assert novel.chapters[0].chapter == 1
    assert novel.chapters[1].chapter == 2

    print(
        f"  [PASS] 小说生成完成: {novel.total_chapters}章, {novel.total_word_count}字"
    )
    print(f"  第1章标题: {novel.chapters[0].title}")
    print(f"  第1章前50字: {novel.chapters[0].content[:50]}...")


def test_markdown_output():
    """测试完整 Markdown 输出"""
    print("\n" + "=" * 60)
    print("Markdown 完整输出测试")
    print("=" * 60)

    plan, story_result = _make_test_data()
    profiles = {c["name"]: c["description"] for c in plan.characters}

    writer = ChapterWriter(llm_client=_FakeLLMClient())
    novel = writer.write_novel(story_result, plan, profiles)

    md = novel.to_markdown()

    assert "# 红楼梦续" in md
    assert "*古典言情*" in md
    assert "## 第1章 月下相思" in md
    assert "## 第2章 晨间试探" in md
    assert "---" in md

    print("  [PASS] Markdown 完整输出格式正确")
    print(f"  总字数: {len(md)} 字符")


if __name__ == "__main__":
    test_chapter_novel()
    test_novel_result()
    test_group_scenes_by_chapter()
    test_format_action_log()
    test_end_to_end_mock()
    test_markdown_output()

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
