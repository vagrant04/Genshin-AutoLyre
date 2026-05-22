"""Async MIDI downloader with size cap and timeout.

Streams the response body to a local path. Aborts and removes the file
if size exceeds 5 MB (spec §8.2.1).
"""
from __future__ import annotations

from pathlib import Path

import httpx

MAX_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0


class DownloadError(Exception):
    """Raised when a download fails or violates the size cap."""


async def download_to_path(
    url: str,
    target: Path,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        async with http.stream("GET", url, timeout=timeout) as response:
            if response.status_code != 200:
                raise DownloadError(
                    f"HTTP {response.status_code} when downloading {url}"
                )
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_BYTES:
                raise DownloadError(
                    f"File exceeds {MAX_BYTES} bytes (declared {content_length})"
                )
            written = 0
            with target.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    written += len(chunk)
                    if written > MAX_BYTES:
                        fh.close()
                        target.unlink(missing_ok=True)
                        raise DownloadError(
                            f"File exceeds {MAX_BYTES} bytes during stream"
                        )
                    fh.write(chunk)
        return target
    except DownloadError:
        target.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {exc}") from exc
    finally:
        if own_client:
            await http.aclose()
