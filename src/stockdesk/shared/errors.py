"""错误码与给人看的提示：每个错误都说清出了什么事、下一步怎么做。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    NO_SNAPSHOT = "NO_SNAPSHOT"
    STALE_PRICE = "STALE_PRICE"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    UNSOURCED_NUMBER = "UNSOURCED_NUMBER"
    STALE_NOTES = "STALE_NOTES"
    SELF_REVIEW_FAILED = "SELF_REVIEW_FAILED"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    FX_MISSING = "FX_MISSING"
    NOT_YET_BUILT = "NOT_YET_BUILT"
    BAD_INPUT = "BAD_INPUT"


NEXT_STEP: dict[ErrorCode, str] = {
    ErrorCode.NO_SNAPSHOT: "先运行 `sd fetch` 或 `sd import` 取数。",
    ErrorCode.STALE_PRICE: "重新取价格后再算。",
    ErrorCode.DATA_INCOMPLETE: "按缺口清单补抓；非关键字段补不到时用 `sd import --gap-ack` 登记原因。",
    ErrorCode.SOURCE_CONFLICT: "查原文后用 `sd import` 覆盖并注明。",
    ErrorCode.UNSOURCED_NUMBER: "改正文，或先把这个数字补进数据。",
    ErrorCode.STALE_NOTES: "解读依据的是旧数据，请按新的财报包重写解读。",
    ErrorCode.SELF_REVIEW_FAILED: "按问题清单逐条修改后重试。",
    ErrorCode.SOURCE_BLOCKED: "云端请改用 WebFetch 抓网页，再 `sd import`。",
    ErrorCode.FX_MISSING: "补抓当日汇率。",
    ErrorCode.NOT_YET_BUILT: "这个命令属于后面的施工切片，还没实现。",
    ErrorCode.BAD_INPUT: "检查命令参数。",
}


class StockdeskError(Exception):
    """带错误码的失败。details 放机器可读的细节（缺口清单、问题清单等）。"""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "message": self.message,
            "next_step": NEXT_STEP[self.code],
            "details": self.details,
        }
