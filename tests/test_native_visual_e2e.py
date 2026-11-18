"""One real offline Native -> shared documentary renderer -> delivery regression."""
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image
import pytest

from kitok.config import Settings
from kitok.longform.cli import load_longform_config
from kitok.media.ffmpeg import EncoderSettings, FFmpegNativeEngine, RenderSpec
from kitok.media.ffprobe import probe_video_clock
from kitok.rendering.native import NativeLongformRenderer
from kitok.stock.models import StockAsset, StockVariant, SelectedStock


@pytest.mark.parametrize('mode', ['photo', 'documentary', 'hybrid', 'case_only'])
def test_native_visual_config_reaches_shared_ffmpeg_delivery(tmp_path, mode, monkeypatch, capsys):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg is required for the real media integration')
    def ffmpeg(*args):
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y',*args],check=True,capture_output=True)
    stock=tmp_path/'stock.mp4'
    voice=tmp_path/'voice.wav'
    ffmpeg('-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','8','-c:v','libx264',
           '-preset','ultrafast','-pix_fmt','yuv420p',str(stock))
    ffmpeg('-f','lavfi','-i','sine=frequency=230:sample_rate=48000','-t','6',str(voice))
    episode = tmp_path / 'content/longform/loose_thread/fixture'
    (episode / 'images').mkdir(parents=True)
    Image.new('RGB',(350,500),'#aa9966').save(episode/'images'/'real.png')
    script='The city appears. This photograph documents the original story.'
    (episode/'script.txt').write_text(script)
    config={'id':'native_visual_test','subject':'Test with supplied photograph','script_file':str(episode/'script.txt'),
            'keywords':['city'],'narrator_voice':'fish_audio:test:Narrator','music_enabled':False,'music_mode':'off',
            'visual_plan':{'visual_cues':[{'asset':'images/real.png','start':1.5,'duration':2.4}]}}
    if mode == 'documentary':
        config.pop('visual_plan')
        config['mounting_style']='documentary'
    elif mode in {'hybrid', 'case_only'}:
        case_clip = episode / 'case.mp4'
        ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=160x180:rate=30', '-t', '8',
               '-c:v', 'libx264', '-preset', 'ultrafast', str(case_clip))
        config['visual_plan']['visual_cues'] = ([
            {'asset': 'case.mp4', 'anchor': {'phrase': 'The city'}, 'duration': 1.2, 'source_start': .5,
             'usage': 'document', 'credit': 'Fixture credit', 'license': 'Fixture license'},
            *config['visual_plan']['visual_cues'],
        ] if mode == 'hybrid' else [{'asset': 'case.mp4', 'start': 0, 'duration': 6, 'source_start': .5}])
    (episode/'config.json').write_text(json.dumps(config))
    definition=load_longform_config(episode/'config.json',project_root=tmp_path)
    settings=Settings(_env_file=None,data_root=tmp_path)
    calls=[]
    class Fish:
        def __init__(self,*args,**kwargs):
            calls.append('fish-fixture')
        def synthesize(self,text,reference,output,**kwargs):
            shutil.copyfile(voice,output)
            output.with_suffix('.alignment.json').write_text(json.dumps({'method': 'fish_provider_timestamps', 'words':[
                {'word':word,'start':i*.6,'end':(i+1)*.6} for i,word in enumerate(script.split())]}))
        def close(self):
            pass
    asset=StockAsset(1,'city',8.,(StockVariant('https://unused.invalid/stock.mp4',320,180,30),))
    selection=SelectedStock(asset,asset.variants[0])
    class Stock:
        def search_videos(self,*args,**kwargs):
            calls.append('stock-fixture'); return [asset]
        def select_candidate(self,*args,**kwargs):
            return selection
        def download_asset(self,*args):
            return stock
    output=tmp_path/'outputs'/'longform'/'native_visual_test.mp4'
    engine=FFmpegNativeEngine(encoder=EncoderSettings('libx264','ultrafast'),spec=RenderSpec(width=320,height=180))
    keep_workspace = mode == 'documentary'
    result = NativeLongformRenderer(settings, Stock(), engine, output_path=output,
                                    fish_factory=Fish, keep_workspace=keep_workspace).render(definition)
    assert result.output == output
    assert calls == (['fish-fixture'] if mode == 'case_only' else ['fish-fixture', 'stock-fixture'])
    clock=probe_video_clock(output)
    assert clock.frames==180 and clock.start_time==0
    manifest=json.loads(output.with_suffix('.native.json').read_text())
    if mode == 'photo':
        assert manifest['visual_sources'][0]['path']==str((episode / 'images/real.png').relative_to(tmp_path))
    receipt=json.loads(output.with_suffix('.editorial.json').read_text())
    if mode != 'documentary':
        assert any((scene.get('asset') or '').startswith('visual_') for scene in receipt['scenes'])
        assert 'Photographs and documents supplied' in output.with_suffix('.credits.md').read_text()
    else:
        plan=json.loads((output.parent/'.native-work'/definition.item.id/'motion-plan.json').read_text())
        assert plan['fade_in']==.6 and plan['fade_out']==.8
        assert plan['scenes'][0]['start']==0 and plan['scenes'][-1]['end']==6.
    if mode in {'hybrid', 'case_only'}:
        plan = json.loads((output.parent / '.native-work' / definition.item.id / 'motion-plan.json').read_text())
        case_scene = next(scene for scene in plan['scenes'] if scene['asset'] == 'visual_0')
        assert case_scene['source_start'] == pytest.approx(.5)
        assert case_scene['camera']['preset'] == 'static' and case_scene['image_fit'] == 'contain'
        assert manifest['visual_sources'][0]['path'] == str((episode / 'case.mp4').relative_to(tmp_path))
        assert bool(manifest['stock_sources']) is (mode == 'hybrid')
        if mode == 'hybrid':
            assert plan['alignment']['visual_cues'][0]['timing'] == 'provider-phrase-anchor'
            assert manifest['visual_sources'][0]['license'] == 'Fixture license'
            assert 'Fixture credit' in output.with_suffix('.credits.md').read_text()
    work = output.parent / '.native-work' / definition.item.id
    assert (work / 'narration.mp3').is_file()
    assert (work / 'narration.alignment.json').is_file()
    assert (work / 'motion-plan.json').is_file()
    assert (tmp_path / receipt['validation_report']).is_file()
    editorial_work = output.parent / '.editorial-work' / receipt['episode_id']
    assert bool(list(editorial_work.glob('shot_*.mp4'))) is keep_workspace
    if not keep_workspace:
        assert set(path.name for path in editorial_work.iterdir()) == {
            'render.lock', Path(receipt['validation_report']).name,
        }
    ffmpeg('-xerror','-i',str(output),'-f','null','-')


    if mode != 'hybrid':
        return
    from kitok.longform import cli
    from kitok.youtube_stickman_es.audio import read_srt

    def no_provider(*args, **kwargs):
        pytest.fail('An existing render must never reach the stock provider')

    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    monkeypatch.setattr(cli, 'load_longform_config', lambda path: load_longform_config(path, project_root=tmp_path))
    monkeypatch.setattr('kitok.providers.pexels.PexelsProvider', no_provider)
    argv = [str(episode / 'config.json')]
    target = episode / 'entrega'
    assert cli.main([*argv, '--deliver-only']) == 1
    assert 'publicacion_youtube.json' in capsys.readouterr().err
    assert not target.exists()

    (episode / 'editorial').mkdir()
    (episode / 'miniaturas').mkdir()
    thumb = episode / 'miniaturas/miniatura_final.png'
    Image.new('RGB', (1280, 720), '#123456').save(thumb)
    publication = {
        'title': 'Fixture title',
        'description': 'Fixture description',
        'tags': ['city', 'source footage'],
        'settings': {'language': 'English', 'category': 'Education', 'made_for_kids': False,
                     'altered_content': False},
    }
    metadata = episode / 'editorial/publicacion_youtube.json'
    metadata.write_text(json.dumps(publication))
    supplied = episode / 'voz.srt'
    supplied.write_text('1\n00:00:00,000 --> 00:00:01,000\nWrong text\n')
    assert cli.main([*argv, '--deliver']) == 1
    assert 'transcript must match' in capsys.readouterr().err
    assert not target.exists()
    supplied.unlink()

    assert cli.main([*argv, '--deliver']) == 0
    assert (target / 'video_final.mp4').samefile(output)
    assert (target / 'miniatura.png').read_bytes() == thumb.read_bytes()
    assert (target / 'titulo.txt').read_text() == 'Fixture title\n'
    assert (target / 'descripcion.txt').read_text() == 'Fixture description\n'
    assert (target / 'etiquetas.txt').read_text() == 'city, source footage\n'
    assert 'English' in (target / 'ajustes_youtube.txt').read_text()
    cues = read_srt(target / 'voz.srt')
    assert cues[0]['start'] == 0 and cues[-1]['end'] == pytest.approx(5.4)
    assert ' '.join(cue['text'] for cue in cues) == script
    assert cli.main([*argv, '--deliver-only']) == 0

    from kitok.longform.episodes import MOVES_PATH
    canonical = episode.with_name('001_fixture')
    history = tmp_path / MOVES_PATH
    history.parent.mkdir(exist_ok=True)
    history.write_text(json.dumps({str(episode.relative_to(tmp_path)): str(canonical.relative_to(tmp_path))}))
    episode.rename(canonical)
    assert cli.main([*argv, '--deliver-only']) == 0
    metadata = canonical / metadata.relative_to(episode)
    episode = canonical
    target = episode / 'entrega'
    assert (target / 'video_final.mp4').samefile(output)

    publication['title'] = 'A different title'
    metadata.write_text(json.dumps(publication))
    assert cli.main([*argv, '--deliver-only']) == 1
    assert 'Existing entrega was preserved' in capsys.readouterr().err
    assert (target / 'titulo.txt').read_text() == 'Fixture title\n'
    assert not list(episode.glob('.entrega-*'))
    capsys.readouterr()
    config['voice_rate'] = 1.04
    (episode / 'config.json').write_text(json.dumps(config))
    assert cli.main([*argv, '--deliver-only']) == 1
    assert 'different montage or narration settings' in capsys.readouterr().err


