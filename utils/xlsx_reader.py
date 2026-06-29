"""读取学生账号.xlsx 模块。"""
from dataclasses import dataclass
from typing import List

import openpyxl


@dataclass
class Account:
    """学生账号信息。"""
    serial: int           # 序号
    name: str             # 姓名
    account: str          # 账号（身份证号）
    password: str         # 密码
    subject: str          # 科目

    def __repr__(self) -> str:
        return f"Account(name={self.name!r}, account={self.account!r}, subject={self.subject!r})"


def read_accounts(xlsx_path: str) -> List[Account]:
    """读取学生账号 Excel 文件。

    Excel 结构（来自 account_file 配置指定的 xlsx 文件）：
        序号 | 姓名 | 账号 | 密码 | 科目

    Args:
        xlsx_path: xlsx 文件路径

    Returns:
        Account 列表
    """
    accounts: List[Account] = []
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        ws = wb.active
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            if not row or not row[0]:
                continue
            try:
                accounts.append(
                    Account(
                        serial=int(row[0]),
                        name=str(row[1]).strip() if row[1] is not None else "",
                        account=str(row[2]).strip() if row[2] is not None else "",
                        password=str(row[3]).strip() if row[3] is not None else "",
                        subject=str(row[4]).strip() if row[4] is not None else "",
                    )
                )
            except (IndexError, ValueError, TypeError) as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"跳过第 {i+1} 行（数据不完整或格式错误）: {e}"
                )
    finally:
        wb.close()
    return accounts
