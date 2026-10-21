"""Real local camera/transition proofs: images share the documentary frame clock."""
import json
import subprocess
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageStat
import pytest

from kitok.editing.camera import CameraMotion, camera_filters, image_plate
from kitok.editing.motion_components import MotionDesign, treatment_filters, write_motion_ass
from kitok.editing.production import render_editorial_plan
from kitok.editing.storyboard import EditorialAsset, EditorialPlan, EditorialScene


def ffmpeg(*args):
    return subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *map(str,args)],
                          check=True, capture_output=True, timeout=60)


def frame(path, *, index):
    data = ffmpeg('-i',path,'-vf',f'select=eq(n\\,{index})','-frames:v',1,
                  '-pix_fmt','rgb24','-f','rawvideo','-').stdout
    return Image.frombytes('RGB',(320,180),data)


def test_camera_validation_and_source_document_highlight(tmp_path):
    assert CameraMotion.model_validate('slow_pull_out').preset == 'slow_pull_out'
    for invalid in ({'preset':'parallax'}, {'focus_x':1.1}, {'rotation':3}, {'end_scale':float('nan')}):
        with pytest.raises(ValueError):
            CameraMotion.model_validate(invalid)
    source = tmp_path/'document.png'
    Image.new('RGB',(120,240),'white').save(source)
    original = source.read_bytes()
    target = tmp_path/'plate.png'
    image_plate(source,target,width=320,height=180,fit='contain',highlight_box=(.2,.2,.8,.4))
    with Image.open(target) as image:
        # Whole document is 79x158 centered, with its top/bottom and source box intact.
        assert image.getpixel((160,12)) == (255,255,255)
        assert image.getpixel((160,166)) == (255,255,255)
        assert image.getpixel((160,60))[2] < 240
    assert source.read_bytes() == original
    design=MotionDesign(effect='document',highlight_box=(.2,.2,.8,.4))
    assert not write_motion_ass(design,tmp_path/'highlight.ass',duration=2,width=320,height=180,over_stock=True)
    with pytest.raises(ValueError):
        MotionDesign(effect='document',highlight_box=(.8,.2,.2,.4))


def test_resumed_motion_validates_remaining_delay_at_short_stock_boundary():
    scene=EditorialScene(id='continuation',start=4,end=4.4,
        intention='Continue the same approved emphasis',spoken_claim='20 million',asset='stock',
        motion_design=MotionDesign(effect='amount',text='20 million',delay=.5,elapsed=3,hold=3.4))
    assert scene.motion_design.elapsed==3
    with pytest.raises(ValueError,match='Motion delay must leave a readable interval'):
        EditorialScene(id='unreadable',start=4,end=4.4,
            intention='Wait before emphasis',spoken_claim='20 million',asset='stock',
            motion_design=MotionDesign(effect='amount',text='20 million',delay=.5,elapsed=.1))


def test_global_cue_accepts_brief_entering_fragment_and_skips_inactive_phases(tmp_path):
    design=MotionDesign(effect='amount',text='20 million',delay=3.9,hold=2)
    scene=EditorialScene(id='before-cut',start=0,end=4,intention='Preserve exact spoken anchor',
                         spoken_claim='20 million',asset='stock',motion_design=design)
    assert write_motion_ass(scene.motion_design,tmp_path/'entering.ass',duration=4,width=320,height=180)
    for name,elapsed in [('before',0),('after',8)]:
        local=design.model_copy(update={'elapsed':elapsed})
        assert not write_motion_ass(local,tmp_path/f'{name}.ass',duration=1,width=320,height=180)
    with pytest.raises(ValueError,match='no readable interval'):
        write_motion_ass(MotionDesign(effect='amount',text='20 million',delay=.9),
                         tmp_path/'invalid.ass',duration=1,width=320,height=180)


def test_real_global_overlay_continues_across_stock_boundary_without_restart(tmp_path):
    from PIL import ImageChops
    design=MotionDesign(effect='amount',text='20 million',label='Approved amount',delay=3.9,hold=2)
    whole=tmp_path/'whole.ass'
    before=tmp_path/'before.ass'
    after=tmp_path/'after.ass'
    write_motion_ass(design,whole,duration=8,width=320,height=180,over_stock=True)
    write_motion_ass(design,before,duration=4,width=320,height=180,over_stock=True)
    write_motion_ass(design.model_copy(update={'elapsed':4}),after,duration=4,width=320,height=180,over_stock=True)
    for i,stamp in enumerate([3.9,4.,4.1,4.3,5.8,6.]):
        pictures=[]
        for suffix,ass,duration,seek in [('continuous',whole,8,stamp),
            ('split',before if stamp<4 else after,4,stamp if stamp<4 else stamp-4)]:
            target=tmp_path/f'{i}-{suffix}.png'
            ffmpeg('-f','lavfi','-i',f'color=c=0x29323a:s=320x180:r=30:d={duration}',
                   '-vf',f'ass={ass}','-ss',f'{seek:.9f}','-frames:v',1,target)
            with Image.open(target) as picture:pictures.append(picture.convert('RGB'))
        assert max(ImageStat.Stat(ImageChops.difference(*pictures)).mean)<1,stamp