@pytest.mark.parametrize("provider_duration, has_replacement", [
    (7.0, True),
    (7.1, True),
    (7.1, False),
])
def test_native_reselects_short_stock_without_changing_frame_clock(
    tmp_path, monkeypatch, caplog, provider_duration, has_replacement
):
    from kitok.longform.models import TimelineSlot
    from kitok.rendering.native import NativeRenderError
    from kitok.stock.selector import StockSelector

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for the real media integration")

    def ffmpeg(*args):
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", *args],
            check=True, capture_output=True,
        )

    short_stock = tmp_path / "short.mp4"
    usable_stock = tmp_path / "usable.mp4"
    voice = tmp_path / "voice.wav"
    # These frame boundaries reproduce 7.010167 s of required source coverage.
    first_duration = 6.023166666666667
    duration = first_duration + 7.0
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
           "-frames:v", "208", "-c:v", "libx264", "-preset", "ultrafast", str(short_stock))
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
           "-frames:v", "240", "-c:v", "libx264", "-preset", "ultrafast", str(usable_stock))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=230:sample_rate=48000",
           "-t", str(duration), str(voice))
    script = "The city appears. The road shows the next part of the story."
    (tmp_path / "script.txt").write_text(script)
    config = {
        "id": "native_stock_duration",
        "subject": "Measured stock coverage",
        "script_file": "script.txt",
        "keywords": ["city", "road"],
        "narrator_voice": "fish_audio:test:Narrator",
        "music_enabled": False,
        "music_mode": "off",
        "mounting_style": "documentary",
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    definition = load_longform_config(tmp_path / "config.json", project_root=tmp_path)
    slots = [
        TimelineSlot(0, "city", 0.0, first_duration),
        TimelineSlot(1, "road", first_duration, 7.0),
    ]
    monkeypatch.setattr("kitok.rendering.native.build_semantic_timeline", lambda *a, **kw: slots)

    class Fish:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, text, reference, output, **kwargs):
            shutil.copyfile(voice, output)
            words = script.split()
            output.with_suffix(".alignment.json").write_text(json.dumps({
                "words": [
                    {"word": word, "start": i * duration / len(words),
                     "end": (i + 1) * duration / len(words)}
                    for i, word in enumerate(words)
                ],
            }))

        def close(self):
            pass

    variant = StockVariant("https://unused.invalid/stock.mp4", 320, 180, 30)
    first = StockAsset(1, "city", 8.0, (variant,))
    short = StockAsset(6124789, "road", provider_duration, (variant,))
    replacement = StockAsset(3, "road", 8.0, (variant,))
    downloads = []

    class Stock:
        def search_videos(self, query, **kwargs):
            if query == "city":
                return [first]
            return [short, replacement] if has_replacement else [short]

        def select_candidate(self, assets, **kwargs):
            return StockSelector().select_candidate(assets, **kwargs)

        def download_asset(self, selection):
            downloads.append(selection.asset.asset_id)
            return short_stock if selection.asset.asset_id == 6124789 else usable_stock

    output = tmp_path / "outputs" / "longform" / "native_stock_duration.mp4"
    settings = Settings(_env_file=None, data_root=tmp_path)
    engine = FFmpegNativeEngine(
        encoder=EncoderSettings("libx264", "ultrafast"),
        spec=RenderSpec(width=320, height=180),
    )
    renderer = NativeLongformRenderer(
        settings, Stock(), engine, output_path=output,
        fish_factory=Fish, keep_workspace=True,
    )
    if not has_replacement:
        with pytest.raises(NativeRenderError, match="asset=6124789.*slot=2"):
            renderer.render(definition)
        assert downloads == [1, 6124789]
        assert not output.exists()
        assert not output.with_suffix(".native.json").exists()
        assert not list(tmp_path.rglob("motion-plan.json"))
        return

    renderer.render(definition)
    assert downloads == ([1, 3] if provider_duration == 7.0 else [1, 6124789, 3])
    clock = probe_video_clock(output)
    assert clock.frames == round(duration * 30) == 391
    assert clock.start_time == 0
    assert clock.duration == pytest.approx(391 / 30)
    manifest = json.loads(output.with_suffix(".native.json").read_text())
    assert [clip["asset_id"] for clip in manifest["timeline"]] == [1, 3]
    assert manifest["timeline"][1]["timeline_start"] == first_duration
    assert manifest["timeline"][1]["duration"] == 7.0
    assert {row["asset_id"] for row in manifest["stock_sources"]} == {1, 3}
    work = output.parent / ".native-work" / definition.item.id
    assert (work / "narration.mp3").read_bytes() == voice.read_bytes()
    if provider_duration > 7.0:
        assert "6124789" in caplog.text and "replacement" in caplog.text
