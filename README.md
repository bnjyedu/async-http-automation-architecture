# 异步 HTTP 自动化系统架构

> **作者：[题库大王]**
>
> 面向某自考学习平台的纯 HTTP 自动化系统，采用 Worker-per-Student 架构，每账号独立协程 + 独立 httpx.AsyncClient，实现完全隔离的并发处理。

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![httpx](https://img.shields.io/badge/httpx-0.28.1-green)
![asyncio](https://img.shields.io/badge/asyncio-native-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 核心卖点

- **纯 HTTP 实现**：无浏览器依赖，轻量高效，资源占用低
- **多账号并发**：Worker-per-Student 架构，数百账号同时处理互不干扰
- **崩溃不丢数据**：原子写入 + 断点续学，长时间运行稳定可靠
- **风控友好**：随机间隔、请求级 Referer、并发限制，降低封号风险

## 功能特性

### 业务功能

| 功能 | 说明 |
|------|------|
| 视频课程自动学习 | 进度自动提交，支持断点续学，跳过已完成章节 |
| 阶段测验自动完成 | 自动创建试卷并提交答案，支持满分提交 |
| 补做测试自动答题 | 自动获取题目并提交，支持题型识别与分数计算 |
| 题库自动采集 | 拦截答案并存储到 SQLite，INSERT ON CONFLICT 原子去重 |
| 进度跟踪与统计 | JSON 原子写入，崩溃不丢数据，支持运行时查看进度 |

### 技术亮点

| 特性 | 实现方式 |
|------|---------|
| Worker-per-Student 并发 | 每账号独立协程 + 独立 httpx.AsyncClient + 独立 Cookie Jar |
| 原子写入 | 临时文件 + `os.replace` 替换，`asyncio.Lock` 串行化写操作 |
| Protocol 鸭子类型 | `CourseLike` Protocol 结构化类型，无需继承即可匹配 |
| SQLite 原子 upsert | `INSERT ON CONFLICT DO UPDATE`，无竞态条件 |
| 分层架构 | 依赖方向严格自上而下，低层不反向依赖高层 |
| 按请求级 Referer | 实例级 + 请求级双模式，请求级优先，避免并发竞态 |
| 风控规避 | 随机提交间隔 + 请求级 Referer + `Semaphore` 并发限制 |

## 架构图

```
                    ┌─────────────────────────────────────┐
                    │            main.py (入口)            │
                    │   读取配置 → 加载账号 → 启动引擎      │
                    └─────────────────┬───────────────────┘
                                      │ asyncio.gather
                    ┌─────────────────┼───────────────────┐
                    │                 │                   │
              ┌─────▼─────┐    ┌─────▼─────┐      ┌─────▼─────┐
              │ Worker #1  │    │ Worker #2  │ ...  │ Worker #N  │
              │ (账号 A)   │    │ (账号 B)   │      │ (账号 N)   │
              └─────┬─────┘    └─────┬─────┘      └─────┬─────┘
                    │                 │                   │
              ┌─────▼─────┐    ┌─────▼─────┐      ┌─────▼─────┐
              │ HttpClient │    │ HttpClient │      │ HttpClient │
              │(独立Cookie)│    │(独立Cookie)│      │(独立Cookie)│
              └─────┬─────┘    └─────┬─────┘      └─────┬─────┘
                    │                 │                   │
                    └─────────────────┼───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │          共享存储层                   │
                    │  ┌────────────┐  ┌───────────────┐  │
                    │  │QuestionBank│  │ProgressTracker│  │
                    │  │  (SQLite)  │  │    (JSON)     │  │
                    │  └────────────┘  └───────────────┘  │
                    └─────────────────────────────────────┘
```

**依赖方向**：`main` → `browserless`(未发布) → `{course, player, exam, storage}` → `utils`

`course/models.py`（`HttpCourse` 数据类）无依赖，供所有上层模块导入，避免低层反向依赖高层。

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/bnjyedu/async-http-automation-architecture.git
cd async-http-automation-architecture

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行验证（无副作用，验证关键路径）
python verify.py
```

预期输出：5 项测试全部通过（视频列表解析、课程名匹配、textarea 解析、题库 upsert、xlsx 读取）。

> ⚠️ 本仓库为架构展示项目，核心引擎模块未发布，`main.py` 无法独立运行。详见下方[项目说明](#项目说明)。

## 目录结构

```
├── main.py                 # 主入口（架构展示，依赖未发布的引擎模块）
├── verify.py               # 端到端验证脚本（5 项测试，无副作用）
├── http_client.py          # HTTP 客户端封装（Cookie/Referer/JSONP）
├── constants.example.py    # 常量模板（脱敏，复制为 constants.py 后使用）
├── config.example.yaml     # 配置模板（脱敏，复制为 config.yaml 后使用）
├── pyrightconfig.json      # Pylance 类型检查配置
├── requirements.txt        # 依赖清单
├── wechat_qrcode.jpg       # 作者微信二维码
├── blog.md                 # 技术博客全文
├── README.md               # 项目说明（本文件）
├── course/                 # 课程模块
│   ├── models.py           # 课程数据模型（HttpCourse，无依赖）
│   └── matcher.py          # 课程名匹配（Protocol + 括号归一化）
├── player/                 # 视频模块
│   └── video_list_parser.py # 视频列表 HTML 解析（正则 + 去重）
├── exam/                   # 测验模块（公共工具）
│   └── common.py           # 正则、序列化、答案映射构造
├── storage/                # 存储层
│   ├── question_bank.py    # 题库（SQLite，INSERT ON CONFLICT 原子 upsert）
│   └── progress_tracker.py # 进度跟踪（JSON，os.replace 原子写）
└── utils/                  # 工具
    ├── xlsx_reader.py      # 账号读取（openpyxl）
    ├── logger.py           # 日志（TimedRotatingFileHandler 按日滚动）
    └── time_utils.py       # 时长解析（"36:17" → 秒）
```

## 项目说明

本仓库展示一个纯 HTTP 自动化系统的**架构设计**，聚焦于异步并发、原子写入、分层解耦等工程实践。

⚠️ **这是架构展示项目，非完整可运行系统。** 核心引擎模块和业务逻辑模块未发布，发布的模块展示以下技术能力：

- Worker-per-Student 异步并发架构
- `os.replace` 原子写入 + `asyncio.Lock` 并发保护
- `typing.Protocol` 鸭子类型解耦
- SQLite `INSERT ON CONFLICT` 原子 upsert
- 分层架构与依赖方向控制
- 按请求级 Referer 避免并发竞态

完整设计思路见 [blog.md](blog.md)。

## 适用场景

- 需要为大量独立账号并发执行 HTTP 任务的场景
- 对数据持久性要求高（崩溃不丢数据）的场景
- 需要降低风控风险的批量操作场景
- 学习 Python 异步架构、原子写入、分层设计的工程实践

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| httpx | 0.28.1 | 异步 HTTP 客户端 |
| openpyxl | 3.1.5 | xlsx 文件读取 |
| pyyaml | 6.0.3 | YAML 配置解析 |
| aiosqlite | 0.22.1 | 异步 SQLite |

## 联系方式

<p align="center">
  <img src="wechat_qrcode.jpg" width="220" alt="微信二维码" />
</p>

<p align="center">扫码添加作者微信</p>

## 免责声明

- 本项目仅展示架构设计与工程实践，不包含任何业务实现代码
- `constants.example.py` 和 `config.example.yaml` 中的 URL/盐值均为占位符
- 核心引擎和业务逻辑模块未发布
- 请勿将本项目用于违反平台服务条款的用途

---

*作者：[题库大王]*
