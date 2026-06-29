"""SQLite 题库存储模块（异步）。"""
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    questionID    INTEGER PRIMARY KEY,
    questionText  TEXT,
    options       TEXT,
    rightAnswer   TEXT,
    quesType      INTEGER,
    score         REAL,
    splitScore    REAL,
    courseName    TEXT,
    cwareID       INTEGER,
    pointID       INTEGER,
    paperID       INTEGER,
    capturedAt    TEXT,
    analysis      TEXT,
    userAnswer    TEXT,
    serialNum     INTEGER,
    paperViewID   INTEGER,
    paperScoreID  INTEGER,
    submitAt      TEXT
);
CREATE INDEX IF NOT EXISTS idx_questions_cwareID ON questions(cwareID);
CREATE INDEX IF NOT EXISTS idx_questions_pointID ON questions(pointID);
CREATE INDEX IF NOT EXISTS idx_questions_quesType ON questions(quesType);
CREATE INDEX IF NOT EXISTS idx_questions_courseName ON questions(courseName);

CREATE TABLE IF NOT EXISTS exam_records (
    paperScoreID  INTEGER PRIMARY KEY,
    paperViewID   INTEGER,
    paperID       INTEGER,
    siteCourseID  INTEGER,
    courseName    TEXT,
    examName      TEXT,
    score         REAL,
    totalScore    REAL,
    spendTime     INTEGER,
    submitAt      TEXT,
    account       TEXT,
    reviewed      INTEGER DEFAULT 0,
    reviewJson    TEXT
);
CREATE INDEX IF NOT EXISTS idx_exam_records_course ON exam_records(courseName);
CREATE INDEX IF NOT EXISTS idx_exam_records_paperViewID ON exam_records(paperViewID);
CREATE INDEX IF NOT EXISTS idx_exam_records_account ON exam_records(account);
"""

# 新列索引（旧库迁移完成后才能创建，避免 OperationalError）
POST_MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_questions_paperViewID ON questions(paperViewID);
CREATE INDEX IF NOT EXISTS idx_questions_paperScoreID ON questions(paperScoreID);
"""

# 旧库升级：缺失字段列表（ALTER TABLE ADD COLUMN 兼容旧库）
MIGRATION_COLUMNS = [
    ("analysis", "TEXT"),
    ("userAnswer", "TEXT"),
    ("serialNum", "INTEGER"),
    ("paperViewID", "INTEGER"),
    ("paperScoreID", "INTEGER"),
    ("submitAt", "TEXT"),
]


def _ensure_dir(path: str) -> None:
    """安全创建目录（空路径保护）。"""
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)


