import hashlib
import subprocess
from types import SimpleNamespace

from PIL import Image
import pytest

from kitok.editing.production import _blend_frames,render_editorial_plan
from kitok.editing.storyboard import EditorialPlan,EditorialScene,EditorialAsset
from kitok.media.ffprobe import probe_video_clock


def test_transition_duration_validates_and_legacy_default_is_unchanged():
    assert _blend_frames(150,150,30)==8
    assert _blend_frames(150,150,30,.4)==12
    assert _blend_frames(30,12,30,.4)==4
    for value in (0,2,float('nan')):
        with pytest.raises(ValueError):
            EditorialPlan(episode_id='test',title='Test',audio_source='a.wav',duration=2,
                          transition_duration=value,assets={'a':EditorialAsset(path='a.png',description='A')},
                          scenes=[EditorialScene(id='a',start=0,end=2,asset='a',intention='Test',spoken_claim='Test')])


def test_real_duration_change_invalidates_transition_cache_preserving_frames_and_output_hash(tmp_path):
    for name,color in [('a','ivory'),('b','maroon')]:Image.new('RGB',(320,180),color).save(tmp_path/(name+'.png'))
    audio=tmp_path/'audio.m4a'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','sine=frequency=220:duration=4',
                    '-c:a','aac',str(audio)],check=True,capture_output=True)
    plan=EditorialPlan(episode_id='duration',title='Duration test',audio_source=audio.name,duration=4,
                       width=320,height=180,assets={key:EditorialAsset(path=key+'.png',description=key) for key in ('a','b')},
                       scenes=[EditorialScene(id=key,start=i*2,end=(i+1)*2,asset=key,intention='Technical test',
                                              spoken_claim='Test',transition='cut' if i==0 else 'dissolve')
                               for i,key in enumerate(('a','b'))])
    settings=SimpleNamespace(ffmpeg_binary='ffmpeg',ffprobe_binary='ffprobe')
    first=render_editorial_plan(plan,root=tmp_path,output=tmp_path/'first.mp4',settings=settings,encoder_name='libx264')
    handle=tmp_path/'.editorial-work/duration/a.handle.mp4'
    assert probe_video_clock(handle).frames==8
    plan.transition_duration=.4
    second=render_editorial_plan(plan,root=tmp_path,output=tmp_path/'second.mp4',settings=settings,encoder_name='libx264')
    assert probe_video_clock(handle).frames==12
    assert not second['reused_scenes']
    third=render_editorial_plan(plan,root=tmp_path,output=tmp_path/'third.mp4',settings=settings,encoder_name='libx264')
    assert third['reused_scenes']==['a','b']
    for name,result in [('first',first),('second',second),('third',third)]:
        output=tmp_path/(name+'.mp4')
        assert probe_video_clock(output).frames==120
        assert result['output_sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
