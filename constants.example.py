# 平台共享常量 - 脱敏示例版
#
# 实际使用时:
#   1. 复制本文件为 constants.py
#   2. 将 example.com 替换为实际平台域名
#   3. 将 TOKEN_SALT 占位符替换为实际盐值, 或从 config.yaml 注入
#
# 集中管理 URL/域名/盐值, 避免多文件重复定义。
# 注: 以下 API 路径均为通用示例, 非真实路径。

# 域名(示例值, 实际使用时替换)
GCKH_BASE = "https://gckh.example.com"
MEMBER_BASE = "https://member.example.com"
PLATFORM_HOME = "https://platform.example.com/"
XUEXI_BASE = "https://xuexi.example.com"

# 登录
LOGIN_PAGE = f"{GCKH_BASE}/api/auth/login"

# 视频学习
VIDEO_PLAY_URL = f"{XUEXI_BASE}/api/video/play"
VIDEO_LIST_API = f"{XUEXI_BASE}/api/video/list"
SUBMIT_URL = f"{XUEXI_BASE}/api/video/submit"
TOKEN_SALT = "TOKEN_SALT_PLACEHOLDER"  # 实际盐值从 config.yaml 注入, 不入库

# 阶段测验
STAGE_EXAM_ENTRY = f"{MEMBER_BASE}/api/exam/entry"
STAGE_EXAM_LIST_URL = f"{MEMBER_BASE}/api/exam/list"
STAGE_CREATE_PAPER_URL = f"{MEMBER_BASE}/api/exam/create"
STAGE_FINAL_SUBMIT_URL = f"{MEMBER_BASE}/api/exam/submit"

# 补做测试
PROCESS_EVAL_URL = f"{GCKH_BASE}/api/eval/info"
POINT_ANSWER_ENTRY = f"{MEMBER_BASE}/api/quiz/entry"
POINT_GET_QUES_URL = f"{MEMBER_BASE}/api/quiz/questions"
POINT_SUBMIT_URL = f"{MEMBER_BASE}/api/quiz/submit"
