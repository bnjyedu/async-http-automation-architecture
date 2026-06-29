# 平台共享常量 - 脱敏示例版
#
# 实际使用时：
#   1. 复制本文件为 constants.py
#   2. 将 example.com 替换为实际平台域名
#   3. 将 TOKEN_SALT 占位符替换为实际盐值, 或从 config.yaml 注入
#
# 集中管理 URL/域名/盐值, 避免多文件重复定义。

# 域名（示例值，实际使用时替换）
GCKH_BASE = "https://gckh.example.com"
MEMBER_BASE = "https://member.example.com"
PLATFORM_HOME = "https://platform.example.com/"
XUEXI_BASE = "https://xuexi.example.com"

# 登录
LOGIN_PAGE = f"{GCKH_BASE}/uc/login/toLogin"

# 视频学习
VIDEO_PLAY_URL = f"{XUEXI_BASE}/xcware/video/videoPlay/videoPlayhls.shtm"
VIDEO_LIST_API = f"{XUEXI_BASE}/xcware/video/videoPlay/getVideoList.shtm"
SUBMIT_URL = f"{XUEXI_BASE}/xcware/video/videoPlay/service/saveCwareKcjyTime.shtm"
TOKEN_SALT = "TOKEN_SALT_PLACEHOLDER"  # 实际盐值从 config.yaml 注入，不入库

# 阶段测验
STAGE_EXAM_ENTRY = f"{MEMBER_BASE}/qzgckh/index/indexForGckhJk.shtm"
STAGE_EXAM_LIST_URL = f"{MEMBER_BASE}/qzgckh/index/advcIndexSubGCKH.shtm"
STAGE_CREATE_PAPER_URL = f"{MEMBER_BASE}/web-qz/moni/exam/exam_createPaper.action"
STAGE_FINAL_SUBMIT_URL = f"{MEMBER_BASE}/web-qz/save/save_saveMoniExam.action"

# 补做测试
PROCESS_EVAL_URL = f"{GCKH_BASE}/api/processExamCacheData/processEvaluationInfo"
POINT_ANSWER_ENTRY = f"{MEMBER_BASE}/qzgckh/pointExam/memberPointAnswer.shtm"
POINT_GET_QUES_URL = f"{MEMBER_BASE}/qzgckh/create/testExam/point/getQues4NoCache.shtm"
POINT_SUBMIT_URL = f"{MEMBER_BASE}/qzgckh/paperByCommon/saveAll/saveAllTestQues.shtm"
