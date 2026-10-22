"""Narration inputs and licensed mixes for the isolated stickman pipeline.

Imported SRT timing is operator supplied, not proof of acoustic synchronization.
Only real provider timestamps may create a missing SRT; estimated speech timing
is deliberately unavailable. The caller holds the episode's generation lock.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from ..audio_library import AudioLibrary
from ..editing.manifest import clean_script
from ..fish_voice import FishVoiceClient
from ..media.ffprobe import probe_media, stream_durations
from ..state import write_json_atomic


class StickmanAudioError(ValueError):
    pass


_TIMECODE = r"(?P<{}>\d{{2,}}:[0-5]\d:[0-5]\d,\d{{3}})"
_TIMING = re.compile(_TIMECODE.format("start") + r"\s+-->\s+" + _TIMECODE.format("end"))


def _seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    try:
        result = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000
        if not math.isfinite(result):
            raise ValueError
        return result
    except (ValueError, OverflowError):
        raise StickmanAudioError("SRT time must be finite") from None


def _validate_cues(cues: list[dict], *, duration: float | None = None) -> None:
    if not cues:
        raise StickmanAudioError("SRT must contain at least one cue")
    previous = 0.0
    for index, cue in enumerate(cues, 1):
        try:
            start, end = float(cue["start"]), float(cue["end"])
            valid = (cue["index"] == index and not isinstance(cue["index"], bool)
                     and isinstance(cue["text"], str) and bool(cue["text"].strip())
                     and math.isfinite(start) and math.isfinite(end)
                     and 0 <= previous <= start < end)
        except (TypeError, ValueError, KeyError, OverflowError):
            valid = False
        if not valid:
            raise StickmanAudioError("SRT cues must be sequential, nonempty, finite and nonoverlapping")
        if duration is not None and end > duration + .001:
            raise StickmanAudioError("SRT cue exceeds the measured narration duration")
        previous = end


def parse_srt(text: str) -> list[dict]:
    """Strict numbered SRT, including UTF-8 BOM and Windows newlines."""
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    cues = []
    for block in re.split(r"\n[ \t]*\n", text):
        lines = block.splitlines()
        if len(lines) < 3 or not re.fullmatch(r"[1-9]\d*", lines[0].strip()):
            raise StickmanAudioError("Malformed SRT: expected numbered cues and timestamps")
        match = _TIMING.fullmatch(lines[1].strip())
        if match is None:
            raise StickmanAudioError("Malformed SRT time: expected HH:MM:SS,mmm --> HH:MM:SS,mmm")
        cues.append({"index": int(lines[0].strip()), "start": _seconds(match["start"]),
                     "end": _seconds(match["end"]), "text": "\n".join(lines[2:]).strip()})
    _validate_cues(cues)
    return cues


def read_srt(path: Path) -> list[dict]:
    try:
        return parse_srt(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError) as error:
        raise StickmanAudioError("Cannot read UTF-8 narration SRT") from error


def format_srt(cues: list[dict]) -> str:
    _validate_cues(cues)

    def stamp(value):
        milliseconds = round(float(value) * 1000)
        seconds, millis = divmod(milliseconds, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    result = "\n\n".join(f"{cue['index']}\n{stamp(cue['start'])} --> {stamp(cue['end'])}\n{cue['text']}" for cue in cues) + "\n"
    # Quantizing sub-millisecond provider data must not create invalid cues.
    parse_srt(result)
    return result


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tokens(text: str) -> list[str]:
    return [match.group().casefold() for match in re.finditer(r"\w+", clean_script(text))]


def _state(episode: Path) -> Path:
    directory = episode / ".stickman"
    if directory.is_symlink():
        raise StickmanAudioError("Episode audio state cannot be a symlink")
    directory.mkdir(exist_ok=True)
    return directory


def _read_record(path: Path) -> dict | None:
    if path.is_symlink():
        raise StickmanAudioError("Audio receipt cannot be a symlink")
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("version") != 1:
            raise ValueError
        return record
    except (OSError, ValueError):
        raise StickmanAudioError("Invalid audio receipt; preserve it and review before resuming") from None


def _new_text(path: Path, content: str) -> None:
    """Promote a fully written file without replacing any operator artifact."""
    fd, temporary = tempfile.mkstemp(prefix=".stickman-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise StickmanAudioError("Narration SRT already exists; it was preserved") from None
    finally:
        os.unlink(temporary)


def _provider_segments(path: Path, script: str, duration: float) -> list[dict]:
    """Validate original Fish segments without inventing intra-segment timestamps."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("method") != "fish_provider_timestamps":
            raise ValueError
        words = data["words"]
        if not isinstance(words, list) or not words:
            raise ValueError
        segments, transcript, previous = [], [], 0.0
        for word in words:
            if (not isinstance(word, dict) or not isinstance(word.get("word"), str)
                    or isinstance(word.get("start"), bool) or isinstance(word.get("end"), bool)):
                raise ValueError
            start, end = float(word["start"]), float(word["end"])
            tokens = _tokens(word["word"])
            if (not tokens or not math.isfinite(start) or not math.isfinite(end)
                    or not previous <= start <= end <= duration + .001):
                raise ValueError
            previous = end
            transcript.extend(tokens)
            segments.append({"word": word["word"], "start": start, "end": end})
        if transcript != _tokens(script):
            raise ValueError
        return segments
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise StickmanAudioError(
            "Missing or invalid full-transcript Fish alignment. Provide a real aligned voz.srt; "
            "audio was preserved, with no estimated timing or second synthesis."
        ) from None


