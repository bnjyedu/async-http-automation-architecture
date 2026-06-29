"""时间相关工具函数。"""


def parse_duration(duration_str: str) -> int:
    """将时长字符串转换为秒。

    支持格式:
        "36:17" -> 36*60 + 17 = 2177
        "1:23:45" -> 1*3600 + 23*60 + 45 = 5025
        "2177" -> 2177
    """
    s = duration_str.strip()
    if not s:
        return 0

    if ":" not in s:
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    parts = s.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return 0

    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0
