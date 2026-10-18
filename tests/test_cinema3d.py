"""Bad render specifications fail before Chromium, files, or external providers."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def invoke(spec, output, *extra):
    node = shutil.which('node')
    if not node or not (ROOT / 'frontend/node_modules/playwright').is_dir():
        pytest.skip('Optional 3D renderer requires installed frontend dependencies')
    return subprocess.run(
        [node, str(ROOT / 'scripts/cinema3d.mjs'), '--spec', str(spec),
         '--output', str(output), *map(str, extra)],
        capture_output=True, text=True, timeout=10,
    )


@pytest.mark.parametrize('change', [
    {'width': 1919}, {'height': 1081}, {'width': 10000}, {'fps': 120},
    {'duration': 31}, {'reveal_at': -1}, {'mode': 'invented'},
    {'shot': 'file:///etc/passwd'}, {'label': 'x' * 71},
])
def test_cinema3d_rejects_invalid_spec_before_browser(tmp_path, change):
    spec = tmp_path / 'spec.json'
    spec.write_text(json.dumps({'mode': 'private', **change}))
    output = tmp_path / 'should-not-exist.mp4'
    result = invoke(spec, output)
    assert result.returncode != 0
    assert not output.exists()
    assert not list(tmp_path.glob('*.part.mp4'))
    assert 'Unsupported' in result.stderr or 'Invalid' in result.stderr


@pytest.mark.parametrize('protected', ['spec', 'output', 'pending', 'preview', 'symlink'])
def test_cinema3d_preserves_inputs_outputs_and_pending_work(tmp_path, protected):
    spec = tmp_path / 'spec.json'
    original = json.dumps({'mode': 'private'})
    spec.write_text(original)
    output = tmp_path / 'clip.mp4'
    extra = []
    if protected == 'spec':
        output = spec
    elif protected == 'output':
        output.write_bytes(b'operator video')
    elif protected == 'pending':
        (tmp_path / 'clip.stage3d.part.mp4').write_bytes(b'active render')
    elif protected == 'preview':
        (tmp_path / 'preview_before.jpg').write_bytes(b'operator picture')
        extra = ['--previews', tmp_path / 'preview']
    else:
        output.symlink_to(spec)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = invoke(spec, output, *extra)
    assert result.returncode != 0
    assert 'Refusing' in result.stderr or 'Unsupported output' in result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