def test_compiler_prefix_can_extend_valid_operator_delay_beyond_fifteen_seconds(tmp_path):
    from kitok.editing.manifest import build_edit_manifest
    from kitok.editing.motion import motion_plan
    from kitok.editing.visual_cues import VisualCue
    from kitok.longform.models import TimelineClip, TimelineSlot
    stock=tmp_path/'stock.mp4'; stock.write_bytes(b'compile fixture')
    narration=tmp_path/'voice.mp3'; narration.write_bytes(b'compile fixture')
    script='An explicitly delayed amount remains anchored to the same continuous narration.'
    clips=[TimelineClip(TimelineSlot(index=i,start=start,duration=length,query='fixture'),1,stock,0.)
           for i,(start,length) in enumerate([(0.,8.8),(8.8,23.2)])]
    plan=motion_plan(clips,narration,32.,root=tmp_path,episode_id='prefix',
        editing=build_edit_manifest(script,32.,['fixture']),style='basic',script=script,
        visual_plan={'visual_cues':[{'start':8.5,'duration':20,'effect':'amount','text':'20 million',
                                    'motion_data':{'delay':14}}]})
    designs=[scene.motion_design for scene in plan.scenes if scene.motion_design]
    assert designs[0].delay==pytest.approx(22.5)
    active=next(design for design in designs if design.elapsed>0)
    ass=tmp_path/'delayed.ass'
    assert write_motion_ass(active,ass,duration=20,width=320,height=180)
    # Render the same valid global phase after the compiler's long prefix.
    ffmpeg('-f','lavfi','-i','color=c=0x29323a:s=320x180:r=30:d=20',
           '-vf',f'ass={ass}','-ss',str(max(0,active.delay-active.elapsed)+.5),
           '-frames:v',1,tmp_path/'delayed.png')
    with pytest.raises(ValueError,match='may not exceed 15 seconds'):
        VisualCue(start=0,duration=30,effect='amount',text='20 million',motion_data={'delay':16})


@pytest.mark.parametrize('preset', ['slow_push_in','slow_pull_out','pan_left','pan_right',
    'pan_up','pan_down','diagonal_drift','subtle_rotation','zoom_and_pan','focus_push','static'])
def test_camera_presets_decode_without_exposing_edges(tmp_path,preset):
    target=tmp_path/f'{preset}.mp4'
    filters=camera_filters(CameraMotion(preset=preset,rotation=2 if preset=='subtle_rotation' else 0,
                                        focus_x=0 if preset=='subtle_rotation' else .5),
                           width=320,height=180,frames=12,fps=30)
    ffmpeg('-f','lavfi','-i','color=c=0xb48246:s=320x180:r=30',
           '-vf',','.join(filters) if filters else 'null','-filter_threads','1',
           '-frames:v','12','-c:v','libx264','-pix_fmt','yuv420p',target)
    for index in (0,6,11):
        decoded=frame(target,index=index)
        assert min(v[0] for v in decoded.getextrema()) > 30


def test_real_photo_stock_moving_transitions_and_global_fades_preserve_audio(tmp_path):
    source=tmp_path/'stock.mp4'
    ffmpeg('-f','lavfi','-i','testsrc2=size=320x180:rate=30000/1001:duration=4',
           '-c:v','libx264','-pix_fmt','yuv420p',source)
    photo=tmp_path/'portrait.png'
    picture=Image.new('RGB',(140,280),'ivory')
    draw=ImageDraw.Draw(picture)
    for y in range(15,270,20):draw.line((5,y,130,y),fill='maroon',width=3)
    picture.save(photo)
    audio=tmp_path/'approved.m4a'
    ffmpeg('-f','lavfi','-i','sine=frequency=220:duration=6','-c:a','aac',audio)
    audio_before=audio.read_bytes()
    transitions=['cut','dissolve','wipe','slide','fade_black','focus']
    plan=EditorialPlan(episode_id='photo-stock',title='Local mixed visual proof',audio_source=audio.name,
        duration=6,width=320,height=180,fade_in=.6,fade_out=.8,
        assets={'stock':EditorialAsset(path=source.name,description='Synthetic fractional stock'),
                'photo':EditorialAsset(path=photo.name,description='Supplied portrait')},
        scenes=[EditorialScene(id=f's{i}',start=i,end=i+1,intention='Mix existing visual inputs',
            spoken_claim='Synthetic fixture',asset='photo' if i%2 else 'stock',source_start=0 if i%2 else .679181,
            camera='slow_push_in',transition=transition)
            for i,transition in enumerate(transitions)])
    output=tmp_path/'delivery.mp4'
    render_editorial_plan(plan,root=tmp_path,output=output,settings=SimpleNamespace(
        ffmpeg_binary='ffmpeg',ffprobe_binary='ffprobe'),encoder_name='libx264')
    frames=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_frames','-show_entries','frame=pix_fmt,best_effort_timestamp_time',
        '-of','json',str(output)]))['frames']
    assert len(frames)==180
    assert {f['pix_fmt'] for f in frames}=={'yuv420p'}
    assert float(frames[0]['best_effort_timestamp_time'])==0
    assert float(frames[-1]['best_effort_timestamp_time'])==pytest.approx(179/30,abs=1e-6)
    assert max(ImageStat.Stat(frame(output,index=0)).mean)<3
    assert max(ImageStat.Stat(frame(output,index=179)).mean)<3
    workspace=tmp_path/'.editorial-work'/plan.episode_id
    assert not list(workspace.glob('*.previous.png'))
    # The first transition frame continues AFTER the preceding final frame.
    # The renderer emits the next frames as a separate continuation handle.
    tail=frame(workspace/'s0.handle.mp4',index=0)
    incoming=frame(workspace/'s1.mp4',index=0)
    from PIL import ImageChops
    assert sum(ImageStat.Stat(ImageChops.difference(tail,incoming)).mean)<5
    replay=frame(workspace/'s0.mp4',index=22)
    assert sum(ImageStat.Stat(ImageChops.difference(replay,incoming)).mean)>5
    def audio_hash(path):
        return ffmpeg('-i',path,'-map','0:a:0','-c:a','copy','-f','hash','-hash','sha256','-').stdout
    assert audio_hash(audio)==audio_hash(output)
    assert audio.read_bytes()==audio_before
    ffmpeg('-xerror','-i',output,'-f','null','-')


