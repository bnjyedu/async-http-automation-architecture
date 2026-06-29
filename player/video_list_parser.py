"""视频列表 HTML 解析(共享模块)。

解析视频列表接口响应中的 a 节点, 提取 videoID / title / duration / status。

正则容忍属性顺序变化, 与原引擎实现保持一致。
"""
import re
from dataclasses import dataclass
from typing import List


@dataclass
class HttpVideo:
    """视频讲次。"""
    videoID: str
    title: str
    duration: str
    status: str = "未学"


VIDEO_LIST_PATTERN = re.compile(
    r'<a[^>]*\sid="(\d+)"[^>]*>.*?'
    r'<span[^>]*class="fr time"[^>]*data-value="\d+"[^>]*>([^<]+)</span>.*?'
    r'<i[^>]*class="cg fl (leve2_\w+)"[^>]*></i>.*?'
    r'<span[^>]*title="([^"]*)"',
    re.S,
)

VIDEO_STATUS_MAP = {
    "leve2_wx": "未学",
    "leve2_jxz": "学习中",
    "leve2_yx": "已学",
}


def parse_video_list_html(html: str) -> List[HttpVideo]:
    """解析视频列表 HTML，返回 HttpVideo 列表（按 videoID 去重）。"""
    videos: List[HttpVideo] = []
    seen_ids = set()
    for m in VIDEO_LIST_PATTERN.finditer(html):
        video_id = m.group(1)
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        duration = m.group(2).strip()
        level_cls = m.group(3)
        title = m.group(4).strip()
        videos.append(HttpVideo(
            videoID=video_id,
            title=title,
            duration=duration,
            status=VIDEO_STATUS_MAP.get(level_cls, "未学"),
        ))
    return videos
