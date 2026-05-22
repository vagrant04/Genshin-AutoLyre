"""Basic Pitch transcription wrapper.

The Basic Pitch model is heavy (~30 s lazy-load on first run). We let
TensorFlow handle that internally on the first `transcribe()` call;
subsequent calls in the same process are fast.

We invoke Basic Pitch in a thread to keep the FastAPI event loop
responsive (Basic Pitch is sync + CPU-bound).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from audio.exceptions import TranscriptionError

_LOG = logging.getLogger(__name__)


SENSITIVITY_PRESETS: dict[str, float] = {
    "low": 0.7,
    "medium": 0.5,
    "high": 0.3,
}

DEFAULT_MIN_NOTE_LENGTH_MS = 60


async def transcribe(
    audio_path: Path,
    midi_out_path: Path,
    *,
    onset_threshold: float = 0.5,
    min_note_length_ms: int = DEFAULT_MIN_NOTE_LENGTH_MS,
) -> Path:
    """Transcribe `audio_path` to `midi_out_path` via Basic Pitch.

    Returns the output path on success. Raises TranscriptionError on any
    failure (missing input, decoder error, model crash).
    """
    if not audio_path.is_file():
        raise TranscriptionError(f"audio file not found: {audio_path}")
    midi_out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await asyncio.to_thread(
            _run_basic_pitch,
            audio_path,
            midi_out_path,
            onset_threshold,
            min_note_length_ms,
        )
    except TranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError(f"basic-pitch failed: {exc}") from exc
    if not midi_out_path.is_file() or midi_out_path.stat().st_size == 0:
        raise TranscriptionError("basic-pitch produced no output")
    return midi_out_path


def _run_basic_pitch(
    audio_path: Path,
    midi_out_path: Path,
    onset_threshold: float,
    min_note_length_ms: int,
) -> None:
    """Sync helper, called via asyncio.to_thread."""
    import scipy.signal
    import scipy.signal.windows

    # Monkey-patch for scipy >=1.11: gaussian moved to windows submodule
    if not hasattr(scipy.signal, 'gaussian'):
        scipy.signal.gaussian = scipy.signal.windows.gaussian

    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

    # Use ONNX model to avoid TensorFlow version compatibility issues
    model_dir = Path(ICASSP_2022_MODEL_PATH).parent
    onnx_model = model_dir / "nmp.onnx"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        predict_and_save(
            audio_path_list=[str(audio_path)],
            output_directory=str(tmp_dir),
            save_midi=True,
            sonify_midi=False,
            save_model_outputs=False,
            save_notes=False,
            model_or_model_path=str(onnx_model),
            onset_threshold=onset_threshold,
            minimum_note_length=min_note_length_ms,
        )
        produced = list(tmp_dir.glob("*_basic_pitch.mid"))
        if not produced:
            raise TranscriptionError(
                "basic-pitch did not produce a .mid output"
            )
        shutil.move(str(produced[0]), str(midi_out_path))