def _provider_cues(path: Path, script: str, duration: float) -> list[dict]:
    try:
        segments = _provider_segments(path, script, duration)
        expanded = [(token, word["start"], word["end"])
                    for word in segments for token in _tokens(word["word"])]
        spoken = clean_script(script)
        spans = list(re.finditer(r"\w+", spoken))
        cues, cursor = [], 0
        while cursor < len(expanded):
            start = expanded[cursor][1]
            # Safe boundaries respect whole provider segments, including a
            # hyphenated word expanded into several lexical tokens at one time.
            boundaries = [end for end in range(cursor, len(expanded))
                          if expanded[end][2] > start
                          and (end == len(expanded) - 1 or expanded[end + 1][1] >= expanded[end][2])]
            if not boundaries:
                if not cues:
                    raise ValueError
                # A terminal run of instantaneous tokens cannot form its own
                # positive-duration subtitle. Attach its text to the preceding
                # cue and use the final provider endpoint, even across silence.
                cues[-1]["text"] += " " + " ".join(spoken[spans[cursor].start():].split())
                cues[-1]["end"] = expanded[-1][2]
                break
            within = [end for end in boundaries if expanded[end][2] - start <= 3.0]
            # Do not split a long sentence only at its final punctuation: the
            # visual planner needs genuine boundaries roughly every five seconds.
            # Prefer real clause punctuation once a chunk has a useful duration.
            punctuated = [end for end in within if expanded[end][2] - start >= 1
                          and re.search(r"[.!?;:,]", spoken[spans[end].end():
                              spans[end + 1].start() if end + 1 < len(spans) else len(spoken)])]
            end = (punctuated or within or boundaries[:1])[-1]
            char_start = 0 if cursor == 0 else spans[cursor].start()
            char_end = spans[end + 1].start() if end + 1 < len(spans) else len(spoken)
            cues.append({"index": len(cues) + 1, "start": start,
                         "end": expanded[end][2],
                         # Script paragraphs must not become SRT block separators.
                         "text": " ".join(spoken[char_start:char_end].split())})
            cursor = end + 1
        _validate_cues(cues, duration=duration)
        # Persist and subsequently consume precisely the same millisecond clock.
        return parse_srt(format_srt(cues))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise StickmanAudioError(
            "Missing or invalid full-transcript Fish alignment. Provide a real aligned voz.srt; "
            "audio was preserved, with no estimated timing or second synthesis."
        ) from None


