"""Check current documentation, public examples and the small tracked root layout.

Offline structural checks only: editorial truth still needs code/runtime review.
Historical documents are reachable through a clearly labelled archive index.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
ROOT_FILES = {'.env.example', '.gitignore', 'AGENTS.md', 'GUIA.md', 'PROJECT_STATUS.md',
              'README.md', 'Makefile', 'main.py', 'longform.py', 'pyproject.toml', 'requirements.txt'}
ARCHIVE_INDEX = 'docs/archive/README.md'
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^)\n]+)\)')


def inspect_documents(root: Path, paths: list[str]) -> list[str]:
    root = root.resolve()
    errors = []
    for name in sorted(set(paths)):
        path = root / name
        if not path.is_file():
            continue
        if '/' not in name and name not in ROOT_FILES:
            errors.append(f'{name}: auxiliary files belong in docs/, examples/ or scripts/')
        if not name.endswith('.md') or (name.startswith('docs/archive/') and name != ARCHIVE_INDEX):
            continue
        for match in LINK.finditer(path.read_text(encoding='utf-8')):
            value = match.group(1).strip()
            # Markdown supports angle brackets and an optional quoted link title.
            value = value[1:value.index('>')] if value.startswith('<') and '>' in value else value.split(' "', 1)[0]
            parsed = urlsplit(value)
            if parsed.scheme in {'http', 'https', 'mailto'} or not parsed.path:
                continue
            line = path.read_text(encoding='utf-8').count('\n', 0, match.start()) + 1
            target = (path.parent / unquote(parsed.path)).resolve()
            if parsed.scheme or Path(parsed.path).is_absolute() or not target.is_relative_to(root):
                errors.append(f'{name}:{line}: nonportable local link {value}')
            elif not target.exists():
                errors.append(f'{name}:{line}: missing local link {value}')
            elif (name != ARCHIVE_INDEX and target.is_relative_to(root / 'docs/archive')
                  and target != root / ARCHIVE_INDEX):
                errors.append(f'{name}:{line}: link historical material through {ARCHIVE_INDEX}')
    return errors


def inspect_examples(root: Path) -> list[str]:
    from kitok.editing.director import DirectorBrief
    from kitok.editing.storyboard import EditorialPlan
    from kitok.longform.cli import load_longform_config
    from kitok.models import ContentItem
    from kitok.profiles import VOICES
    errors = []
    for folder, model in [('examples/editorial', None), ('examples/shorts', ContentItem), ('examples/longform', None)]:
        for path in sorted((root / folder).glob('*.json')):
            try:
                data = json.loads(path.read_text())
                if folder == 'examples/editorial':
                    (DirectorBrief if 'beats' in data else EditorialPlan).model_validate(data)
                elif model:
                    if not isinstance(data, list) or not data:
                        raise ValueError('Short examples require a nonempty list')
                    for row in data:
                        item = model.model_validate(row)
                        if item.content_format == 'explainer' and VOICES[item.voice_profile].provider != 'fish':
                            raise ValueError('New public examples require an explicit Fish voice')
                        if item.schedule_enabled:
                            raise ValueError('Public examples must start unscheduled')
                else:
                    load_longform_config(path, project_root=root)
            except (ValueError, OSError, TypeError, KeyError) as error:
                errors.append(f'{path.relative_to(root)}: invalid public template: {error}')
    from kitok.editing.visual_cues import VisualPlan
    for path in sorted((root / 'examples/visuals').glob('*.json')):
        try:
            VisualPlan.model_validate_json(path.read_text())
        except (ValueError, OSError, TypeError) as error:
            errors.append(f'{path.relative_to(root)}: invalid visual template: {error}')
    from kitok.youtube_stickman_es.models import Config as StickmanConfig
    for path in sorted((root/'examples/youtube_stickman_es').glob('*.json')):
        try:
            StickmanConfig.model_validate_json(path.read_text())
        except (ValueError,OSError) as error:
            errors.append(f'{path.relative_to(root)}: invalid stickman configuration: {error}')
    return errors


def main():
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=ROOT, capture_output=True, check=True)
    paths = [name for name in result.stdout.decode().split('\0') if name]
    errors = inspect_documents(ROOT, paths) + inspect_examples(ROOT)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Current documentation links, root layout and public example contracts passed (offline).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
