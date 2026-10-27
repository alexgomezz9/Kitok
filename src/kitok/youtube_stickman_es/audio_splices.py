"""Execute reviewed sample-clock cuts/replacements without synthesis or acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from .audio_autoclean import _hash, _safe_path, _output_lock
from .files import digest, write

RATE = 48000
VERSION = 1


def _decode(source: Path, output: Path, ffmpeg: str, *, channels: int | None = None):
    args = [ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', str(source), '-vn',
            '-map', '0:a:0', '-map_metadata', '-1', '-ar', str(RATE), '-c:a', 'pcm_s16le']
    if channels is not None:
        args += ['-ac', str(channels)]
    subprocess.run([*args, str(output)], check=True, capture_output=True, timeout=180)
    with wave.open(str(output)) as stream:
        return stream.getnframes(), stream.getnchannels()


def apply_splices(source: Path, destination: Path, operations: list[dict], *,
                  ffmpeg: str = 'ffmpeg', source_audio_sha256: str | None = None) -> dict:
    """Apply explicit non-overlapping cuts/replacements to one new PCM output.

    `start_sample`/`end_sample` use the decoded source at48kHz. Replacements need
    an exact file hash and a review reason; their text/ASR acceptance is external.
    Output remains pending independent recognition. Existing edits are immutable.
    """
    source, destination = Path(source).absolute(), Path(destination).absolute()
    _safe_path(source)
    _safe_path(destination)
    if not source.is_file() or source.stat().st_size > 1024**3:
        raise ValueError('A bounded original narration file is required')
    source_sha = _hash(source)
    if source_audio_sha256 is not None and source_sha != source_audio_sha256:
        raise ValueError('Original narration differs from the reviewed source hash')
    if not isinstance(operations, list) or not operations:
        raise ValueError('Explicit cut/replacement operations are required')
    normalized, clips, previous = [], {}, 0
    for item in operations:
        if not isinstance(item, dict):
            raise ValueError('Each audio splice must be an object')
        start, end, path = item.get('start_sample'), item.get('end_sample'), item.get('replacement_path')
        if (type(start) is not int or type(end) is not int or not previous <= start < end
                or not isinstance(item.get('reason'), str) or not item['reason'].strip()):
            raise ValueError('Splices need ordered non-overlapping sample ranges and a review reason')
        previous = end
        record = {'start_sample': start, 'end_sample': end, 'reason': item['reason'],
                  'replacement_path': None, 'replacement_sha256': None,
                  'evidence': item.get('evidence')}
        if path is not None:
            if not isinstance(path, (str, Path)):
                raise ValueError('Replacement path must identify a local audio file')
            clip = Path(path).absolute()
            _safe_path(clip)
            if (not clip.is_file() or clip == source or clip.stat().st_size > 32*1024**2
                    or item.get('replacement_sha256') != _hash(clip)):
                raise ValueError('Replacement audio differs from its reviewed hash or bounds')
            record.update(replacement_path=str(clip), replacement_sha256=item['replacement_sha256'])
            clips[str(clip)] = item['replacement_sha256']
        elif item.get('replacement_sha256') is not None:
            raise ValueError('A cut cannot declare an unused replacement hash')
        normalized.append(record)
    identity = {'version': VERSION, 'source_audio_sha256': source_sha,
                'sample_rate': RATE, 'operations': normalized}
    key = digest(identity)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _output_lock(destination.parent / ('.' + destination.name + '.lock')):
        if destination.exists():
            for name in ('audio.wav', 'manifest.json', 'receipt.json'):
                _safe_path(destination/name)
                if not (destination/name).is_file():
                    raise ValueError('Incomplete audio splice preserved; choose another destination')
            receipt = json.loads((destination/'receipt.json').read_text())
            payload = {k: v for k, v in receipt.items() if k != 'receipt_sha256'}
            if (json.loads((destination/'manifest.json').read_text()) != identity
                    or receipt.get('manifest_sha256') != key or receipt.get('receipt_sha256') != digest(payload)
                    or receipt.get('output_audio_sha256') != _hash(destination/'audio.wav')
                    or receipt.get('status') != 'edited_requires_second_pass'
                    or receipt.get('audio_path') != str(destination/'audio.wav')):
                raise ValueError('Existing audio splice differs; preserve it for review')
            return receipt
        work = Path(tempfile.mkdtemp(prefix='.audio-splice-', dir=destination.parent))
        try:
            pcm = work/'source.wav'
            total, channels = _decode(source, pcm, ffmpeg)
            if not 0 < total <= RATE*3600 or channels not in (1, 2) or normalized[-1]['end_sample'] > total:
                raise ValueError('Splices exceed the decoded source sample clock or narration bounds')
            decoded, inputs = {}, [pcm]
            for index, path in enumerate(clips):
                output = work/f'clip-{index}.wav'
                frames, _ = _decode(Path(path), output, ffmpeg, channels=channels)
                if not 0 < frames <= RATE*120:
                    raise ValueError('Replacement audio must contain at most120seconds')
                decoded[path] = (len(inputs), frames)
                inputs.append(output)
            pieces, mapping, cursor, position = [], [], 0, 0
            def retain(a, b):
                nonlocal position
                if b > a:
                    pieces.append((0, a, b))
                    mapping.append({'kind': 'source', 'input_samples': [a, b],
                                    'output_samples': [position, position+b-a]})
                    position += b-a
            for operation in normalized:
                a, b = operation['start_sample'], operation['end_sample']
                retain(cursor, a)
                path = operation['replacement_path']
                end_position = position
                if path is not None:
                    index, frames = decoded[path]
                    pieces.append((index, 0, frames))
                    end_position += frames
                mapping.append({'kind': 'replacement' if path else 'cut', 'input_samples': [a, b],
                                'output_samples': [position, end_position],
                                'replacement_sha256': operation['replacement_sha256']})
                position, cursor = end_position, b
            retain(cursor, total)
            if not pieces:
                raise ValueError('Audio splices cannot remove the entire narration')
            graph = []
            for index, (input_index, a, b) in enumerate(pieces):
                trim = f'atrim=start_sample={a}:end_sample={b},asetpts=PTS-STARTPTS'
                fade = min(.005, (b-a)/RATE/2)
                if index:
                    trim += f',afade=t=in:d={fade:.9f}'
                if index+1 < len(pieces):
                    trim += f',afade=t=out:st={(b-a)/RATE-fade:.9f}:d={fade:.9f}'
                graph.append(f'[{input_index}:a]{trim}[a{index}]')
            graph.append(''.join(f'[a{i}]' for i in range(len(pieces)))+f'concat=n={len(pieces)}:v=0:a=1[out]')
            command = [ffmpeg, '-nostdin', '-v', 'error', '-n']
            for path in inputs:
                command += ['-i', str(path)]
            output = work/'audio.wav'
            subprocess.run([*command, '-filter_complex', ';'.join(graph), '-map', '[out]',
                            '-c:a', 'pcm_s16le', str(output)], check=True, capture_output=True, timeout=180)
            with wave.open(str(output)) as stream:
                if (stream.getnframes(), stream.getframerate(), stream.getnchannels()) != (position, RATE, channels):
                    raise ValueError('Spliced PCM does not match the exact output sample clock')
            if _hash(source) != source_sha or any(_hash(Path(p)) != sha for p, sha in clips.items()):
                raise ValueError('Source or replacement changed during splicing; nothing was promoted')
            receipt = {'version': VERSION, 'status': 'edited_requires_second_pass',
                       'manifest_sha256': key, 'source_audio_sha256': source_sha,
                       'output_audio_sha256': _hash(output), 'audio_path': str(destination/'audio.wav'),
                       'sample_rate': RATE, 'source_frames': total, 'output_frames': position,
                       'mapping': mapping, 'maximum_seam_fade_seconds': .005,
                       'requires_second_pass': True, 'acoustic_sync_verified': False}
            receipt['receipt_sha256'] = digest(receipt)
            for path in inputs:
                path.unlink()
            write(work/'manifest.json', identity)
            write(work/'receipt.json', receipt)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('Splice destination appeared; other work was preserved')
            work.rename(destination)
            return receipt
        finally:
            if work.exists():
                shutil.rmtree(work)
