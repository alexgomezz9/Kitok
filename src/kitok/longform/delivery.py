"""Assemble a local YouTube Studio handoff from a validated Native render."""
from __future__ import annotations

from dataclasses import dataclass
from errno import EXDEV
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import warnings

from PIL import Image

from ..editing.manifest import script_hash
from ..editing.storyboard import file_hash
from ..editing.visual_cues import script_words, visual_sources
from ..media.ffprobe import probe_media
from ..models import ID_RE
from ..native_recovery import regular
from ..youtube_stickman_es.audio import aligned_srt, format_srt, read_srt
from ..youtube_stickman_es.delivery import publication_metadata
from ..youtube_stickman_es.files import local_file


@dataclass(frozen=True)
class Publication:
    episode: Path
    title: str
    description: str
    tags: str
    settings: str
    thumbnail: bytes

    @property
    def destination(self) -> Path:
        return self.episode / 'entrega'


def prepare_publication(config: Path, root: Path, script: str) -> Publication:
    config = config if config.is_absolute() else root / config
    relative = regular(config, root).relative_to(root)
    if (len(relative.parts) != 5 or relative.parts[:2] != ('content', 'longform')
            or any(not ID_RE.fullmatch(part) for part in relative.parts[2:4])):
        raise ValueError('Delivery requires content/longform/<channel>/<episode>/<config.json>')
    episode = config.parent
    metadata = publication_metadata(episode)
    if not metadata:
        raise ValueError('Delivery requires editorial/publicacion_youtube.json')
    title = metadata['title'].strip()
    description = metadata['description'].strip()
    if any(char in title + description for char in '<>'):
        raise ValueError('YouTube title and description cannot contain angle brackets')
    _check_description(description)
    tags = [tag.strip() for tag in metadata['tags']]
    tag_length = len(','.join(tags)) + sum(2 for tag in tags if ' ' in tag)
    if tag_length > 500 or any(any(char in tag for char in ',\n\r') for tag in tags):
        raise ValueError('YouTube tags must fit 500 characters including commas and multiword quotes')
    settings = metadata.get('settings')
    if not isinstance(settings, dict):
        raise ValueError('Set Studio language, category, made_for_kids and altered_content')
    language = settings.get('language')
    category = settings.get('category')
    if any(not isinstance(value, str) or not value.strip() or not value.strip().isprintable()
           for value in (language, category)):
        raise ValueError('Set Studio language and category as single-line text')
    audience = settings.get('made_for_kids')
    altered = settings.get('altered_content')
    if not isinstance(audience, bool) or not isinstance(altered, bool):
        raise ValueError('Set Studio made_for_kids and altered_content as true or false')
    notes = settings.get('notes', '')
    if not isinstance(notes, str):
        raise ValueError('Studio settings notes must be text')
    choices = (
        f'Idioma del vídeo, título y descripción: {language.strip()}.\n'
        f'Categoría: {category.strip()}.\n'
        f'Creado para niños: {"sí" if audience else "no"}.\n'
        f'Contenido alterado o sintético: {"sí" if altered else "no"}.\n'
        'Visibilidad inicial: privado. Programa en Studio con la fecha y zona horaria elegidas.\n'
        'Sube miniatura.png y voz.srt con tiempos. Revisa las comprobaciones de Studio.\n'
    )
    if notes.strip():
        choices += '\n' + notes.strip() + '\n'
    image_path = local_file(episode, 'miniaturas/miniatura_final.png')
    if image_path.stat().st_size > 50_000_000:
        raise ValueError('Desktop YouTube thumbnail must fit 50 MB')
    thumbnail = image_path.read_bytes()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(thumbnail), formats=['PNG']) as image:
                if image.height < 640 or 9 * image.width != 16 * image.height:
                    raise ValueError('Thumbnail must be 16:9 with at least 640 pixels of height')
                image.verify()
            with Image.open(BytesIO(thumbnail), formats=['PNG']) as image:
                image.load()
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('miniatura_final.png must be a readable PNG') from exc
    _supplied_cues(episode, script)
    return Publication(episode, title, description, ', '.join(tags), choices, thumbnail)


def _check_description(text: str) -> None:
    if len(text.encode('utf-8')) > 5000:
        raise ValueError('YouTube description must fit 5,000 UTF-8 bytes including credits')


def _description(publication: Publication, render: dict) -> str:
    description = publication.description
    music = render.get('music_selection') or {}
    credits = music.get('credits') or []
    if credits:
        required = [*credits, music['changes_notice']]
        missing = list(dict.fromkeys(credit for credit in required if credit not in description))
        if missing:
            description += '\n\n' + '\n\n'.join(missing)
    _check_description(description)
    return description


def _supplied_cues(episode: Path, script: str) -> list[dict] | None:
    supplied = local_file(episode, 'voz.srt', exists=False)
    if not supplied.exists():
        return None
    cues = read_srt(supplied)
    if script_words(' '.join(cue['text'] for cue in cues)) != script_words(script):
        raise ValueError('voz.srt transcript must match the narration script')
    return cues