def prepare_narration(episode: Path, *, root: Path, settings, voice: dict | None = None,
                      generate: bool = False) -> dict:
    """Validate/reuse narration; generating new Fish audio requires explicit opt-in."""
    episode = Path(episode).absolute()
    audio, srt, script_path = (episode / name for name in ("voz.mp3", "voz.srt", "guion_final.txt"))
    alignment = audio.with_suffix(".alignment.json")
    if any(path.is_symlink() for path in (audio, srt, script_path, alignment)):
        raise StickmanAudioError("Narration inputs cannot be symlinks")
    try:
        script = script_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise StickmanAudioError("A UTF-8 guion_final.txt is required") from error
    if not _tokens(script):
        raise StickmanAudioError("The final narration script is empty")
    script_sha = _hash(script_path)
    state = _state(episode)
    receipt_path = state / "narration.json"
    receipt = _read_record(receipt_path)
    request_path = state / "voice_request.json"
    request = _read_record(request_path)
    # A previously accepted pair cannot silently adopt a different audio/script/SRT.
    if receipt and (receipt.get("script_sha256") != script_sha
                    or not audio.is_file() or not srt.is_file()
                    or receipt.get("audio_sha256") != _hash(audio)
                    or receipt.get("srt_sha256") != _hash(srt)):
        raise StickmanAudioError("Narration inputs changed after validation; preserve receipts and use a new episode revision")
    if request and request.get("script_sha256") != script_sha:
        raise StickmanAudioError("The script changed after a Fish request; review the original paid audio")
    if not audio.is_file():
        if not generate:
            raise StickmanAudioError("Missing voz.mp3: import existing audio or explicitly generate with configured Fish voice")
        voice = voice or {}
        reference_id = voice.get("reference_id")
        if not isinstance(reference_id, str) or not reference_id.strip():
            raise StickmanAudioError("Fish generation requires an explicit voice reference_id")
        identity = {"reference_id": reference_id, "model": voice.get("model") or settings.fish_model,
                    "speed": voice.get("speed", 1.0)}
        if request and request.get("voice") != identity:
            raise StickmanAudioError("Fish voice settings changed after a request; inspect the original operation")
        if not request:
            write_json_atomic(request_path, {"version": 1, "script_sha256": script_sha, "voice": identity})
        # A paid result is written to private state before exclusive promotion.
        # An operator-created voz.mp3 appearing during the request is preserved.
        staged_audio = state / "fish-voz.mp3"
        staged_alignment = staged_audio.with_suffix(".alignment.json")
        if staged_audio.is_symlink() or staged_alignment.is_symlink():
            raise StickmanAudioError("Staged Fish audio cannot be a symlink")
        client = FishVoiceClient(
            settings.fish_api_key.get_secret_value(), identity["model"],
            timeout=settings.fish_tts_timeout_seconds, cache_dir=settings.audio_cache_dir,
            timestamps=True, ffprobe=settings.ffprobe_binary,
        )
        try:
            if not staged_audio.exists():
                client.synthesize(script.strip(), reference_id, staged_audio, speed=identity["speed"])
        finally:
            client.close()
        try:
            os.link(staged_audio, audio)
        except FileExistsError:
            raise StickmanAudioError("voz.mp3 appeared during Fish generation; both the input and paid result were preserved") from None
        if staged_alignment.is_file():
            try:
                os.link(staged_alignment, alignment)
            except FileExistsError:
                # Provider evidence that appeared independently is never replaced.
                if _hash(staged_alignment) != _hash(alignment):
                    raise StickmanAudioError("Provider alignment already exists and differs; audio was preserved") from None
        request = _read_record(request_path)
        request["audio_sha256"] = _hash(audio)
        write_json_atomic(request_path, request)
    if request and voice:
        identity = {"reference_id": voice.get("reference_id"), "model": voice.get("model") or settings.fish_model,
                    "speed": voice.get("speed", 1.0)}
        if request.get("voice") != identity:
            raise StickmanAudioError("Fish voice settings changed after a request; existing audio was preserved")
    info = probe_media(audio, settings.ffprobe_binary)
    if not info.audio_codec or not math.isfinite(info.duration) or info.duration <= 0:
        raise StickmanAudioError("voz.mp3 must contain measurable, finite narration audio")
    _, audio_duration = stream_durations(audio, settings.ffprobe_binary)
    duration = audio_duration if audio_duration is not None else info.duration
    if not math.isfinite(duration) or duration <= 0:
        raise StickmanAudioError("voz.mp3 has invalid audio stream duration")
    audio_sha = _hash(audio)
    if request and request.get("audio_sha256") and request["audio_sha256"] != audio_sha:
        raise StickmanAudioError("Generated Fish audio changed; preserve the original paid result")
    if receipt and receipt.get("alignment_sha256") and (
            not alignment.is_file() or _hash(alignment) != receipt["alignment_sha256"]):
        raise StickmanAudioError("Provider alignment changed after validation; use a new episode revision")
    alignment_sha = _hash(alignment) if alignment.is_file() else None
    segments = _provider_segments(alignment, script, duration) if alignment_sha else None
    method = receipt["alignment_method"] if receipt else "imported_srt_human_sync_review_required"
    if not srt.is_file():
        cues = _provider_cues(alignment, script, duration)
        _new_text(srt, format_srt(cues))
        method = "fish_provider_timestamps_full_transcript"
    srt_sha = _hash(srt)
    cues = read_srt(srt)
    _validate_cues(cues, duration=duration)
    if [token for cue in cues for token in _tokens(cue["text"])] != _tokens(script):
        raise StickmanAudioError("SRT transcript does not match guion_final.txt; no script rewriting is permitted")
    if _hash(audio) != audio_sha or _hash(script_path) != script_sha or _hash(srt) != srt_sha:
        raise StickmanAudioError("Narration inputs changed during validation; no receipt was accepted")
    result = {"version": 1, "audio_path": str(audio), "srt_path": str(srt), "duration": duration,
              "cues": cues, "script_sha256": script_sha, "audio_sha256": audio_sha,
              "srt_sha256": srt_sha, "alignment_method": method,
              "acoustic_sync_verified": False, "human_sync_review_required": True,
              "source": ("fish" if request and request.get("audio_sha256") == audio_sha
                         else "imported_after_unconfirmed_fish_request" if request else "imported")}
    if alignment_sha:
        if _hash(alignment) != alignment_sha:
            raise StickmanAudioError("Provider alignment changed during validation; no receipt was accepted")
        result["alignment_sha256"] = alignment_sha
        # Fish also returns whole segments under 'words'. Never invent word times.
        if all(len(_tokens(segment["word"])) == 1 for segment in segments):
            result["words"] = segments
    if receipt is None:
        write_json_atomic(receipt_path, result)
    return result


