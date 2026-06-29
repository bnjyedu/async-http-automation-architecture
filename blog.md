# 用 Python 异步架构构建高并发 HTTP 自动化系统：从设计到落地

> **作者：[题库大王]**
>
> 本文记录一个面向某自考学习平台的纯 HTTP 自动化系统架构演进过程，聚焦于异步并发、原子写入、分层解耦等工程实践。系统需要为数百个独立账号并发执行 HTTP 任务（登录、数据提交、状态跟踪），每个账号隔离运行、互不污染。

## 背景

需求很简单：为某自考学习平台构建自动化客户端，要求：

- 同时处理多个账号，每个账号独立 Cookie/会话
- 长时间运行，断点续传，崩溃不丢数据
- 并发提交不能触发平台风控
- 多类型任务（数据采集 + 表单提交）顺序执行，共享同一会话

技术栈选型：Python 3.8+ + httpx（异步 HTTP）+ SQLite（题库）+ openpyxl（账号读取）。不依赖浏览器，纯 HTTP 实现。

## 核心架构：Worker-per-Student

### 问题

多个账号并发时，最直观的方案是共享一个 `httpx.AsyncClient`。但这会导致：

1. **Cookie 串号**：A 账号登录后，B 账号的请求带上 A 的 Cookie
2. **Referer 竞态**：A 设置 Referer 后，B 的请求在 A 的 Referer 下发出
3. **一崩全崩**：一个账号异常影响所有账号

### 解决方案

每个账号一个独立 `Worker` 协程，持有独立的 `HttpClient`（独立 `httpx.AsyncClient` + 独立 Cookie Jar）：

```python
class BrowserlessWorker:
    """每学生一个独立协程，独立 HttpClient，独立 Cookie Jar。"""

    def __init__(self, account, config, logger, progress, question_bank):
        self.account = account
        self.client = HttpClient(logger)  # 独立实例
        self.login_mgr = HttpLoginManager(self.client, logger, config)
        self.catalog = HttpCourseCatalog(self.client, logger)
        self.submitter = HttpCompletionSubmitter(self.client, logger, config)

    async def run(self) -> dict:
        stats = {"completed": 0, "error": 0, "skipped": 0}
        try:
            await self.client.open()
            # 顺序执行：视频和测验共享同一 HttpClient，
            # 并发会导致 set_referer 互相覆盖（Referer 竞态）
            await self._process_videos(matched, stats)
            await self._process_quizzes(matched, stats)
        finally:
            await self.client.close()
        return stats
```

并发控制用 `asyncio.Semaphore` + `asyncio.gather(return_exceptions=True)`：

```python
async def run_browserless(accounts, config, logger, progress, question_bank):
    concurrency = int(config.get("concurrency", 1))
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_run(account):
        async with semaphore:
            worker = BrowserlessWorker(account, config, logger, progress, question_bank)
            return await worker.run()

    # return_exceptions=True：单个 Worker 异常不影响其他
    results = await asyncio.gather(
        *[bounded_run(acc) for acc in accounts], return_exceptions=True
    )
```

关键点：
- `Semaphore` 限制并发上限，避免触发风控
- `return_exceptions=True` 隔离异常，一个账号失败不拖垮全局
- 同一 Worker 内的任务**顺序执行**（共享 HttpClient，并发会 Referer 竞态）

## 分层架构与依赖方向

### 问题

初版代码把所有逻辑堆在一个文件里，导致：
- 低层模块（如测验执行器）反向依赖高层模块（如主引擎）
- 循环导入靠延迟导入（`from xxx import yyy` 写在函数内）规避，丑陋且脆弱

### 解决方案

严格分层，依赖方向自上而下：

```
高层编排    browserless.py  →  Worker 调度、视频学习、测验触发
              ↓
业务模块    exam/           →  测验执行
            course/         →  课程匹配、课程数据模型
            player/         →  视频列表解析
              ↓
存储层      storage/        →  题库（SQLite）、进度跟踪（JSON 原子写）
              ↓
基础设施    http_client.py  →  httpx 封装
            constants.py    →  URL/域名集中管理
            utils/          →  工具函数
```

### 关键设计：共享数据类独立成模块

`HttpCourse` 是平台课程信息的纯数据载体，被高层引擎和低层测验模块共同使用。如果定义在高层 `browserless.py`，低层 `exam/` 反向导入就会形成循环依赖。

