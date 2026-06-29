"""测验模块公共工具：正则、序列化、答案映射构造。

统一维护 quiz_runner / stage_exam_client / html_parser 中
重复的 textarea 正则、JSON 序列化和提交答案构造逻辑。
"""
import json
import random
import re
from typing import Any, Dict


# ─── textarea 正则(题目获取 / 试卷创建响应共用) ────

ANSWER_TEXTAREA_PATTERN = re.compile(
    r'<textarea[^>]*name="userAnsMapStr"[^>]*>(.*?)</textarea>', re.S,
)
COMMON_INFO_PATTERN = re.compile(
    r'<textarea[^>]*name="commonInfoStr"[^>]*>(.*?)</textarea>', re.S,
)
QUES_TYPE_SHOW_PATTERN = re.compile(
    r'<textarea[^>]*name="quesTypeShowMapStr"[^>]*>(.*?)</textarea>', re.S,
)
QUES_SHOW_LIST_PATTERN = re.compile(
    r'<textarea[^>]*name="quesShowListStr"[^>]*>(.*?)</textarea>', re.S,
)


# ─── quesType → quesViewType 映射（抓包确认） ────

QUES_VIEW_TYPE_MAP: Dict[int, int] = {
    1: 1,    # 单选题
    2: 2,    # 多选题
    3: 3,    # 判断题
    4: 4,    # 简答题
    46: 46,  # 论述题
}


def dumps(obj: Any) -> str:
    """紧凑 JSON 序列化（无空格，保留中文）。"""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def safe_int(val: Any, default: int = 0) -> int:
    """安全转 int，异常或 None 返回 default。"""
    try:
        if val is None:
            return default
        return int(val)
    except (ValueError, TypeError):
        return default


def safe_float(val: Any, default: float = 0.0) -> float:
    """安全转 float，异常或 None 返回 default。"""
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def parse_four_textareas(html: str) -> Dict[str, Any]:
    """解析响应 HTML 中的 4 个 textarea。

    Returns:
        {answers, commonInfo, quesTypeShow, quesShowList}
        answers 为空字典时表示解析失败。
    """
    answers: dict = {}
    common_info: dict = {}
    ques_type_show: dict = {}
    ques_show_list: list = []

    m = ANSWER_TEXTAREA_PATTERN.search(html)
    if m:
        try:
            answers = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    m = COMMON_INFO_PATTERN.search(html)
    if m:
        try:
            common_info = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    m = QUES_TYPE_SHOW_PATTERN.search(html)
    if m:
        try:
            ques_type_show = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    m = QUES_SHOW_LIST_PATTERN.search(html)
    if m:
        try:
            ques_show_list = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    return {
        "answers": answers,
        "commonInfo": common_info,
        "quesTypeShow": ques_type_show,
        "quesShowList": ques_show_list,
    }


def build_submit_ans_map(
    ans_map: Dict[str, Dict[str, Any]],
    ques_time_range: tuple = (10, 60),
) -> Dict[str, Dict[str, Any]]:
    """在 userAnsMapStr 每题中添加 userAnswer=rightAnswer 及提交必需字段。

    抓包确认的必需字段：
    - questionID（字符串）、userAnswer、isView=1、isAnswer=1
    - quesType、quesTime（单选题有，简答/论述题无）、rightAnswer
    - score、relOrder、splitScore=0（强制）
    - quesViewType（阶段测验最终提交必需）、parentID=0

    Args:
        ans_map: 原始 answers map {questionID_str: {rightAnswer, quesType, ...}}
        ques_time_range: quesTime 随机范围，补做测试默认 (10,60)，阶段测验 (7,30)

    Returns:
        构造好的提交答案 map
    """
    submit: dict = {}
    for qid, info in ans_map.items():
        right_answer = info.get("rightAnswer", "")
        entry = dict(info)
        entry["questionID"] = str(qid)
        entry["userAnswer"] = right_answer
        entry["isAnswer"] = 1
        entry["isView"] = 1
        entry["rightAnswer"] = right_answer
        entry["splitScore"] = 0

        ques_type = safe_int(info.get("quesType", 1), 1)
        entry["quesViewType"] = QUES_VIEW_TYPE_MAP.get(ques_type, ques_type)
        entry["parentID"] = 0

        # 单选/多选/判断题需要 quesTime，简答/论述题不需要
        if ques_type in (1, 2, 3):
            entry["quesTime"] = random.randint(*ques_time_range)
        elif "quesTime" in entry:
            del entry["quesTime"]

        submit[qid] = entry
    return submit
