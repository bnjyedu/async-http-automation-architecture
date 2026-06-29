# 异步 HTTP 自动化系统架构

> **作者：[渝粤题库郭大侠]**
>
> 面向某自考学习平台的纯 HTTP 自动化系统，采用 Worker-per-Student 架构，每账号独立协程 + 独立 httpx.AsyncClient，实现完全隔离的并发处理。

## 项目说明

本仓库展示一个纯 HTTP 自动化系统的**架构设计**，聚焦于异步并发、原子写入、分层解耦等工程实践。

⚠️ **这是架构展示项目，非完整可运行系统。** 核心引擎模块（`browserless.py`）和业务逻辑模块（`exam/`）未发布，因其包含平台逆向细节。发布的模块展示以下技术亮点：

- Worker-per-Student 异步并发架构
- `os.replace` 原子写入 + `asyncio.Lock` 并发保护
- `typing.Protocol` 鸭子类型解耦
- SQLite `INSERT ON CONFLICT` 原子 upsert
- 分层架构与依赖方向控制
- 按请求级 Referer 避免并发竞态

完整设计思路见 [blog.md](blog.md)。

## 目录结构

```
├── main.py                 # 主入口（架构展示，依赖未发布的 browserless 模块）
├── verify.py               # 端到端验证脚本（5 项测试，无副作用）
├── http_client.py          # HTTP 客户端封装（Cookie/Referer/JSONP）
├── constants.example.py    # 常量模板（脱敏，实际使用时复制为 constants.py）
├── config.example.yaml     # 配置模板（脱敏，实际使用时复制为 config.yaml）
├── requirements.txt        # 依赖清单
├── blog.md                 # 技术博客全文
├── course/                 # 课程模块
│   ├── models.py           # 课程数据模型（HttpCourse，无依赖）
│   └── matcher.py          # 课程名匹配（Protocol 鸭子类型 + 括号归一化）
├── player/                 # 视频模块
│   └── video_list_parser.py # 视频列表 HTML 解析（正则 + 去重）
├── storage/                # 存储层
│   ├── question_bank.py    # 题库（SQLite，INSERT ON CONFLICT 原子 upsert）
│   └── progress_tracker.py # 进度跟踪（JSON，os.replace 原子写）
└── utils/                  # 工具
    ├── xlsx_reader.py      # 账号读取（openpyxl）
    ├── logger.py           # 日志（TimedRotatingFileHandler 按日滚动）
    └── time_utils.py       # 时长解析（"36:17" → 秒）
```

## 技术亮点

### 1. Worker-per-Student 异步架构

每个账号一个独立 Worker 协程，持有独立的 HttpClient（独立 httpx.AsyncClient + 独立 Cookie Jar），实现完全隔离：
- Cookie/Referer 不串号
- 异常不扩散（`asyncio.gather(return_exceptions=True)`）
- `asyncio.Semaphore` 限制并发上限

### 2. 原子写入：崩溃不丢数据

进度文件用临时文件 + `os.replace` 原子替换，`asyncio.Lock` 串行化写操作，损坏文件自动备份。

### 3. Protocol 鸭子类型

`CourseLike` Protocol 定义结构化鸭子类型，任何带 `courseName` 属性的对象都能传入匹配函数，无需继承。

### 4. 分层架构

依赖方向严格自上而下。`course/models.py`（`HttpCourse` 数据类）无依赖，供所有上层模块导入，避免低层反向依赖高层。

### 5. 按请求级 Referer

`HttpClient` 支持实例级和按请求级两种 Referer 模式，**按请求级优先**，避免并发竞态。

## 运行验证

发布的 `verify.py` 可独立运行，验证关键路径（无副作用）：

```bash
pip install -r requirements.txt
python verify.py
```

预期输出：5 项测试全部通过。

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| httpx | 0.28.1 | 异步 HTTP 客户端 |
| openpyxl | 3.1.5 | xlsx 文件读取 |
| pyyaml | 6.0.3 | YAML 配置解析 |
| aiosqlite | 0.22.1 | 异步 SQLite |

## 免责声明

- 本项目仅展示架构设计与工程实践，不包含任何平台逆向代码
- `constants.example.py` 和 `config.example.yaml` 中的 URL/盐值均为占位符
- 核心引擎和业务逻辑模块未发布
- 请勿将本项目用于违反平台服务条款的用途

---

*作者：[渝粤题库郭大侠]*