解法：把 `HttpCourse` 提取到无依赖的 `course/models.py`：

```python
# course/models.py
"""课程数据模型（共享）。

HttpCourse 是纯数据载体，无副作用、无依赖。
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
```

依赖方向变为：
- 重构前：`exam` → `browserless` → `exam`（循环，靠延迟导入规避）
- 重构后：`exam` → `course.models`，`browserless` → `course.models`（无循环）

## 原子写入：崩溃不丢数据

### 进度文件（JSON）

进度文件记录每个账号每节课的完成状态，长时间运行中可能随时被中断（Ctrl+C、进程崩溃、断电）。要求：**写入要么完整成功，要么不变**。

方案：临时文件 + `os.replace` 原子替换。

```python
async def _save(self) -> None:
    """原子写入：先写临时文件，再 os.replace 原子替换。

    os.replace 在同一 filesystem 上是原子操作（POSIX rename /
    Windows MoveFileEx），保证进程崩溃时进度文件要么是旧内容
    要么是新内容，不会出现半截写入。
    """
    tmp = f"{self.progress_file}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(self._data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())  # 强制刷盘
        except OSError:
            pass
    os.replace(tmp, self.progress_file)  # 原子替换
```

并发保护：`asyncio.Lock` 串行化写操作。

```python
class ProgressTracker:
    def __init__(self, progress_file: str):
        self._data = self._load()
        self._lock: Optional[asyncio.Lock] = None  # 延迟初始化，绑定到运行中的事件循环

    def _get_lock(self) -> asyncio.Lock:
        """延迟初始化 Lock，确保绑定到运行中的事件循环。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def mark_done(self, account, course, cwareID, videoID, status="completed"):
        async with self._get_lock():
            self._data.setdefault(account, {}).setdefault(course, {}).setdefault(
                cwareID, {}
            )[videoID] = status
            await self._save()
```

损坏恢复：加载时若 JSON 解析失败，备份原文件而非静默丢弃。

```python
def _load(self) -> Dict[str, Any]:
    """加载进度文件。损坏时备份并返回空 dict，而非静默丢弃。"""
    if not os.path.exists(self.progress_file):
        return {}
    try:
        with open(self.progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        backup = f"{self.progress_file}.corrupt.{int(time.time())}"
        try:
            os.replace(self.progress_file, backup)
            logger.warning("进度文件损坏已备份: %s -> %s", self.progress_file, backup)
        except OSError:
            logger.error("进度文件损坏且备份失败: %s", self.progress_file)
        return {}
```

### 题库（SQLite）

SQLite 的 `INSERT ... ON CONFLICT DO UPDATE` 天然原子，无需额外锁：

```python
async def upsert(self, questionID, rightAnswer, quesType, ...):
    async with aiosqlite.connect(self.db_path) as db:
        cursor = await db.execute(
            """INSERT INTO questions (questionID, questionText, ...)
               VALUES (?, ?, ...)
               ON CONFLICT(questionID) DO UPDATE SET
                   rightAnswer=excluded.rightAnswer,
                   questionText=CASE WHEN excluded.questionText != ''
                                THEN excluded.questionText
                                ELSE questions.questionText END,
                   ...""",
            (questionID, questionText, ...),
        )
        await db.commit()
```

`CASE WHEN` 实现"仅在新值非空时覆盖"，避免空值覆盖已有数据。

## Protocol 鸭子类型：解耦匹配逻辑

### 问题

课程名匹配函数需要接受多种课程对象（HTTP 响应对象、测试 mock 对象等），但不想耦合到具体类。

### 解决方案

用 `typing.Protocol` 定义结构化鸭子类型：

```python
# course/matcher.py
from typing import List, Optional, Protocol


class CourseLike(Protocol):
    """鸭子类型：只要有 courseName 字段即可匹配。"""
    courseName: str


def match_course(subject: str, courses: List[CourseLike]) -> Optional[CourseLike]:
    """根据科目名匹配课程。

    匹配策略：
        1. 精确匹配 courseName == subject
        2. 括号归一化后匹配（中英文括号互换，因肉眼难辨 "英语(二)" 与 "英语（二）"）

    不使用别名表，不使用模糊子串匹配。
    """
    subject = subject.strip()

    # 1. 精确匹配
    for course in courses:
        if course.courseName == subject:
            return course

    # 2. 括号归一化后匹配
    subject_norm = _normalize_brackets(subject)
    if subject_norm != subject:
        for course in courses:
            if _normalize_brackets(course.courseName) == subject_norm:
                return course

    return None
```

