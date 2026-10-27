"""Episode housekeeping without providers or changes to production input paths."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from .delivery import _cache_locks, _source_documents, sha256
from .files import episode_lock, episode_path, local_file, replace_state

DIRECTORIES = ('entrega', 'imagenes', 'referencias', 'miniaturas',
               'planificacion_visual', 'editorial')
MARKER = '<!-- Kitok: índice generado; entradas originales conservadas -->'


def _files(folder):
    paths = sorted(folder.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('Workspace contains symlinks; housekeeping blocked')
    return [p for p in paths if p.is_file()]


def _referenced(root, episode):
    protected = set()
    def collect(value):
        if isinstance(value, str):
            for base in (root, episode):
                candidate = (base / value).resolve()
                if candidate.is_relative_to(episode):
                    protected.add(candidate)
        elif isinstance(value, dict):
            for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    for source in _source_documents(episode):
        collect(json.loads(source.read_text()))
    return protected


def _cache_candidates(root, episode, folders):
    protected = _referenced(root, episode)
    candidates = []
    for folder in folders:
        for p in folder.iterdir():
            if re.fullmatch(r's\d+_\d+(?:\.handle)?\.(?:mp4|json|ass)|s\d+_\d+\.source\.png|assembled\.mp4', p.name):
                candidates.append(p)
    frames = local_file(episode, '.qa.contact-frames', exists=False)
    if frames.is_dir():
        candidates.extend(frames.glob('[0-9][0-9][0-9].jpg'))
    return [p for p in candidates if p.resolve() not in protected]


def _atlas_candidates(episode):
    """Drop assembly sheets only when every scene has a recorded final PNG hash."""
    folder = episode / 'planificacion_visual'
    manifests = {p.parent.name: json.loads(p.read_text())
                 for p in folder.glob('lotes_imagenes/*/manifest.json')}
    def resolved(scene):
        if replacement := scene.get('cleanup_superseded_by'):
            matches = [s for s in manifests.get(replacement, {}).get('scenes', [])
                       if s['id'] == scene['id'] and s['state'] == 'accepted']
            if len(matches) != 1: return False
            scene = matches[0]
        elif scene['state'] != 'accepted':
            return False
        path = local_file(episode, scene['image_file'])
        if sha256(path) != scene.get('delivery_sha256', scene['sha256']): return False
        from .images import ImageBatch
        ImageBatch.inspect(path, require_delivery_size=False)
        return True
    result = []
    for manifest in folder.glob('lotes_imagenes/*/manifest.json'):
        candidates = [p for pattern in ('atlas.png', 'contacto_recortes.png', 'crops/*.png')
                      for p in manifest.parent.glob(pattern)]
        if not candidates:
            continue
        data = json.loads(manifest.read_text())
        if not data['scenes'] or not all(resolved(s) for s in data['scenes']):
            continue
        result.extend(candidates)
    # Earlier episodes have a single verification receipt instead of per-batch manifests.
    receipt = folder / 'laminas_finales/verificacion_imagenes.json'
    if receipt.is_file() and list(receipt.parent.glob('*.png')):
        records = json.loads(receipt.read_text()).get('records', [])
        if records and all(sha256(local_file(episode, r['file'])) == r['sha256'] for r in records):
            from .images import ImageBatch
            for r in records:
                ImageBatch.inspect(local_file(episode, r['file']), require_delivery_size=False)
            result.extend(receipt.parent.glob('*.png'))
    return sorted(set(result))


def index_episode(episode):
    """Common visible folders; legacy input filenames remain valid."""
    for name in DIRECTORIES:
        local_file(episode, name, exists=False).mkdir(exist_ok=True)
    path = local_file(episode, 'LEEME.md', exists=False)
    if path.exists() and MARKER not in path.read_text():
        raise ValueError('Preserve the operator LEEME.md before generating an index')
    roots = [p for p in sorted(episode.iterdir()) if p.is_file() and p != path and not p.name.startswith('.')]
    lines = [MARKER, f'# {episode.name}', '']
    state_path = local_file(episode, 'editorial/estado.json', exists=False)
    if state_path.is_file():
        state = json.loads(state_path.read_text())
        if state.get('phase') == 'standby':
            lines += ['**EN PAUSA — no continuar este episodio ahora.**', '']
        if state.get('next_action'):
            lines += [state['next_action'], '']
    lines += ['Entradas actuales (las rutas se conservan para no romper Kitok):', '']
    lines.extend(f'- [{p.name}]({p.name})' for p in roots)
    lines += ['', 'Carpetas comunes:', '',
              '- `entrega/`: vídeos conservados y archivos para revisión; su existencia no acredita aprobación.',
              '- `imagenes/`: PNG definitivos; `referencias/`: anclas y fuentes.',
              '- `planificacion_visual/`: plan, prompts y manifiestos; sin láminas ya resueltas.',
              '- `miniaturas/`: propuestas y selección; `editorial/`: investigación y estado.',
              '- `.stickman/`: estado interno de Kitok. No borrar para forzar otra voz.',
              '', 'Pruebas: `local/pruebas/<episodio>/`. Revisiones retiradas: '
              '`local/archivo_episodios/<episodio>/` con restauracion.json dentro de cada ZIP.',
              'Para recuperar una revisión: extraer los miembros archivados en la ruta `revision` '
              'y copiar cada ruta de `retained` a su ruta original; comprobar todos los SHA256.', '']
    lines += [f'- Vídeo conservado: [entrega/{p.name}](entrega/{p.name})'
              for p in sorted((episode / 'entrega').glob('*.mp4'))]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def organize(root: Path, episode: Path, *, apply=False, archive_revisions=False):
    """Explicit maintenance. Dry run first; closed revisions are archived before removal."""
    root = root.resolve()
    episode = episode_path(root, episode)
    with ExitStack() as locks:
        locks.enter_context(episode_lock(episode))
        revisions = local_file(episode, 'revisiones', exists=False)
        children = sorted(p for p in revisions.iterdir()) if revisions.is_dir() and archive_revisions else []
        if any(not p.is_dir() or p.is_symlink() for p in children):
            raise ValueError('Unexpected revision path')
        scopes = [episode] + children
        cache = []
        for scope in scopes:
            _files(scope)  # Reject links before any mutations or archive traversal.
            if scope != episode:
                locks.enter_context(episode_lock(scope))
            folders = locks.enter_context(_cache_locks(scope))
            cache.extend(_cache_candidates(root, scope, folders))
        protected = _referenced(root, episode)
        if any(path.is_relative_to(revision) for revision in children for path in protected):
            raise ValueError('A current input references a historical revision; preserve its active paths')
        for scope in children:
            protected.update(_referenced(root, scope))
        atlas = _atlas_candidates(episode)
        removable = sorted(p for p in set(cache + atlas) if p.resolve() not in protected)
        report = {'mode': 'applied' if apply else 'dry_run', 'episode': str(episode.relative_to(root)),
                  'removed': [{'path': str(p.relative_to(episode)), 'sha256': sha256(p),
                               'bytes': p.stat().st_size} for p in removable],
                  'archive_revisions': [p.name for p in children], 'archives': [],
                  'provider_calls': 0}
        if not apply:
            return report
        # Preflight destination boundaries before deleting even regenerable files.
        index_path = local_file(episode, 'LEEME.md', exists=False)
        if index_path.exists() and MARKER not in index_path.read_text():
            raise ValueError('Preserve the operator LEEME.md first')
        for name in DIRECTORIES:
            path = local_file(episode, name, exists=False)
            if path.exists() and not path.is_dir():
                raise ValueError('Expected directory: ' + name)
        archive_dir = local_file(root, f'local/archivo_episodios/{episode.name}', exists=False)
        archive_dir.mkdir(parents=True, exist_ok=True)
        # Deduplicate against originals outside the revisions, never against a cache being removed.
        canonical = {sha256(p): p for p in _files(episode)
                     if p not in removable and not p.is_relative_to(revisions)} if children else {}
        for revision in children:
            archive = local_file(root, str((archive_dir / (revision.name + '.zip')).relative_to(root)), exists=False)
            if archive.exists():
                raise ValueError('Archive already exists; preserve both paths and inspect interrupted maintenance')
            retained, members = {}, []
            for p in _files(revision):
                if p in removable:
                    continue
                sha = sha256(p)
                source = canonical.get(sha)
                if p.suffix == '.mp4' and source is None:
                    target = local_file(episode, f'entrega/{revision.name}__{p.name}', exists=False)
                    target.parent.mkdir(exist_ok=True)
                    if target.exists():
                        if sha256(target) != sha: raise ValueError('Delivery collision')
                    else:
                        os.link(p, target)
                    source = target
                    canonical[sha] = target
                if source:
                    retained[str(p.relative_to(revision))] = {'path': str(source.relative_to(root)), 'sha256': sha}
                else:
                    members.append((p, sha))
            fd, temporary = tempfile.mkstemp(prefix='.archive-', dir=archive_dir)
            os.close(fd)
            try:
                with ZipFile(temporary, 'w', ZIP_DEFLATED) as z:
                    for p, _ in members: z.write(p, str(p.relative_to(revision)))
                    z.writestr('restauracion.json', json.dumps({
                        'revision': str(revision.relative_to(root)), 'retained': retained,
                        'archived': {str(p.relative_to(revision)): sha for p, sha in members},
                        'removed_cache': [str(p.relative_to(revision)) for p in removable if p.is_relative_to(revision)],
                        'note': 'Historical revision; restore inputs before reusing. Not editorial approval.'}, ensure_ascii=False, indent=2))
                import hashlib
                with ZipFile(temporary) as z:
                    for p, sha in members:
                        if hashlib.sha256(z.read(str(p.relative_to(revision)))).hexdigest() != sha:
                            raise ValueError('Archive verification failed')
                for rel, item in retained.items():
                    if sha256(root / item['path']) != item['sha256']:
                        raise ValueError('Retained input changed')
                os.link(temporary, archive)
                # Complete archive and retained copies exist before removing any source.
                shutil.rmtree(revision)
                report['archives'].append(str(archive.relative_to(root)))
            finally:
                Path(temporary).unlink(missing_ok=True)
        for p in removable:
            if p.exists(): p.unlink()
        # Keep a compact provenance receipt, including hashes of discarded sheets.
        if report['removed'] or report['archives']:
            history = local_file(episode, '.stickman/workspace-history.json', exists=False)
            previous = json.loads(history.read_text()) if history.exists() else []
            replace_state(history, previous + [report])
        index_episode(episode)
        return report
