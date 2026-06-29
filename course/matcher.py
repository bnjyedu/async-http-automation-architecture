"""课程名匹配（共享）。

匹配策略：
    1. 精确匹配 courseName == subject
    2. 括号归一化后匹配（中英文括号互换，因肉眼难辨 "英语（二）" 与 "英语(二)"）

不使用别名表，不使用模糊子串匹配。
要求 xlsx 的 subject、平台 courseName、题库文件名统一使用平台规范名
（如 "马克思主义基本原理"、"英语（二）"）。

使用 typing.Protocol 鸭子类型，兼容 HttpCourse 与任何带 courseName 字段的对象。
"""
from typing import List, Optional, Protocol


class CourseLike(Protocol):
    """鸭子类型：只要有 courseName 字段即可匹配。"""
    courseName: str


def _normalize_brackets(s: str) -> str:
    """归一化括号：英文 () → 中文 （），便于肉眼难辨的括号差异匹配。

    例：
        "英语(二)" → "英语（二）"
        "英语(二)听力" → "英语（二）听力"
    """
    return s.replace("(", "（").replace(")", "）")


def match_course(subject: str, courses: List[CourseLike]) -> Optional[CourseLike]:
    """根据科目名匹配课程。

    Args:
        subject: 学生科目名（xlsx 中的 subject 字段，应为平台规范名）
        courses: 候选课程列表（必须有 courseName 字段）

    Returns:
        匹配到的课程对象，或 None
    """
    subject = subject.strip()

    # 1. 精确匹配
    for course in courses:
        if course.courseName == subject:
            return course

    # 2. 括号归一化后匹配（中英文括号互换）
    subject_norm = _normalize_brackets(subject)
    if subject_norm != subject:
        for course in courses:
            if _normalize_brackets(course.courseName) == subject_norm:
                return course

    return None