def _subtitles(publication: Publication, output: Path, root: Path, definition,
               duration: float, render: dict, edit: dict) -> str:
    script = definition.item.script
    cues = _supplied_cues(publication.episode, script)
    if cues is not None:
        if cues[-1]['end'] > duration + .001:
            raise ValueError('voz.srt exceeds the final narration or video duration')
        return format_srt(cues)
    source_id = definition.source_narration_id or output.stem
    if not ID_RE.fullmatch(source_id):
        raise ValueError('Invalid narration source ID')
    source = output.parent / '.native-work' / source_id / 'narration.mp3'
    try:
        narration = regular(source, root)
        alignment = regular(source.with_suffix('.alignment.json'), root)
        if file_hash(narration) != edit.get('audio_sha256'):
            raise ValueError('The cached narration does not match the render')
        expected = render.get('narration_alignment_sha256')
        if expected is not None and file_hash(alignment) != expected:
            raise ValueError('Fish alignment changed after rendering')
        return aligned_srt(alignment, script, duration)
    except ValueError as exc:
        raise ValueError(
            f'{exc}. Supply the aligned voz.srt in the episode and rerun --deliver-only.'
        ) from exc


def deliver(publication: Publication, output: Path, root: Path, definition, *, ffprobe: str) -> Path:
    """Validate, stage and atomically expose the package under the caller's locks."""
    output = regular(output, root)
    native = regular(output.with_suffix('.native.json'), root)
    edit_path = regular(output.with_suffix('.edit.json'), root)
    regular(output.with_suffix('.credits.md'), root)
    render = _read_receipt(native)
    edit = _read_receipt(edit_path)
    if (render.get('renderer') != 'native' or render.get('content_id') != definition.item.id
            or edit.get('script_sha256') != script_hash(definition.item.script)):
        raise ValueError('The saved Native render does not match this episode ID and script')
    if render.get('definition_sha256') and render['definition_sha256'] != definition.fingerprint():
        raise ValueError('The Native render was produced with different montage or narration settings')
    if definition.visual_plan is not None:
        sources = visual_sources(definition.visual_plan, root, definition.visual_root)
        if sources != render.get('visual_sources'):
            raise ValueError('The case media changed after rendering')
    expected = render.get('output_sha256')
    if not expected:
        # Motion renders made before Native recorded its own digest already have a receipt.
        editorial = regular(output.with_suffix('.editorial.json'), root)
        expected = _read_receipt(editorial).get('output_sha256')
    if not expected or file_hash(output) != expected:
        raise ValueError('The final MP4 does not match its validated render receipt')
    info = probe_media(output, ffprobe)
    if (info.video_codec != 'h264' or info.audio_codec != 'aac' or not info.width
            or not info.height or 9 * info.width != 16 * info.height
            or not math.isfinite(info.duration)):
        raise ValueError('Delivery requires a valid horizontal H.264/AAC MP4')
    narration_duration = render.get('narration_duration')
    if (type(narration_duration) not in (float, int) or not math.isfinite(narration_duration)
            or narration_duration <= 0):
        raise ValueError('The Native render has no valid narration duration')
    subtitles = _subtitles(publication, output, root, definition,
                           min(narration_duration, info.duration), render, edit)
    texts = {
        'titulo.txt': publication.title,
        'descripcion.txt': _description(publication, render),
        'etiquetas.txt': publication.tags,
        'ajustes_youtube.txt': publication.settings.rstrip(),
        'voz.srt': subtitles.rstrip(),
    }
    files = {name: (content + '\n').encode('utf-8') for name, content in texts.items()}
    files['miniatura.png'] = publication.thumbnail
    return _publish(publication.destination, output, files, expected)


def _read_receipt(path: Path) -> dict:
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(receipt, dict):
        raise ValueError(f'Invalid render receipt: {path.name}')
    return receipt


def _publish(destination: Path, output: Path, files: dict[str, bytes], expected: str) -> Path:
    if destination.is_symlink():
        raise ValueError('Delivery folder cannot be a symlink')
    if destination.exists():
        if destination.is_dir() and _same_delivery(destination, files, output, expected):
            return destination
        raise ValueError('Existing entrega was preserved; use another episode or revision')
    with TemporaryDirectory(prefix='.entrega-', dir=destination.parent) as folder:
        staged = Path(folder) / 'package'
        staged.mkdir()
        for name, content in files.items():
            (staged / name).write_bytes(content)
        video = staged / 'video_final.mp4'
        try:
            os.link(output, video, follow_symlinks=False)
        except OSError as exc:
            if exc.errno != EXDEV:
                raise
            shutil.copyfile(output, video)
            if file_hash(video) != expected:
                raise ValueError('The copied MP4 differs from the validated render')
        staged.rename(destination)
    return destination


def _same_delivery(destination: Path, files: dict[str, bytes], output: Path, expected: str) -> bool:
    video = destination / 'video_final.mp4'
    entries = {path.name for path in destination.iterdir()}
    if entries != set(files) | {video.name} or video.is_symlink() or not video.is_file():
        return False
    for name, content in files.items():
        path = destination / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            return False
    return video.samefile(output) or file_hash(video) == expected
