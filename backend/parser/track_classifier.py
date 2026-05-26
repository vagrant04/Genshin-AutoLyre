"""Track role + chord_type classification.

Pure function over ParsedMidi. Implements spec §8.2.2 priority rules:
  1. Name match (melody / bass / drum keywords)
  2. Pitch-range exclusion (all notes below C3 → bass; all above C6 → ignored;
     fewer than 10 notes → ignored)
  3. Comprehensive scoring among the remainder; highest scorer is melody,
     others are accompaniment.
"""
from __future__ import annotations

from config import ParsedMidi, ParsedNote, ParsedTrack, TrackInfo, TrackRole
from mapper.note_mapper import map_note

_MELODY_KEYWORDS = ("melody", "vocal", "主旋律", "soprano", "lead", "right")
_BASS_KEYWORDS = ("bass", "left", "低音")
_IGNORED_KEYWORDS = ("drum", "perc", "打击")
_MIN_NOTES = 10
_NAME_TIME_TOLERANCE = 30  # ticks; spec §7.3 step 1 also uses 30


def classify_tracks(parsed: ParsedMidi) -> list[TrackInfo]:
    role_by_index: dict[int, TrackRole] = {}
    pending_indices: list[int] = []

    # Pass 1: name + pitch-range + size rules.
    for track in parsed.tracks:
        role = _classify_by_rules(track)
        if role is not None:
            role_by_index[track.index] = role
        else:
            pending_indices.append(track.index)

    # Pass 2: score the remainder; top score = melody, rest = accompaniment.
    # If a melody was already assigned by name in pass 1, all remaining
    # pending tracks become accompaniment instead.
    if pending_indices:
        already_has_melody = TrackRole.MELODY in role_by_index.values()
        scored = sorted(
            pending_indices,
            key=lambda i: _score_track(parsed.tracks[i]),
            reverse=True,
        )
        if already_has_melody:
            for idx in scored:
                role_by_index[idx] = TrackRole.ACCOMPANIMENT
        else:
            role_by_index[scored[0]] = TrackRole.MELODY
            for idx in scored[1:]:
                role_by_index[idx] = TrackRole.ACCOMPANIMENT

    # Build TrackInfo with chord_type detection for accompaniment tracks.
    infos: list[TrackInfo] = []
    for track in parsed.tracks:
        role = role_by_index[track.index]
        chord_type = (
            _detect_chord_type(track.notes)
            if role == TrackRole.ACCOMPANIMENT
            else "none"
        )
        infos.append(
            TrackInfo(
                index=track.index,
                name=track.name,
                note_count=len(track.notes),
                pitch_range=_format_pitch_range(track.notes),
                preview_keys=_preview_keys(track.notes),
                suggested_role=role,
                chord_type=chord_type,
            )
        )
    return infos


def _classify_by_rules(track: ParsedTrack) -> TrackRole | None:
    name_lower = track.name.lower()
    if any(kw in name_lower for kw in _IGNORED_KEYWORDS):
        return TrackRole.IGNORED
    if any(kw in name_lower for kw in _MELODY_KEYWORDS):
        return TrackRole.MELODY
    if any(kw in name_lower for kw in _BASS_KEYWORDS):
        return TrackRole.BASS

    if len(track.notes) < _MIN_NOTES:
        return TrackRole.IGNORED
    if all(n.midi_num < 48 for n in track.notes):
        return TrackRole.BASS
    if all(n.midi_num > 84 for n in track.notes):
        return TrackRole.IGNORED
    return None


def _score_track(track: ParsedTrack) -> float:
    if not track.notes:
        return 0.0
    note_count_score = min(len(track.notes) / 100.0, 1.0)
    in_range = sum(1 for n in track.notes if 60 <= n.midi_num <= 72)
    central_score = in_range / len(track.notes)
    avg_velocity = sum(n.velocity for n in track.notes) / len(track.notes)
    velocity_score = min(avg_velocity / 100.0, 1.0)
    return 0.4 * note_count_score + 0.3 * central_score + 0.3 * velocity_score


def _detect_chord_type(notes: list[ParsedNote]) -> str:
    if not notes:
        return "none"

    sorted_notes = sorted(notes, key=lambda n: n.start_tick)
    groups: list[list[ParsedNote]] = []
    for note in sorted_notes:
        if groups and abs(note.start_tick - groups[-1][0].start_tick) <= _NAME_TIME_TOLERANCE:
            groups[-1].append(note)
        else:
            groups.append([note])

    multi_groups = [g for g in groups if len(g) >= 2]
    multi_ratio = sum(len(g) for g in multi_groups) / len(notes)

    # Arpeggiated heuristic: even spacing + short durations + few simultaneous.
    if len(sorted_notes) >= 4 and not multi_groups:
        intervals = [
            sorted_notes[i + 1].start_tick - sorted_notes[i].start_tick
            for i in range(len(sorted_notes) - 1)
        ]
        if intervals:
            avg = sum(intervals) / len(intervals)
            jitter = max(abs(i - avg) for i in intervals) / max(avg, 1)
            short = all(n.duration_tick <= 480 for n in sorted_notes[:20])
            if jitter <= 0.5 and short:
                return "arpeggiated"

    if multi_ratio > 0.5:
        return "mixed" if any(len(g) == 1 for g in groups) else "chordal"
    return "none"


def _format_pitch_range(notes: list[ParsedNote]) -> str:
    if not notes:
        return ""
    lo = min(n.midi_num for n in notes)
    hi = max(n.midi_num for n in notes)
    return f"{_midi_to_name(lo)}~{_midi_to_name(hi)}"


def _midi_to_name(midi: int) -> str:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return f"{names[midi % 12]}{midi // 12 - 1}"


def _preview_keys(notes: list[ParsedNote]) -> str:
    sample = sorted(notes, key=lambda n: n.start_tick)[:8]
    keys = [map_note(n).key_pc for n in sample]
    return " ".join(keys)