class QuestionBank:
    """题库异步存储。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        _ensure_dir(db_path)

    async def init(self) -> None:
        """初始化数据库 schema 并执行旧库迁移。"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            # 旧库迁移：检查 questions 表是否缺失新字段
            cursor = await db.execute("PRAGMA table_info(questions)")
            existing_cols = {row[1] for row in await cursor.fetchall()}
            await cursor.close()
            for col, col_type in MIGRATION_COLUMNS:
                if col not in existing_cols:
                    if not (col.isidentifier() and col_type.isidentifier()):
                        raise ValueError(f"非法列名或类型: {col} {col_type}")
                    await db.execute(
                        f"ALTER TABLE questions ADD COLUMN {col} {col_type}"
                    )
            # 新列索引必须在迁移完成后创建（旧库无 paperViewID/paperScoreID 列）
            await db.executescript(POST_MIGRATION_INDEXES)
            await db.commit()

    async def upsert(
        self,
        questionID: int,
        rightAnswer: str,
        quesType: int,
        score: float = 0.0,
        splitScore: float = 0.0,
        courseName: str = "",
        cwareID: int = 0,
        pointID: int = 0,
        paperID: int = 0,
        questionText: str = "",
        options: str = "",
        analysis: str = "",
        userAnswer: str = "",
        serialNum: int = 0,
        paperViewID: int = 0,
        paperScoreID: int = 0,
        submitAt: str = "",
    ) -> bool:
        """原子插入或更新题目（INSERT ... ON CONFLICT，无竞态）。

        Returns:
            True 表示新增，False 表示已存在（已更新）
        """
        captured_at = datetime.now().isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            # 先查是否存在（同连接内无竞态）
            cur_check = await db.execute(
                "SELECT 1 FROM questions WHERE questionID=?", (questionID,)
            )
            is_new = await cur_check.fetchone() is None
            await cur_check.close()

            cursor = await db.execute(
                """INSERT INTO questions
                   (questionID, questionText, options, rightAnswer, quesType, score,
                    splitScore, courseName, cwareID, pointID, paperID, capturedAt,
                    analysis, userAnswer, serialNum, paperViewID, paperScoreID, submitAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(questionID) DO UPDATE SET
                       rightAnswer=excluded.rightAnswer, quesType=excluded.quesType,
                       score=excluded.score, splitScore=excluded.splitScore,
                       courseName=excluded.courseName, cwareID=excluded.cwareID,
                       pointID=excluded.pointID, paperID=excluded.paperID,
                       questionText=CASE WHEN excluded.questionText != '' THEN excluded.questionText ELSE questions.questionText END,
                       options=CASE WHEN excluded.options != '' THEN excluded.options ELSE questions.options END,
                       analysis=CASE WHEN excluded.analysis != '' THEN excluded.analysis ELSE questions.analysis END,
                       userAnswer=excluded.userAnswer, serialNum=excluded.serialNum,
                       paperViewID=excluded.paperViewID, paperScoreID=excluded.paperScoreID,
                       submitAt=excluded.submitAt""",
                (
                    questionID, questionText, options, rightAnswer, quesType, score,
                    splitScore, courseName, cwareID, pointID, paperID, captured_at,
                    analysis, userAnswer, serialNum, paperViewID, paperScoreID, submitAt,
                ),
            )
            await db.commit()
            await cursor.close()
            return is_new

    async def bulk_upsert_review(
        self,
        questions: List[dict],
        course_name: str,
        paper_id: int = 0,
        paper_view_id: int = 0,
        paper_score_id: int = 0,
        submit_at: str = "",
    ) -> int:
        """批量原子 upsert 回顾题目（单连接+事务，性能优）。

        用于 PaperReviewer.review()，避免逐题开连接。

        Args:
            questions: [{questionID, questionText, options(dict), rightAnswer, score, analysis, userAnswer, serialNum}, ...]
            course_name, paper_id, paper_view_id, paper_score_id: 上下文

        Returns:
            处理题目数
        """
        captured_at = submit_at or datetime.now().isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            for q in questions:
                qid = q["questionID"]
                options_str = json.dumps(q.get("options", {}), ensure_ascii=False)
                cursor = await db.execute(
                    """INSERT INTO questions
                       (questionID, questionText, options, rightAnswer, quesType, score,
                        splitScore, courseName, cwareID, pointID, paperID, capturedAt,
                        analysis, userAnswer, serialNum, paperViewID, paperScoreID, submitAt)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(questionID) DO UPDATE SET
                           rightAnswer=excluded.rightAnswer,
                           questionText=CASE WHEN excluded.questionText != '' THEN excluded.questionText ELSE questions.questionText END,
                           options=CASE WHEN excluded.options != '' THEN excluded.options ELSE questions.options END,
                           analysis=CASE WHEN excluded.analysis != '' THEN excluded.analysis ELSE questions.analysis END,
                           userAnswer=excluded.userAnswer, serialNum=excluded.serialNum,
                           paperViewID=excluded.paperViewID, paperScoreID=excluded.paperScoreID,
                           submitAt=excluded.submitAt""",
                    (
                        qid, q.get("questionText", ""), options_str,
                        q.get("rightAnswer", ""), 0, q.get("score", 0.0),
                        0.0, course_name, 0, 0, paper_id, captured_at,
                        q.get("analysis", ""), q.get("userAnswer", ""),
                        q.get("serialNum", 0), paper_view_id, paper_score_id, captured_at,
                    ),
                )
                await cursor.close()
            await db.commit()
            return len(questions)

    async def bulk_update_ques_type(self, answers: dict) -> int:
        """批量补全 quesType（回顾页 HTML 不含题型信息）。

        Args:
            answers: {questionID_str: {quesType, ...}}

        Returns:
            更新行数
        """
        if not answers:
            return 0
        updated = 0
        async with aiosqlite.connect(self.db_path) as db:
            for qid_str, info in answers.items():
                try:
                    qid = int(qid_str)
                except (ValueError, TypeError):
                    continue
                ques_type = int(info.get("quesType", 0) or 0)
                if ques_type == 0:
                    continue
                cursor = await db.execute(
                    "UPDATE questions SET quesType=? "
                    "WHERE questionID=? AND (quesType=0 OR quesType IS NULL)",
                    (ques_type, qid),
                )
                updated += cursor.rowcount if cursor.rowcount > 0 else 0
                await cursor.close()
            await db.commit()
        return updated

    async def upsert_exam_record(
        self,
        paperScoreID: int,
        paperViewID: int,
        paperID: int,
        siteCourseID: int,
        courseName: str,
        examName: str,
        score: float,
        totalScore: float,
        spendTime: int,
        submitAt: str,
        account: str,
        reviewed: int = 0,
        reviewJson: str = "",
    ) -> None:
        """原子插入或更新答题记录（ON CONFLICT，无竞态）。"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO exam_records
                   (paperScoreID, paperViewID, paperID, siteCourseID, courseName, examName,
                    score, totalScore, spendTime, submitAt, account, reviewed, reviewJson)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(paperScoreID) DO UPDATE SET
                       paperViewID=excluded.paperViewID, paperID=excluded.paperID,
                       siteCourseID=excluded.siteCourseID, courseName=excluded.courseName,
                       examName=excluded.examName, score=excluded.score,
                       totalScore=excluded.totalScore, spendTime=excluded.spendTime,
                       submitAt=excluded.submitAt, account=excluded.account,
                       reviewed=excluded.reviewed, reviewJson=excluded.reviewJson""",
                (
                    paperScoreID, paperViewID, paperID, siteCourseID, courseName, examName,
                    score, totalScore, spendTime, submitAt, account, reviewed, reviewJson,
                ),
            )
            await cursor.close()
            await db.commit()

    async def mark_exam_reviewed(self, paperScoreID: int, reviewJson: str = "") -> int:
        """标记某次答题记录为已回顾。

        Returns:
            影响行数（0 表示该记录不存在）
        """
        async with aiosqlite.connect(self.db_path) as db:
            if reviewJson:
                cursor = await db.execute(
                    "UPDATE exam_records SET reviewed=1, reviewJson=? WHERE paperScoreID=?",
                    (reviewJson, paperScoreID),
                )
            else:
                cursor = await db.execute(
                    "UPDATE exam_records SET reviewed=1 WHERE paperScoreID=?",
                    (paperScoreID,),
                )
            rowcount = cursor.rowcount
            await cursor.close()
            await db.commit()
            return rowcount if rowcount > 0 else 0

    async def bulk_upsert_from_intercepted(
        self,
        ans_map: Dict[str, Dict[str, Any]],
        courseName: str = "",
        cwareID: int = 0,
        pointID: int = 0,
        paperID: int = 0,
        questions_content: Optional[Dict[int, dict]] = None,
    ) -> int:
        """批量落库拦截到的答案 map。

        Args:
            ans_map: {questionID_str: {rightAnswer, quesType, score, splitScore, ...}}
            courseName, cwareID, pointID, paperID: 上下文信息
            questions_content: {questionID: {questionText, options: {A:..., B:...}}}
                从 HTML DOM 提取的题目内容，可选

        Returns:
            新增题目数量
        """
        added = 0
        for qid_str, info in ans_map.items():
            try:
                qid = int(qid_str)
            except (ValueError, TypeError):
                continue

            question_text = ""
            options_str = ""
            if questions_content and qid in questions_content:
                qc = questions_content[qid]
                question_text = qc.get("questionText", "")
                opts = qc.get("options", {})
                if opts:
                    options_str = json.dumps(opts, ensure_ascii=False)

            try:
                ques_type = int(info.get("quesType", 0))
            except (ValueError, TypeError):
                ques_type = 0
            try:
                score_val = float(info.get("score", 0.0))
            except (ValueError, TypeError):
                score_val = 0.0
            try:
                split_score = float(info.get("splitScore", 0.0))
            except (ValueError, TypeError):
                split_score = 0.0

            is_new = await self.upsert(
                questionID=qid,
                rightAnswer=str(info.get("rightAnswer", "")),
                quesType=ques_type,
                score=score_val,
                splitScore=split_score,
                courseName=courseName,
                cwareID=cwareID,
                pointID=pointID,
                paperID=paperID,
                questionText=question_text,
                options=options_str,
            )
            if is_new:
                added += 1
        return added

    async def count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM questions")
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else 0

    @staticmethod
    def _write_json_file(path: str, data: list) -> None:
        """同步写 JSON 文件（供 asyncio.to_thread 调用）。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def export_json_by_course(self, output_dir: str) -> dict:
        """按科目分开导出题库为独立 JSON 文件。

        Args:
            output_dir: 输出目录

        Returns:
            {courseName: 导出条数} 字典
        """
        os.makedirs(output_dir, exist_ok=True)
        result: Dict[str, int] = {}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT DISTINCT courseName FROM questions WHERE courseName != '' ORDER BY courseName"
            )
            courses = [row["courseName"] for row in await cursor.fetchall()]
            await cursor.close()

            for course_name in courses:
                cursor = await db.execute(
                    "SELECT * FROM questions WHERE courseName = ? ORDER BY questionID",
                    (course_name,),
                )
                rows = await cursor.fetchall()
                await cursor.close()
                data = [dict(r) for r in rows]

                safe_name = course_name.replace("/", "_").replace("\\", "_").replace(":", "_")
                out_path = os.path.join(output_dir, f"{safe_name}.json")
                await asyncio.to_thread(self._write_json_file, out_path, data)
                result[course_name] = len(data)
        return result