好处：
- 任何带 `courseName` 属性的对象都能传入（HTTP 响应、`SimpleNamespace`、mock 对象）
- 静态类型检查器能验证结构一致性
- 测试时不需要构造完整对象，`SimpleNamespace(courseName="xxx")` 即可

## 按请求级 Referer：避免并发竞态

### 问题

`httpx.AsyncClient` 的 Referer 是实例级状态。多个协程共享同一 client 时，A 设置 Referer 后、B 的请求发出前，B 也设置了 Referer，导致 A 的请求带上 B 的 Referer。

### 解决方案

`HttpClient` 支持两种 Referer 模式，**按请求级优先**：

```python
class HttpClient:
    def __init__(self, logger):
        self._referer: Optional[str] = None  # 实例级

    def set_referer(self, url: str) -> None:
        """设置实例级默认 Referer。"""
        self._referer = url

    def _build_headers(self, extra=None, referer=None) -> dict:
        headers = {}
        # 按请求级 referer 优先于实例级
        effective_referer = referer if referer is not None else self._referer
        if effective_referer:
            headers["Referer"] = effective_referer
        if extra:
            headers.update(extra)
        return headers

    async def get(self, url, params=None, headers=None, referer=None):
        resp = await self._client.get(
            url, params=params, headers=self._build_headers(headers, referer)
        )
        return resp
```

同一 Worker 内的任务**顺序执行**（避免 set_referer 互相覆盖），跨 Worker 各自独立 client（无共享状态）。

## 共享常量集中管理

### 问题

URL、域名、盐值等常量散落在多个文件，修改时容易遗漏，导致不一致。

### 解决方案

提取到 `constants.py` 单一数据源：

```python
# constants.py
# 平台共享常量 - URL/域名/盐值集中管理, 避免多文件重复定义
# 注: 以下 API 路径均为通用示例, 非真实路径
GCKH_BASE = "https://gckh.example.com"
MEMBER_BASE = "https://member.example.com"

# 登录
LOGIN_PAGE = f"{GCKH_BASE}/api/auth/login"

# 视频学习
VIDEO_PLAY_URL = f"{XUEXI_BASE}/api/video/play"
SUBMIT_URL = f"{XUEXI_BASE}/api/video/submit"
TOKEN_SALT = "TOKEN_SALT_PLACEHOLDER"  # 实际盐值不入库, 运行时从 config.yaml 注入

# 阶段测验
STAGE_CREATE_PAPER_URL = f"{MEMBER_BASE}/api/exam/create"
STAGE_FINAL_SUBMIT_URL = f"{MEMBER_BASE}/api/exam/submit"
```

所有模块从 `constants` 导入，修改 URL 只需改一处。

## 工程化实践

### 配置校验

`gap` 参数（如 `submit_gap: [3, 6]`）支持标量或列表，启动时统一规范化：

```python
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for gap_key in ("submit_gap", "quiz_gap"):
        val = config.get(gap_key)
        if val is not None:
            if isinstance(val, (int, float)):
                config[gap_key] = [val, val]  # 标量 → [val, val]
            elif not (isinstance(val, list) and len(val) == 2):
                raise ValueError(
                    f"配置项 {gap_key} 必须是 [min, max] 列表或标量，当前: {val}"
                )
    return config
```

### 端到端验证脚本

独立的 `verify.py` 验证关键路径（HTML 解析、课程匹配、textarea 解析、题库 upsert、xlsx 读取），无副作用，启动前一键自检：

```python
def test_course_match():
    """验证课程名匹配（精确 + 中英文括号归一化）。"""
    from types import SimpleNamespace
    courses = [
        SimpleNamespace(courseName="马克思主义基本原理"),
        SimpleNamespace(courseName="英语（二）"),
    ]

    # 精确匹配
    matched = match_course("马克思主义基本原理", courses)
    assert matched is not None

    # 中英文括号归一化
    matched = match_course("英语(二)", courses)  # 英文括号
    assert matched.courseName == "英语（二）"

    # 别名应不匹配
    matched = match_course("马原", courses)
    assert matched is None
```

