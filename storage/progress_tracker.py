"""断点续学进度跟踪模块。

写入安全设计：
- asyncio.Lock 保护并发写入（同一事件循环内的协程串行化）
- 原子写入：先写临时文件，再 os.replace 原子替换，防止进程崩溃导致文件损坏
- 损坏文件备份：_load() 遇到 JSON 解析失败时备份原文件并告警，而非静默丢弃进度
- 空路径保护：_ensure_dir 对空路径跳过 makedirs，避免崩溃
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _ensure_dir(path: str) -> None:
    """安全创建目录：空路径或无目录部分时跳过。"""
    if not path:
        return
    parent = os.path.dirname(path)
    if not parent:
        return
    os.makedirs(parent, exist_ok=True)


class ProgressTracker:
    """基于 JSON 的进度跟踪器。

    数据结构：
        {
            "<account>": {
                "<course_name>": {
                    "<cwareID>": {
                        "<videoID>": "completed" | "skipped" | "error:<msg>"
                    }
                }
            }
        }

    线程/协程安全：
    - 读方法（is_done/get_status/summary）保持同步，依赖 GIL 保证读一致性
    - 写方法（mark_done/mark_error）为 async，内部用 asyncio.Lock 串行化
    - _save 使用临时文件 + os.replace 原子替换
    """

    def __init__(self, progress_file: str):
        self.progress_file = progress_file
        _ensure_dir(progress_file)
        self._data: Dict[str, Any] = self._load()
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """延迟初始化 Lock，确保绑定到运行中的事件循环。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _load(self) -> Dict[str, Any]:
        """加载进度文件。损坏时备份并返回空 dict，而非静默丢弃。"""
        if not os.path.exists(self.progress_file):
            return {}
        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # 备份损坏文件，避免下次再次加载失败，同时保留现场供排查
            backup = f"{self.progress_file}.corrupt.{int(time.time())}"
            try:
                os.replace(self.progress_file, backup)
                logger.warning(
                    "进度文件损坏已备份: %s -> %s (原因: %s)",
                    self.progress_file, backup, e,
                )
            except OSError as be:
                logger.error(
                    "进度文件损坏且备份失败: %s (原因: %s)", self.progress_file, be,
                )
            return {}

    async def _save(self) -> None:
        """原子写入：先写临时文件，再 os.replace 原子替换。

        os.replace 在同 filesystem 上是原子操作（POSIX rename / Windows MoveFileEx），
        保证进程崩溃时进度文件要么是旧内容要么是新内容，不会出现半截写入。
        """
        tmp = f"{self.progress_file}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, self.progress_file)

    def is_done(self, account: str, course: str, cwareID: str, videoID: str) -> bool:
        """检查指定 videoID 是否已完成（同步读，安全）。"""
        return (
            self._data.get(account, {})
            .get(course, {})
            .get(cwareID, {})
            .get(videoID) == "completed"
        )

    async def mark_done(
        self,
        account: str,
        course: str,
        cwareID: str,
        videoID: str,
        status: str = "completed",
    ) -> None:
        """标记 videoID 状态（async 写，加锁串行化）。

        Args:
            status: "completed" | "skipped" | "error:<msg>"
        """
        async with self._get_lock():
            self._data.setdefault(account, {}).setdefault(course, {}).setdefault(
                cwareID, {}
            )[videoID] = status
            await self._save()

    async def mark_error(
        self, account: str, course: str, cwareID: str, videoID: str, msg: str
    ) -> None:
        """标记错误状态（async 写）。"""
        await self.mark_done(
            account, course, cwareID, videoID, f"error:{msg[:200]}"
        )

    def summary(self, account: Optional[str] = None) -> Dict[str, int]:
        """生成进度统计（同步读，安全）。

        Args:
            account: 指定账号，None 表示全部

        Returns:
            {"completed": N, "skipped": N, "error": N, "pending": N}
        """
        stats = {"completed": 0, "skipped": 0, "error": 0, "pending": 0}
        accounts = [account] if account else list(self._data.keys())
        for acc in accounts:
            for course, cwares in self._data.get(acc, {}).items():
                for cwareID, videos in cwares.items():
                    for vid, status in videos.items():
                        if status == "completed":
                            stats["completed"] += 1
                        elif status == "skipped":
                            stats["skipped"] += 1
                        elif status.startswith("error"):
                            stats["error"] += 1
                        else:
                            stats["pending"] += 1
        return stats