def test_date_typewriter_reveals_actual_glyphs_in_order(tmp_path):
    design=MotionDesign(effect='date_typewriter_focus',text='2007',delay=0)
    ass=tmp_path/'date.ass'
    write_motion_ass(design,ass,duration=1,width=320,height=180)
    output=tmp_path/'typed.mp4'
    ffmpeg('-f','lavfi','-i','color=c=0x10141a:s=320x180:r=30:d=1',
           '-vf',f'ass={ass}','-c:v','libx264','-pix_fmt','yuv420p',output)
    from PIL import ImageChops
    early=frame(output,index=1).crop((45,48,160,90))
    late=frame(output,index=18).crop((45,48,160,90))
    # Later digits occupy the same stable baseline; this region is empty at entry.
    assert sum(ImageStat.Stat(ImageChops.difference(early,late)).mean)>8


def test_transition_without_source_continuation_uses_reported_safe_cut(tmp_path):
    stock=tmp_path/'exact.mp4'
    ffmpeg('-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=1',
           '-c:v','libx264','-pix_fmt','yuv420p',stock)
    audio=tmp_path/'audio.m4a'
    ffmpeg('-f','lavfi','-i','sine=frequency=220:duration=2','-c:a','aac',audio)
    plan=EditorialPlan(episode_id='no-handle',title='Safe optional transition',audio_source=audio.name,
        duration=2,width=320,height=180,
        assets={'stock':EditorialAsset(path=stock.name,description='Exactly one second')},
        scenes=[EditorialScene(id=f's{i}',start=i,end=i+1,intention='Preserve exact coverage',
            spoken_claim='Synthetic fixture',asset='stock',transition='cut' if i==0 else 'dissolve')
            for i in range(2)])
    result=render_editorial_plan(plan,root=tmp_path,output=tmp_path/'safe.mp4',
        settings=SimpleNamespace(ffmpeg_binary='ffmpeg',ffprobe_binary='ffprobe'),encoder_name='libx264')
    assert result['transitions'][1] == {'scene_id':'s1','requested':'dissolve','applied':'cut',
                                      'reason':'Outgoing source lacks continuation coverage'}
    assert result['video_frames']==60
    assert not list((tmp_path/'.editorial-work'/plan.episode_id).glob('*.handle.mp4'))


def test_date_fades_before_background_recovers_focus(tmp_path):
    source=tmp_path/'original.mp4'
    ffmpeg('-f','lavfi','-i','testsrc2=s=320x180:r=30:d=2','-c:v','libx264',source)
    design=MotionDesign(effect='date_typewriter_focus',text='2007',delay=0,hold=2)
    ass=tmp_path/'date.ass'
    write_motion_ass(design,ass,duration=2,width=320,height=180)
    filters=treatment_filters(design,duration=2,width=320,height=180,fps=30)
    output=tmp_path/'focused.mp4'
    ffmpeg('-i',source,'-vf',','.join([*filters,f'ass={ass}']),
           '-filter_threads','1','-c:v','libx264',output)
    from PIL import ImageChops
    def difference(index,region):
        a=frame(source,index=index).crop(region)
        b=frame(output,index=index).crop(region)
        return sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)
    assert difference(15,(230,10,315,43))>15  # backdrop stays blurred while date is held
    assert difference(59,(0,0,320,180))<8  # date is gone and original focus has returned
