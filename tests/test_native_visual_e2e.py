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
def test_native_visual_config_reaches_shared_ffmpeg_delivery(tmp_path, mode):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg is required for the real media integration')
    def ffmpeg(*args):
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y',*args],check=True,capture_output=True)
    stock=tmp_path/'stock.mp4'
    voice=tmp_path/'voice.wav'
    ffmpeg('-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','8','-c:v','libx264',
           '-preset','ultrafast','-pix_fmt','yuv420p',str(stock))
    ffmpeg('-f','lavfi','-i','sine=frequency=230:sample_rate=48000','-t','6',str(voice))
    episode=tmp_path/'episode'; (episode/'images').mkdir(parents=True)
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
            output.with_suffix('.alignment.json').write_text(json.dumps({'words':[
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
    result=NativeLongformRenderer(settings,Stock(),engine,output_path=output,fish_factory=Fish).render(definition)
    assert result.output == output
    assert calls == (['fish-fixture'] if mode == 'case_only' else ['fish-fixture', 'stock-fixture'])
    clock=probe_video_clock(output)
    assert clock.frames==180 and clock.start_time==0
    manifest=json.loads(output.with_suffix('.native.json').read_text())
    if mode == 'photo':
        assert manifest['visual_sources'][0]['path']=='episode/images/real.png'
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
        assert manifest['visual_sources'][0]['path'] == 'episode/case.mp4'
        assert bool(manifest['stock_sources']) is (mode == 'hybrid')
        if mode == 'hybrid':
            assert plan['alignment']['visual_cues'][0]['timing'] == 'provider-phrase-anchor'
            assert manifest['visual_sources'][0]['license'] == 'Fixture license'
            assert 'Fixture credit' in output.with_suffix('.credits.md').read_text()
    ffmpeg('-xerror','-i',str(output),'-f','null','-')