### 按日滚动日志

`TimedRotatingFileHandler` 按日切割，保留 30 天，DEBUG 写文件 + INFO 输出控制台：

```python
def get_logger(name="automation", data_dir="./data") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    log_file = os.path.join(data_dir, "logs", f"run_{datetime.now():%Y%m%d}.log")
    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=30, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    ))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger
```

## 总结

这个项目的核心技术点：

| 问题 | 方案 | 收益 |
|------|------|------|
| 多账号并发隔离 | Worker-per-Student + 独立 HttpClient | Cookie/Referer 不串号，异常不扩散 |
| 循环依赖 | 共享数据类独立成模块（`course/models.py`） | 依赖方向自上而下，无延迟导入 |
| 崩溃丢数据 | 临时文件 + `os.replace` 原子替换 | 写入要么完整成功要么不变 |
| 并发写竞态 | `asyncio.Lock` 串行化 | 同一事件循环内写操作串行 |
| JSON 损坏 | 加载时备份 + 返回空 dict | 保留现场供排查，不静默丢数据 |
| 类耦合 | `typing.Protocol` 鸭子类型 | 任何带 courseName 的对象可传入 |
| Referer 竞态 | 按请求级 Referer 优先于实例级 | 并发请求 Referer 不互相覆盖 |
| 常量散落 | `constants.py` 单一数据源 | 修改 URL 只改一处 |

工程上最大的体会：**异步并发 + 共享状态是万恶之源**。能顺序执行就顺序执行（同一 Worker 内），必须并发时用独立实例（Worker 间）或锁（共享状态）。`os.replace` 和 `INSERT ON CONFLICT` 这类原子原语比手写锁更可靠。

## 实现成果

系统已稳定落地运行，覆盖自考学习平台的全流程自动化：

### 功能完成度

| 模块 | 功能 | 状态 |
|------|------|------|
| HTTP 登录 | 身份证号 → memberId → sid → 完整鉴权 Cookie | ✅ 已实现 |
| 课程匹配 | xlsx 科目 ↔ 平台课程（精确 + 括号归一化） | ✅ 已实现 |
| 视频学习 | 播放页解析 → h5Vars 提取 → 构造 studyTimeStr + token → 提交完成 | ✅ 已实现 |
| 补做测试 | 表单解析 → 题目提取 → 满分提交 | ✅ 已实现 |
| 阶段测验 | 8 步流程（创建试卷 → 临时保存 → 最终提交 → 清理） | ✅ 已实现 |
| 试卷回顾 | 提交后回顾试卷，落库完整题目 + 选项 + 答案 + 解析 | ✅ 已实现 |
| 断点续学 | 进度跟踪 + 崩溃恢复 + 满分测验跳过 | ✅ 已实现 |
| 题库导出 | 按科目自动导出 JSON（平台规范名命名） | ✅ 已实现 |

### 实际运行表现

- **账号隔离**：多账号并发运行，Cookie/Referer 零串号
- **风控规避**：通过 `submit_delay`（≥8s）+ `submit_gap`（3-6s）+ `quiz_gap`（5-10s）三层间隔控制，未触发平台风控
- **数据完整性**：`os.replace` 原子写 + `asyncio.Lock` 并发保护，多次中断重启后进度文件无损
- **题库积累**：阶段测验提交后自动回顾落库，题库持续增长，支持后续按科目导出
- **可维护性**：分层架构 + 共享模块提取，新增课程无需改代码（只需 xlsx 填写规范科目名）

### 工程指标

| 指标 | 数值 |
|------|------|
| 代码文件 | 20+ Python 模块 |
| 共享模块 | 3 个（constants / course.models / course.matcher） |
| 依赖项 | 4 个（httpx / openpyxl / pyyaml / aiosqlite） |
| 静态检查 | pyflakes 零警告 |
| 端到端验证 | 5 项测试全部通过 |
| 断点续学 | 支持（进度文件原子写 + 损坏自动备份） |

系统从初版单文件堆砌，经三轮重构演化为分层架构，最终实现：**纯 HTTP 无浏览器依赖、多账号隔离并发、崩溃不丢数据、题库自动积累**的稳定运行。

---

*本文聚焦架构设计与工程实践，隐去了平台具体信息和逆向细节。*

*作者：[题库大王]*