def prepare_mix(episode: Path, narration: dict, *, root: Path, settings,
                music: dict | None = None, sfx_events: list[dict] | None = None) -> dict:
    """Use Kitok's licensed AudioLibrary exclusively; never download music here."""
    music = music or {"mode": "off"}
    mode = music.get("mode", "off")
    if mode not in {"off", "auto", "manual"}:
        raise StickmanAudioError("Music mode must be off, auto or manual")
    if mode == "manual" and (not isinstance(music.get("track_id"), str) or not music["track_id"]):
        raise StickmanAudioError("Manual music requires an explicit cached track_id")
    source = Path(narration["audio_path"])
    source_sha = _hash(source)
    if source_sha != narration["audio_sha256"]:
        raise StickmanAudioError("Narration changed before audio mixing")
    if mode == "off":
        if sfx_events:
            raise StickmanAudioError("Sound effects require an enabled AudioLibrary music mix")
        return {"audio_path": str(source), "duration": narration["duration"], "audio_sha256": source_sha,
                "mode": "off", "credits": [], "audio_is_final_mix": False}
    state = _state(Path(episode))
    request = {"version": 1, "narration_sha256": source_sha, "duration": narration["duration"],
               "music": music, "sfx_events": sfx_events or []}
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()
    output = state / f"mix-{fingerprint[:24]}.m4a"
    receipt_path = output.with_suffix(output.suffix + ".json")
    existing = _read_record(receipt_path)
    if output.is_symlink():
        raise StickmanAudioError("Audio mix output cannot be a symlink")
    if output.exists() or existing:
        if (not output.is_file() or not existing or existing.get("output_sha256") != _hash(output)
                or existing.get("narration_sha256") != source_sha):
            raise StickmanAudioError("Existing audio mix is incomplete or changed; preserve and review it")
        return {"audio_path": str(output), "audio_sha256": existing["output_sha256"],
                "duration": existing["duration"], "mode": mode,
                "credits": existing["selection"]["credits"], "receipt": existing, "audio_is_final_mix": True}
    library = AudioLibrary(Path(root) / "presets" / "music_sources.json",
                           (settings.data_root or Path(root)) / "cache" / "audio-library",
                           ffmpeg=settings.ffmpeg_binary, ffprobe=settings.ffprobe_binary)
    job_id = "stickman-" + fingerprint[:40]
    try:
        if mode == "manual":
            selection = library.select_manual(job_id, music.get("track_id", ""),
                                              channel=music.get("channel", "documentary"))
        else:
            selection = library.select(job_id, channel=music.get("channel", "documentary"),
                                       mood=music.get("mood", "investigation"), count=music.get("count", 2))
        receipt = library.mix(job_id, source, output, duration=narration["duration"],
                              crossfade=music.get("crossfade", 1.5), sfx_events=sfx_events,
                              transition_at=music.get("transition_at"))
    finally:
        library.close()
    return {"audio_path": str(output), "duration": receipt["duration"],
            "audio_sha256": receipt["output_sha256"], "mode": mode,
            "credits": selection["credits"], "receipt": receipt, "audio_is_final_mix": True}
