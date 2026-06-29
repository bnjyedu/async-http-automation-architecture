"""自动化系统主入口。

执行流程：
    1. 加载配置与账号
    2. 引擎：每学生一个 Worker 协程，并发处理
"""
import asyncio
import os
import sys
import traceback
from pathlib import Path

import yaml

# 项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from storage.progress_tracker import ProgressTracker
from storage.question_bank import QuestionBank
from utils.logger import get_logger
from utils.xlsx_reader import read_accounts


CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def load_config() -> dict:
    """加载并校验配置文件。"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 校验 gap 参数形状（必须是 2 元素 list）
    for gap_key in ("submit_gap", "quiz_gap"):
        val = config.get(gap_key)
        if val is not None:
            if isinstance(val, (int, float)):
                config[gap_key] = [val, val]
            elif not (isinstance(val, list) and len(val) == 2):
                raise ValueError(f"配置项 {gap_key} 必须是 [min, max] 列表或标量，当前: {val}")

    return config


async def run_browserless_engine(config: dict, logger, progress: ProgressTracker, question_bank: QuestionBank) -> None:
    """Browserless 引擎：纯 HTTP，多学生并发。"""
    from browserless import run_browserless

    accounts = read_accounts(config["account_file"])
    if not accounts:
        logger.error("账号文件为空或读取失败")
        return

    logger.info(f"加载 {len(accounts)} 条账号记录")
    await run_browserless(accounts, config, logger, progress, question_bank)


async def main():
    """主入口。"""
    config = load_config()
    data_dir = os.path.join(PROJECT_ROOT, config.get("data_dir", "./data"))
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "cookies"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "logs"), exist_ok=True)

    logger = get_logger("automation", data_dir)

    logger.info("=" * 60)
    logger.info("自动化系统启动")
    logger.info(
        f"配置: concurrency={config.get('concurrency', 1)}, resume={config.get('resume')}"
    )
    logger.info("=" * 60)

    progress = ProgressTracker(os.path.join(data_dir, "progress.json"))
    question_bank = QuestionBank(os.path.join(data_dir, "question_bank.db"))
    await question_bank.init()
    logger.info(f"题库初始化完成，当前 {await question_bank.count()} 题")

    stats = progress.summary()
    logger.info(f"进度统计: {stats}")

    try:
        await run_browserless_engine(config, logger, progress, question_bank)
    except KeyboardInterrupt:
        logger.info("用户中断，保存进度后退出")
    except Exception as e:
        logger.error(f"主流程异常: {e}")
        logger.debug(traceback.format_exc())
    finally:
        stats = progress.summary()
        logger.info(f"最终进度: {stats}")
        logger.info(f"题库总量: {await question_bank.count()} 题")
        export_dir = os.path.join(data_dir, "question_bank_by_course")
        try:
            result = await question_bank.export_json_by_course(export_dir)
            for course_name, count in result.items():
                logger.info(f"题库导出 [{course_name}]: {count} 题")
            logger.info(f"题库已按科目导出到目录: {export_dir}")
        except Exception as e:
            logger.error(f"题库导出异常: {e}")

    logger.info("系统退出")


if __name__ == "__main__":
    asyncio.run(main())
