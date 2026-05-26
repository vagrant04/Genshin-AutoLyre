"""In-memory store keyed by file_token.

The /api/parse and /api/upload routes save a ParsedMidi here and return
the token. /api/generate looks the record up by token. Lifetime is the
process lifetime — restart clears all tokens, which manifests as
FILE_NOT_FOUND to the client.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from config import ParsedMidi, TrackInfo


@dataclass(frozen=True)
class StoredRecord:
    parsed: ParsedMidi
    title: str
    track_infos: list[TrackInfo]


class ParsedFileStore:
    def __init__(self) -> None:
        self._records: dict[str, StoredRecord] = {}

    def save(
        self,
        parsed: ParsedMidi,
        title: str,
        *,
        track_infos: list[TrackInfo],
    ) -> str:
        token = f"tmp_{secrets.token_hex(8)}"
        self._records[token] = StoredRecord(
            parsed=parsed, title=title, track_infos=track_infos
        )
        return token

    def get(self, token: str) -> StoredRecord:
        return self._records[token]
