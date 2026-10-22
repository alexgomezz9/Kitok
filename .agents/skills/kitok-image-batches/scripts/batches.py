#!/usr/bin/env python3
"""Local prompt blocks and reviewed PNG crops; no provider, voice or renderer."""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile

from PIL import Image, ImageOps


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(root, value):
    p = Path(value)
    if p.is_absolute() or not p.parts or '..' in p.parts:
        raise ValueError('Expected relative path inside episode')
    out = root
    for part in p.parts:
        out /= part
        if out.is_symlink():
            raise ValueError('Symlink resource refused')
    if not out.resolve().is_relative_to(root):
        raise ValueError('Resource escaped episode')
    return out


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.batch-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def exclusive(path, data):
    """Publish complete bytes without clobbering an existing output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.batch-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_json(path, obj):
    atomic(path, (json.dumps(obj, ensure_ascii=False, indent=2)+'\n').encode())


def plan_data(ep, value):
    path = local(ep, value)
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    scenes = data['scenes']
    ids = [s['id'] for s in scenes]
    if not scenes or len(ids) != len(set(ids)):
        raise ValueError('Scenes must have unique IDs')
    outputs = []
    for s in scenes:
        if not s.get('scene_prompt') or not s.get('visual_description'):
            raise ValueError('Completed scene_prompt and visual_description required')
        out = local(ep, s['image_file'])
        if out.parent != ep/'imagenes' or out.suffix.lower() != '.png' or out.stem != s['id']:
            raise ValueError('Expected imagenes/<original ID>.png contract')
        outputs.append(str(out))
    if len(outputs) != len(set(outputs)):
        raise ValueError('Scene outputs must be unique')
    return path, scenes


def batch_dir(ep, name):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name):
        raise ValueError('Invalid batch ID')
    return local(ep, 'planificacion_visual/lotes_imagenes/'+name)


def load_batch(ep, name):
    folder = batch_dir(ep, name)
    data = json.loads((folder/'manifest.json').read_text())
    if digest(folder/'prompt.txt') != data['prompt_sha256']:
        raise ValueError('Prompt changed')
    for rel, sha in data['inputs'].items():
        if digest(local(ep, rel)) != sha:
            raise ValueError('Input changed: '+rel)
    return folder, data


def dhash(im):
    im = im.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    pix = list(im.tobytes())
    return sum((pix[y*9+x] > pix[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8))


def plan(ep, args):
    src, scenes = plan_data(ep, args.plan)
    pos = next(i for i, s in enumerate(scenes) if s['id'] == args.start)
    if args.count < 1 or args.count > 9 or args.columns not in (1, 2, 3):
        raise ValueError('Use 1-9 scenes and 1-3 columns')
    selected = scenes[pos:pos+args.count]
    if len(selected) != args.count:
        raise ValueError('Insufficient scenes; specify exact remaining count')
    folder = batch_dir(ep, args.batch)
    if folder.exists():
        raise ValueError('Batch exists: resume it or choose another ID')
    refs = list(dict.fromkeys([*args.reference, args.anchor]))
    inputs = {str(src.relative_to(ep)): digest(src)}
    for r in refs:
        with Image.open(local(ep, r)) as im:
            im.verify()
        inputs[r] = digest(local(ep, r))
    style = ''
    config = local(ep, 'configuracion.json')
    if config.exists():
        inputs['configuracion.json'] = digest(config)
        style = json.loads(config.read_text()).get('style_prompt', '')
    rows = math.ceil(args.count/args.columns)
    prompt = (f'Create ONE NEW atlas: {args.columns} columns x {rows} rows, equal panels, '
              'row-major order. Every panel is an independent 16:9 landscape image. '
              'Exact equal divisions, no gutters, no borders, no panel labels, no crossing objects. '
              'Use references for STYLE and identity only, not their compositions. '
              'Keep simple 2D stickman style when the episode requests it. '
              'Only depict the characters/objects requested in each cell, never force the protagonist. '
              'Specific intentional text overrides generic no-text clauses.\nSTYLE\n'+style+'\n')
    records = []
    for i, s in enumerate(selected):
        records.append({'cell': i+1, 'id': s['id'], 'image_file': s['image_file'],
                        'scene_prompt': s['scene_prompt'], 'visual_description': s['visual_description'],
                        'state': 'pending'})
        prompt += f"\nCELL {i+1}, row {i//args.columns+1}, column {i%args.columns+1}\n{s['scene_prompt']}\n"
    for i in range(args.count, rows*args.columns):
        prompt += f'\nCELL {i+1}: empty neutral blank panel; no extra scene.\n'
    data = {'version': 1, 'plan': args.plan, 'inputs': inputs, 'references': refs,
            'anchor': args.anchor, 'columns': args.columns, 'rows': rows, 'scenes': records,
            'generation_tool': 'not_run', 'reported_cost': None, 'warnings': []}
    folder.mkdir(parents=True)
    atomic(folder/'prompt.txt', prompt.encode())
    data['prompt_sha256'] = digest(folder/'prompt.txt')
    write_json(folder/'manifest.json', data)
    return {'manifest': str(folder/'manifest.json'), 'prompt': str(folder/'prompt.txt'), 'ids': [s['id'] for s in selected]}


def crop(ep, args):
    folder, data = load_batch(ep, args.batch)
    if any(s['state'] != 'pending' for s in data['scenes']) or 'atlas_sha256' in data:
        raise ValueError('Already cropped; preserve batch and use a new attempt ID')
    if digest(folder/'prompt.txt') != data['prompt_sha256']:
        raise ValueError('Prompt changed')
    if (folder/'atlas.png').exists() or (folder/'crops').exists():
        raise ValueError('Interrupted attempt preserved; inspect it and use a new batch ID')
    raw = args.atlas.read_bytes()
    with Image.open(io.BytesIO(raw)) as opened:
        im = opened.convert('RGB')
    w, h = im.size
    columns, rows = data['columns'], data['rows']
    if args.inset < 0 or min(w/columns, h/rows) <= 2*args.inset:
        raise ValueError('Invalid crop inset')
    prepared, hashes = [], []
    for i, s in enumerate(data['scenes']):
        x, y = i % columns, i // columns
        box = [round(x*w/columns)+args.inset, round(y*h/rows)+args.inset,
               round((x+1)*w/columns)-args.inset, round((y+1)*h/rows)-args.inset]
        tile = im.crop(box)
        buffer = io.BytesIO(); tile.save(buffer, format='PNG'); payload = buffer.getvalue()
        sha = hashlib.sha256(payload).hexdigest(); perceptual = dhash(tile)
        for ident, old_sha, old_hash in hashes:
            distance = (perceptual ^ old_hash).bit_count()
            if old_sha == sha or distance <= 3:
                data['warnings'].append({'duplicate_candidate': [ident, s['id']], 'distance': distance, 'exact': old_sha == sha})
        hashes.append((s['id'], sha, perceptual))
        if tile.width < 1280 or tile.height < 720:
            data['warnings'].append({'id': s['id'], 'native_size': list(tile.size), 'note': 'Below 720p; not upscaled'})
        if abs(tile.width/tile.height-16/9) > .1:
            raise ValueError('Panel aspect ratio does not match landscape 16:9')
        s.update(state='cropped_unreviewed', box=box, size=list(tile.size), sha256=sha,
                 dhash=f'{perceptual:016x}', crop='crops/'+s['id']+'.png')
        prepared.append((s['crop'], payload))
    exclusive(folder/'atlas.png', raw)
    for rel, payload in prepared:
        exclusive(local(folder, rel), payload)
    data.update(atlas_sha256=digest(folder/'atlas.png'), atlas_size=[w, h], generation_tool=args.source_kind)
    write_json(folder/'manifest.json', data)
    return {'cropped': len(prepared), 'accepted': 0, 'warnings': data['warnings']}


def accept(ep, args):
    folder, data = load_batch(ep, args.batch)
    if not args.reviewer.strip() or not args.note.strip():
        raise ValueError('Real review identity and note required')
    if digest(folder/'atlas.png') != data['atlas_sha256']:
        raise ValueError('Atlas changed')
    selected = [s for s in data['scenes'] if s['id'] in args.ids]
    if set(args.ids) != {s['id'] for s in selected}:
        raise ValueError('Unknown scene ID')
    from kitok.youtube_stickman_es.images import ImageBatch
    # The current Kitok contract requires 16:9 and at least 1280x720. Native crops stay untouched.
    deliveries = {}
    for s in selected:
        source = local(folder, s['crop'])
        if digest(source) != s['sha256']:
            raise ValueError('Changed crop')
        with Image.open(source) as im:
            native = im.size
            needs_fit = im.width < 1280 or im.height < 720 or abs(im.width/im.height-16/9) > .02
            if needs_fit:
                output = ImageOps.fit(im.convert('RGB'), (1280,720), method=Image.Resampling.LANCZOS)
                buf = io.BytesIO(); output.save(buf, format='PNG'); payload = buf.getvalue()
            else:
                payload = source.read_bytes()
        fd, temp = tempfile.mkstemp(dir=folder, suffix='.png', prefix='.validate-')
        try:
            with os.fdopen(fd, 'wb') as output_file:
                output_file.write(payload)
            ImageBatch.inspect(Path(temp))
        finally:
            Path(temp).unlink(missing_ok=True)
        sha = hashlib.sha256(payload).hexdigest()
        deliveries[s['id']] = (payload, sha, native, needs_fit)
    # Preflight ALL outputs before publishing any, so collisions never produce a partial acceptance.
    for s in selected:
        if s['state'] not in ('cropped_unreviewed', 'accepted') or digest(local(folder, s['crop'])) != s['sha256']:
            raise ValueError('Missing/changed crop')
        dest = local(ep, s['image_file'])
        if dest.exists() and digest(dest) != deliveries[s['id']][1]:
            raise ValueError('Existing image differs; preserve it before authorized repair: '+s['id'])
    for s in selected:
        dest = local(ep, s['image_file']); dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            # Exclusive creation preserves an output that appeared after preflight.
            exclusive(dest, deliveries[s['id']][0])
        if digest(dest) != deliveries[s['id']][1]:
            raise ValueError('Output changed during acceptance')
        from kitok.youtube_stickman_es.images import ImageBatch
        ImageBatch.inspect(dest)
        s.update(delivery_sha256=deliveries[s['id']][1], native_size=list(deliveries[s['id']][2]),
                 processing='LANCZOS fit 1280x720' if deliveries[s['id']][3] else 'native',
                 state='accepted', review={'reviewer': args.reviewer, 'note': args.note})
    write_json(folder/'manifest.json', data)
    return {'accepted': [s['id'] for s in selected], 'remaining': [s['id'] for s in data['scenes'] if s['state'] != 'accepted']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('pending', 'plan', 'crop', 'accept'):
        p = sub.add_parser(name); p.add_argument('episode', type=Path)
        if name in ('pending', 'plan'): p.add_argument('--plan', required=True)
        if name != 'pending': p.add_argument('--batch', required=True)
        if name == 'plan':
            p.add_argument('--start', required=True);p.add_argument('--count', type=int, default=9)
            p.add_argument('--columns', type=int, default=3);p.add_argument('--reference', action='append', default=[])
            p.add_argument('--anchor', required=True)
        if name == 'crop':
            p.add_argument('--atlas', type=Path, required=True);p.add_argument('--inset', type=int, default=8)
            p.add_argument('--source-kind', choices=['builtin_imagegen', 'existing_atlas', 'test_fixture'], required=True)
        if name == 'accept':
            p.add_argument('--ids', nargs='+', required=True);p.add_argument('--reviewer', required=True);p.add_argument('--note', required=True)
    args = parser.parse_args(); ep = args.episode.absolute()
    try:
        if ep.is_symlink() or ep.resolve() != ep or not ep.is_dir():
            raise ValueError('Use an existing canonical episode directory')
        if args.command == 'pending':
            _, scenes = plan_data(ep, args.plan)
            reviewed = set()
            stale = []
            for manifest in (ep/'planificacion_visual/lotes_imagenes').glob('*/manifest.json'):
                try:
                    _, batch = load_batch(ep, manifest.parent.name)
                    for record in batch['scenes']:
                        if record['state'] == 'accepted':
                            if digest(local(ep, record['image_file'])) == record.get('delivery_sha256', record['sha256']):
                                reviewed.add(record['id'])
                            else:
                                stale.append(record['id'])
                except (OSError, ValueError, KeyError):
                    stale.append(manifest.parent.name)
            result = {'reviewed': sorted(reviewed), 'stale': stale, ** {'missing': [s['id'] for s in scenes if not local(ep, s['image_file']).exists()],
                      'existing_requires_visual_evidence': [s['id'] for s in scenes if local(ep, s['image_file']).exists() and s['id'] not in reviewed]}}
        else:
            result = globals()[args.command](ep, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, StopIteration) as e:
        parser.exit(2, f'blocked: {e}\n')


if __name__ == '__main__':
    main()
