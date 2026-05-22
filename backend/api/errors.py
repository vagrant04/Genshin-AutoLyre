"""Standard error codes and ApiError exception.

Spec §10. The route handlers raise ApiError; the global handler in
main.py converts them to the documented JSON error envelope.
"""
from __future__ import annotations

from fastapi import status
from pydantic import BaseModel


class ApiErrorPayload(BaseModel):
    error: str
    message: str
    detail: str | None = None


class ApiError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail

    def to_payload(self) -> ApiErrorPayload:
        return ApiErrorPayload(error=self.code, message=self.message, detail=self.detail)


# Code → (HTTP status, default user-facing message). Matches spec §10 table.
ERROR_CATALOG: dict[str, tuple[int, str]] = {
    "SEARCH_FAILED": (status.HTTP_500_INTERNAL_SERVER_ERROR, "全部搜索源不可用，请稍后重试。"),
    "DOWNLOAD_FAILED": (status.HTTP_400_BAD_REQUEST, "MIDI 文件下载失败。"),
    "FILE_TOO_LARGE": (status.HTTP_400_BAD_REQUEST, "文件超过 5MB 限制。"),
    "PARSE_FAILED": (status.HTTP_400_BAD_REQUEST, "MIDI 解析失败，请尝试其他文件。"),
    "INVALID_FILE_TYPE": (status.HTTP_400_BAD_REQUEST, "请上传 .mid 或 .midi 文件。"),
    "NO_MELODY_TRACK": (status.HTTP_400_BAD_REQUEST, "请至少指定一条主旋律轨道。"),
    "FILE_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "文件已过期，请重新解析。"),
    "INVALID_TRACK_INDEX": (status.HTTP_400_BAD_REQUEST, "轨道索引无效。"),
}


def make_error(code: str, *, detail: str | None = None) -> ApiError:
    http_status, default_message = ERROR_CATALOG[code]
    return ApiError(
        code=code,
        message=default_message,
        http_status=http_status,
        detail=detail,
    )
