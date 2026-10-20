"""Regression checks for animated diagram timing and browser audio delivery."""
import subprocess
import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageChops, ImageStat

from kitok.editing.motion_components import MotionDesign
from kitok.editing.production import render_editorial_plan
from kitok.editing.storyboard import EditorialPlan, EditorialScene
from kitok.media.ffprobe import probe_media


def test_real_dissolve_and_wipe_keep_every_delivery_frame_420(tmp_path):
    """The first SPS used to hide High 4:4:4 frames after an xfade cut."""
    voice = tmp_path / 'approved.m4a'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=frequency=230:duration=3', '-c:a', 'aac', str(voice)],
                   check=True, timeout=30)
    original = voice.read_bytes()
    plan = EditorialPlan(episode_id='compatible-transitions', title='Transitions',
        audio_source=voice.name, duration=3, width=640, height=360,
        audio_is_final_mix=True, scenes=[
            EditorialScene(id=f'scene{i}', start=i, end=i+1,
                intention='Delivery compatibility', spoken_claim='Illustrative fixture',
                graphic='motion', transition=transition,
                motion_design=MotionDesign(effect='chapter', text=f'Chapter {i}',
                                           preset=preset, delay=0))
            for i, (transition, preset) in enumerate([
                ('cut', 'investigation'), ('dissolve', 'archive'), ('wipe', 'signal')])])
    output = tmp_path / 'delivery.mp4'
    render_editorial_plan(plan, root=tmp_path, output=output,
        settings=SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe'),
        encoder_name='libx264')
    frames = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=pix_fmt,width,height', '-of', 'json', str(output)]))['frames']
    assert len(frames) == 90
    assert {(f['pix_fmt'], f['width'], f['height']) for f in frames} == {('yuv420p', 640, 360)}
    # Software decoding alone accepts the old mixed-format stream; inspecting
    # every frame is essential to cover browser/Media Foundation delivery.
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'],
                   check=True, capture_output=True, timeout=30)
    def audio_hash(path):
        return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
            '-map', '0:a:0', '-f', 'hash', '-hash', 'sha256', '-'])
    assert audio_hash(output) == audio_hash(voice)
    assert voice.read_bytes() == original


def test_symbolic_diagram_rejects_partial_or_foreign_nodes():
    with pytest.raises(ValueError):
        MotionDesign(effect='flow',text='Access',items=['A','B','C'],symbols=['key'])
    with pytest.raises(ValueError):
        MotionDesign(effect='question',text='Who?',symbols=['key','device','shield'])
    with pytest.raises(ValueError):
        MotionDesign(effect='flow',text='Access',items=['A','B','C'],symbols=['key','downloaded-image','shield'])


def test_real_symbolic_diagram_builds_in_sequence_and_delivers_pcm_as_aac(tmp_path):
    voice=tmp_path/'approved.wav'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=230:duration=3',str(voice)],check=True,timeout=30)
    original=voice.read_bytes()
    plan=EditorialPlan(episode_id='symbols',title='Two factors',audio_source='approved.wav',duration=3,
        width=640,height=360,audio_is_final_mix=True,scenes=[EditorialScene(id='diagram',start=0,end=3,
        intention='Explain two factors',spoken_claim='Knowledge, possession, verification',graphic='motion',
        motion_design=MotionDesign(effect='flow',text='Two factors',items=['Knowledge','Possession','Verification'],
        symbols=['key','device','shield'],preset='signal',delay=0))])
    output=tmp_path/'delivery.mp4'
    result=render_editorial_plan(plan,root=tmp_path,output=output,
        settings=SimpleNamespace(ffmpeg_binary='ffmpeg',ffprobe_binary='ffprobe'),encoder_name='libx264')
    assert probe_media(output,'ffprobe').audio_codec=='aac'
    assert result['audio_delivery']=='encoded-aac-without-normalization'
    assert voice.read_bytes()==original
    # The final node has not appeared at .25s. At 2s the same region has its
    # ring/icon/label; this checks actual decoded pixels, not ASS tag spelling.
    images=[]
    for index,stamp in enumerate((.25,2)):
        path=tmp_path/f'frame{index}.png'
        subprocess.run(['ffmpeg','-v','error','-ss',str(stamp),'-i',str(output),'-frames:v','1',str(path)],check=True,timeout=30)
        with Image.open(path) as image:
            images.append(image.convert('RGB').crop((440,130,600,290)))
    assert sum(ImageStat.Stat(ImageChops.difference(*images)).mean)>8


@pytest.mark.parametrize('source,expected',[
    ('more than twenty-two million dollars','more than $22 million'),
    ('at least seven billion pounds',''),
    ('About ninety-nine trillion euros','About €99 trillion'),
    ('one hundred twenty million dollars',''),
    ('one point five million dollars',''),
    ('-$22 million',''),
    ('$20–30 million',''),
])
def test_short_quantity_copy_keeps_qualifier_unit_and_scale(source,expected):
    from kitok.editing.motion import display_headline
    assert display_headline(source,'amount')==expected


def test_long_question_headline_keeps_original_transcript():
    from kitok.editing.motion import direct_motion
    sentence='How could one player keep making the right decision when the most important information in poker was hidden from him?'
    edit=SimpleNamespace(sections=[SimpleNamespace(section=sentence,audio_start=0,audio_end=10)])
    decision=direct_motion(edit,30)[0]
    assert decision.design.text==sentence
    assert decision.design.display_text==''


def test_weight_pounds_and_embedded_when_are_never_reinterpreted():
    from kitok.editing.motion import display_headline
    assert display_headline('twenty million pounds','amount')==''
    question='Can the investigators determine when the private accounts were accessed without authorisation?'
    assert display_headline(question,'question')==''


@pytest.mark.parametrize('effect,offset,region',[('amount',.4,(40,265,620,278)),('flow',.7,(65,140,165,245))])
def test_resumed_growth_and_opacity_match_continuous_decoded_frame(tmp_path,effect,offset,region):
    from kitok.editing.motion_components import write_motion_ass
    design=MotionDesign(effect=effect,text='$22 million' if effect=='amount' else 'Two factors',delay=0,hold=3,
        items=['Knowledge','Possession','Verification'] if effect=='flow' else [],
        symbols=['key','device','shield'] if effect=='flow' else [])
    frames=[]
    for name,elapsed,stamp in [('whole',0,offset),('resumed',offset,0)]:
        ass=tmp_path/f'{name}.ass'
        write_motion_ass(design.model_copy(update={'elapsed':elapsed}),ass,duration=3-elapsed,width=640,height=360)
        target=tmp_path/f'{name}.png'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=640x360:r=30:d=3',
            '-vf',f'ass={ass}','-ss',str(stamp),'-frames:v','1',str(target)],check=True,timeout=30)
        with Image.open(target) as image:frames.append(image.convert('RGB').crop(region))
    assert max(ImageStat.Stat(ImageChops.difference(*frames)).mean)<1


@pytest.mark.parametrize('sentence',[
    'The regulator confirmed that $22 million had not been refunded to affected players.',
    'The loss was $22 million, but only $2 million was refunded to players.',
])
def test_amount_context_does_not_invent_refund_action(sentence):
    from kitok.editing.motion import direct_motion
    edit=SimpleNamespace(sections=[SimpleNamespace(section=sentence,audio_start=0,audio_end=10)])
    decision=direct_motion(edit,30)[0]
    assert decision.design.text=='$22 million'
    assert decision.design.label==sentence
