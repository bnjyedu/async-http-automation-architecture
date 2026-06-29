"""端到端导入与配置验证脚本。

5 项测试：
    1. video_list_parser：视频列表 HTML 解析
    2. course_match：课程名匹配（精确+括号归一化）
    3. parse_four_textareas：4 个 textarea 解析
    4. question_bank：题库 upsert 去重
    5. xlsx：账号文件读取
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from course.matcher import match_course
from exam.common import parse_four_textareas
from player.video_list_parser import parse_video_list_html
from storage.question_bank import QuestionBank
from utils.xlsx_reader import read_accounts


def check(condition, msg=""):
    """显式检查（不被 -O 跳过，替代 assert）。"""
    if not condition:
        raise AssertionError(msg)


SAMPLE_VIDEO_HTML = """
<a href="javascript:void(0)" id="101" class="clearfix online cur">
    <span class="fr time" data-value="101">14:23</span>
    <i class="cg fl leve2_wx"></i>
    <span title="第01讲　导　言" data-value="101">第01讲　导　言</span>
</a>
<a href="javascript:void(0)" id="102" class="clearfix">
    <span class="fr time" data-value="102">26:16</span>
    <i class="cg fl leve2_yx"></i>
    <span title="第02讲　进入近代后中华民族的磨难与抗争">第02讲</span>
</a>
"""


def test_video_list_parser():
    """验证视频列表 HTML 解析。"""
    videos = parse_video_list_html(SAMPLE_VIDEO_HTML)
    check(len(videos) == 2, f"应解析 2 个视频，实际 {len(videos)}")
    check(videos[0].videoID == "101")
    check(videos[0].title == "第01讲　导　言")
    check(videos[0].duration == "14:23")
    check(videos[0].status == "未学")
    check(videos[1].videoID == "102")
    check(videos[1].status == "已学")
    print("[OK] video_list HTML 解析")


def test_course_match():
    """验证课程名匹配（精确 + 中英文括号归一化）。"""
    # 用简单命名空间模拟 CourseLike（带 courseName）
    from types import SimpleNamespace
    courses = [
        SimpleNamespace(courseName="马克思主义基本原理"),
        SimpleNamespace(courseName="中国近现代史纲要"),
        SimpleNamespace(courseName="习近平新时代中国特色社会主义思想概论"),
        SimpleNamespace(courseName="英语（二）"),
    ]

    # 精确匹配用例
    exact_cases = [
        ("马克思主义基本原理", "马克思主义基本原理"),
        ("中国近现代史纲要", "中国近现代史纲要"),
        ("习近平新时代中国特色社会主义思想概论", "习近平新时代中国特色社会主义思想概论"),
        ("英语（二）", "英语（二）"),
    ]
    for subject, expected in exact_cases:
        matched = match_course(subject, courses)
        check(matched is not None, f"科目 '{subject}' 未匹配")
        check(
            matched.courseName == expected,
            f"科目 '{subject}' 应匹配 '{expected}'，实际 '{matched.courseName}'",
        )

    # 中英文括号归一化用例（肉眼难辨差异）
    bracket_cases = [
        ("英语(二)", "英语（二）"),       # 英文括号 → 中文括号
        ("英语(二)听力", None),            # 不存在，应返回 None
    ]
    for subject, expected in bracket_cases:
        matched = match_course(subject, courses)
        if expected is None:
            check(matched is None, f"科目 '{subject}' 不应匹配任何课程，实际匹配到 '{matched.courseName if matched else None}'")
        else:
            check(matched is not None, f"科目 '{subject}' 未匹配")
            check(
                matched.courseName == expected,
                f"科目 '{subject}' 应匹配 '{expected}'，实际 '{matched.courseName}'",
            )

    # 别名应不再匹配（验证别名表已移除）
    alias_should_fail = ["马原", "马基", "史纲", "习思想", "英语二"]
    for subject in alias_should_fail:
        matched = match_course(subject, courses)
        check(matched is None, f"别名 '{subject}' 应不再匹配（别名表已移除），实际匹配到 '{matched.courseName if matched else None}'")

    print("[OK] 课程名匹配（精确 + 中英文括号归一化）")


SAMPLE_TEXTAREA_HTML = """
<textarea name="userAnsMapStr" style="display:none; ">{"11855715":{"rightAnswer":"B","quesType":1,"score":2.0},"11855716":{"rightAnswer":"A","quesType":1,"score":2.0}}</textarea>
<textarea name="commonInfoStr" style="display:none; ">{"centerID":"8714","paperID":"58888","userID":"98485238"}</textarea>
<textarea name="quesTypeShowMapStr" style="display:none; ">{"1":"单选题"}</textarea>
<textarea name="quesShowListStr" style="display:none; ">[{"questionID":"11855715"}]</textarea>
"""


def test_parse_four_textareas():
    """验证 4 个 textarea 解析。"""
    parsed = parse_four_textareas(SAMPLE_TEXTAREA_HTML)
    check(len(parsed["answers"]) == 2, f"应解析 2 道题答案，实际 {len(parsed['answers'])}")
    check(parsed["answers"]["11855715"]["rightAnswer"] == "B")
    check(parsed["answers"]["11855716"]["rightAnswer"] == "A")
    check(parsed["commonInfo"]["paperID"] == "58888")
    check(parsed["commonInfo"]["centerID"] == "8714")
    check(parsed["quesTypeShow"]["1"] == "单选题")
    check(len(parsed["quesShowList"]) == 1)
    check(parsed["quesShowList"][0]["questionID"] == "11855715")
    print("[OK] 4 个 textarea 解析")


async def test_question_bank():
    """验证题库 upsert 去重。"""
    qb_path = os.path.join(os.environ.get("TEMP", "/tmp"), "test_qb_e2e.db")
    if os.path.exists(qb_path):
        os.remove(qb_path)
    qb = QuestionBank(qb_path)
    await qb.init()

    n1 = await qb.bulk_upsert_from_intercepted(
        {"11855715": {"rightAnswer": "B", "quesType": 1, "score": 2.0}},
        courseName="马原", cwareID=516874, paperID=58888,
    )
    check(n1 == 1, f"第一次应新增 1 题，实际 {n1}")

    n2 = await qb.bulk_upsert_from_intercepted(
        {
            "11855715": {"rightAnswer": "B", "quesType": 1, "score": 2.0},
            "11855716": {"rightAnswer": "A", "quesType": 1, "score": 2.0},
        },
        courseName="马原", cwareID=516874,
    )
    check(n2 == 1, f"第二次应新增 1 题（去重），实际 {n2}")

    total = await qb.count()
    check(total == 2, f"总库应有 2 题，实际 {total}")

    os.remove(qb_path)
    print("[OK] 题库 upsert 去重")


async def main():
    print("=" * 60)
    print("自动化系统 - 端到端导入与单元验证")
    print("=" * 60)

    test_video_list_parser()
    test_course_match()
    test_parse_four_textareas()
    await test_question_bank()

    import yaml
    config_path = Path(__file__).resolve().parent / "config.yaml"
    if not config_path.exists():
        print("[SKIP] xlsx 读取（config.yaml 不存在，复制 config.example.yaml 后可测试）")
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        accounts = read_accounts(config["account_file"])
        check(len(accounts) > 0, "账号文件为空或读取失败")
        print(f"[OK] xlsx 读取 {len(accounts)} 条账号")

    print()
    print("=" * 60)
    print("所有验证通过！系统已就绪，可运行 main.py 启动自动化")
    print("启动命令: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
