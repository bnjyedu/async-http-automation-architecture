"""课程数据模型（共享）。

HttpCourse 是平台课程信息的纯数据载体，无副作用、无依赖。
browserless（高层编排）和 exam（低层执行）都从这里导入，
避免低层 exam 模块反向依赖 browserless，违反分层原则。
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class HttpCourse:
    """课程信息。"""
    courseName: str
    courseId: str
    cwareIDJC: Optional[int]
    cwareIDCJ: Optional[int]
    cwIDJC: str = ""
    cwIDCJ: str = ""
    courseIdExt: str = ""
    stagePaper: str = ""
