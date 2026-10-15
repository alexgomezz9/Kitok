"""Isolated browser fixture: real HTTP/files, simulated paid renderers only."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kitok.api import create_app
from kitok.config import Settings
from kitok.state import StateStore
import kitok.application


def sample(path, geometry):
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=0x315a43:s={geometry}:r=25',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '5',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-movflags', '+faststart', str(path)], check=True, timeout=30)


def main():
    with tempfile.TemporaryDirectory(prefix='kitok-browser-') as directory:
        root = Path(directory)
        background = root / 'assets/backgrounds/random'
        background.mkdir(parents=True)
        vertical = background / 'test.mp4'
        horizontal = root / 'horizontal.mp4'
        sample(vertical, '360x640')
        sample(horizontal, '640x360')
        delivery = root / 'phone'
        if os.environ.get('KITOK_E2E_UNAVAILABLE_DELIVERY') == '1':
            delivery.write_text('unavailable external destination')
        settings = Settings(_env_file=None, data_root=root, ready_dir=delivery,
                            background_root=root / 'assets/backgrounds', character_root=root / 'characters',
                            native_cache_dir=root / 'cache', fish_api_key='browser-test', pexels_api_key='browser-test')
        app = create_app(settings)
        def short_render(settings, queue, state, client, preset, *, ids, **kwargs):
            for cid in ids:
                destination = settings.local_ready_dir / f'{cid}.mp4'
                shutil.copyfile(vertical, destination)
                state.upsert(cid, status='ready', ready_path=str(destination), validation={'duration': 5.0})
        def long_render(record, definition, stage):
            stage('Render de prueba local: sin proveedores externos')
            path = app.state.longform.output_path(record['id'])
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(horizontal, path)
        kitok.application.run_generation = short_render
        app.state.longform._render = long_render
        uvicorn.run(app, host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
