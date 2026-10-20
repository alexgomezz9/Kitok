from pathlib import Path
from types import SimpleNamespace
import json
import subprocess

import pytest

from kitok.editing.manifest import build_edit_manifest
from kitok.editing.motion import direct_motion, motion_plan
from kitok.editing.motion_components import MotionDesign, CATALOG, write_motion_ass
from kitok.editing.production import render_editorial_plan
from kitok.editing.storyboard import EditorialPlan, EditorialScene, EditorialAsset
from kitok.longform.models import TimelineClip, TimelineSlot
from kitok.motion_studio import MotionStudio


def test_motion_semantics_budget_diversity_and_no_false_names():
    text = 'The Hidden World is surprising. In 2007 the system changed. The transaction cost $22 million. In 2008 another change happened. What could anybody know about the hidden information?'
    edit = build_edit_manifest(text,50,['city'])
    decisions = direct_motion(edit,50)
    assert not any(d.design.effect=='identity' for d in decisions)
    assert all(d.design.text in text for d in decisions)
    assert sum(d.end-d.start for d in decisions) <= 50*.38
    assert all(b.start-a.end >= 3 for a,b in zip(decisions,decisions[1:]))
    effects=[d.design.effect for d in decisions]
    assert all(effect not in effects[max(0,i-2):i] for i,effect in enumerate(effects))
    assert all(d.timing=='estimated-sentence' for d in decisions)


def test_motion_anchors_zero_duration_provider_tokens_and_repeated_phrase():
    edit=SimpleNamespace(sections=[SimpleNamespace(section='Why this question?',audio_start=0,audio_end=1),SimpleNamespace(section='Why this question?',audio_start=4,audio_end=9)])
    words=[{'word':word,'start':start,'end':end} for word,start,end in
           [('Why',0,0.2),('this',.2,.3),('question',.3,.5),('Why',5,5),('this',5,6),('question',6,8)]]
    decisions=direct_motion(edit,30,word_alignment={'words':words})
    assert decisions[0].start==5
    assert decisions[0].timing=='provider-phrase-anchor'


@pytest.mark.parametrize('data',[
    {'effect':'keyword','text':'Visible words','emphasis':'invented'},
    {'effect':'comparison','text':'Results','items':['A','B'],'values':[1,float('nan')]},
    {'effect':'flow','text':'System','items':['A','B']},
])
def test_motion_rejects_unbacked_or_invalid_data(data):
    with pytest.raises(ValueError): MotionDesign(**data)


def test_ass_fits_every_family_and_escapes_tags(tmp_path):
    for effect,_,_ in CATALOG:
        data=dict(effect=effect,text='Why is this information hidden?',label='Editorial context',detail='An exact excerpt, with attribution.')
        if effect=='keyword': data['emphasis']='information'
        if effect=='flow': data['items']=['Source','Boundary','Account']
        if effect=='comparison':data.update(items=['Before: 10','After: 40'],values=[10,40])
        write_motion_ass(MotionDesign(**data),tmp_path/f'{effect}.ass',duration=4,width=1280,height=720)
    write_motion_ass(MotionDesign(effect='question',text=r'{\pos(0,0)} Who?'),tmp_path/'safe.ass',duration=4,width=1280,height=720)
    assert r'{\pos(0,0)}' not in (tmp_path/'safe.ass').read_text()


def test_gallery_no_traversal_or_symlinks(tmp_path):
    studio=MotionStudio(SimpleNamespace(s=SimpleNamespace(data_root=tmp_path)))
    folder=tmp_path/'outputs/motion-gallery/question'
    folder.mkdir(parents=True)
    (folder/'item.json').write_text(json.dumps({'id':'question','kind':'effect','title':'Question','duration':4,'family':'typography'}))
    (folder/'preview.mp4').write_bytes(b'video')
    assert studio.list()[0]['files']['preview.mp4'].endswith('/preview.mp4')
    with pytest.raises(ValueError):studio.file('../question','preview.mp4')
    with pytest.raises(ValueError):studio.file('question','item.json')
    (folder/'preview.mp4').unlink()
    (folder/'preview.mp4').symlink_to(tmp_path/'private.mp4')
    with pytest.raises(ValueError):studio.file('question','preview.mp4')
    assert not studio.list()


def test_motion_plan_keeps_stock_and_basic_compatibility(tmp_path):
    audio=tmp_path/'voice.wav';audio.write_bytes(b'voice')
    stock=tmp_path/'stock.mp4';stock.write_bytes(b'stock')
    clips=[TimelineClip(TimelineSlot(0,'city',0,15),1,stock,0),TimelineClip(TimelineSlot(1,'city',15,15),1,stock,0)]
    edit=build_edit_manifest('Why is this important? A quiet city scene continues.',30,['city'])
    plan=motion_plan(clips,audio,30,root=tmp_path,episode_id='sample',editing=edit)
    assert any(s.graphic=='motion' for s in plan.scenes)
    assert any(s.motion_design is None for s in plan.scenes)
    basic=motion_plan(clips,audio,30,root=tmp_path,episode_id='basic',editing=edit,style='basic')
    assert all(s.motion_design is None and s.transition=='cut' for s in basic.scenes)


def test_real_motion_render_cache_and_timed_transition(tmp_path):
    audio=tmp_path/'voice.wav'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=210:duration=4','-y',str(audio)],check=True)
    plan=EditorialPlan(episode_id='real',title='Real motion',audio_source='voice.wav',duration=4,width=640,height=360,
        audio_is_final_mix=False,scenes=[
        EditorialScene(id='one',start=0,end=2,intention='Question',spoken_claim='Why now?',graphic='motion',motion_design=MotionDesign(effect='question',text='Why now?')),
        EditorialScene(id='two',start=2,end=4,intention='Date',spoken_claim='2007',graphic='motion',transition='dissolve',motion_design=MotionDesign(effect='date',text='2007'))])
    settings=SimpleNamespace(ffmpeg_binary='ffmpeg',ffprobe_binary='ffprobe')
    result=render_editorial_plan(plan,root=tmp_path,output=tmp_path/'one.mp4',settings=settings,encoder_name='libx264')
    assert abs(result['duration']-4)<.05
    again=render_editorial_plan(plan,root=tmp_path,output=tmp_path/'two.mp4',settings=settings,encoder_name='libx264')
    assert again['reused_scenes']==['one','two']
    with pytest.raises(ValueError):render_editorial_plan(plan,root=tmp_path,output=tmp_path/'two.mp4',settings=settings,encoder_name='libx264')


def test_rejected_alignment_never_leaks_provider_anchor():
    edit=SimpleNamespace(sections=[SimpleNamespace(section='Why is this information hidden?',audio_start=0,audio_end=10)])
    invalid={'words':[{'word':'Why','start':5}]}
    decisions=direct_motion(edit,30,word_alignment=invalid)
    assert decisions[0].timing=='estimated-sentence'
    assert decisions[0].start==0


def test_percentage_and_question_alternation():
    edit=build_edit_manifest('The probability increased to 50% overnight.',20,['city'])
    assert direct_motion(edit,20)[0].design.text=='50%'
    edit=SimpleNamespace(sections=[SimpleNamespace(section='Why is the hidden information important?',audio_start=i*10,audio_end=i*10+8) for i in range(5)])
    effects=[d.design.effect for d in direct_motion(edit,60)]
    assert all(effect not in effects[max(0,i-2):i] for i,effect in enumerate(effects))


def test_fullscreen_never_restarts_at_stock_boundary(tmp_path):
    audio=tmp_path/'audio.wav';audio.write_bytes(b'audio')
    stock=tmp_path/'stock.mp4';stock.write_bytes(b'stock')
    clips=[TimelineClip(TimelineSlot(0,'city',0,5),1,stock,0),TimelineClip(TimelineSlot(1,'city',5,25),1,stock,0)]
    edit=SimpleNamespace(sections=[SimpleNamespace(section='Why would anybody keep this important information hidden?',audio_start=3,audio_end=9)])
    plan=motion_plan(clips,audio,30,root=tmp_path,episode_id='continuity',editing=edit)
    highlighted=[s for s in plan.scenes if s.motion_design]
    assert len(highlighted)==1
    assert highlighted[0].start<5<highlighted[0].end


def test_important_question_survives_nearby_stock_boundary(tmp_path):
    audio=tmp_path/'voice.wav';audio.write_bytes(b'voice')
    stock=tmp_path/'stock.mp4';stock.write_bytes(b'stock')
    clips=[TimelineClip(TimelineSlot(0,'city',0,1.4),1,stock,0),TimelineClip(TimelineSlot(1,'city',1.4,28.6),1,stock,0)]
    edit=SimpleNamespace(sections=[SimpleNamespace(section='Why is this important?',audio_start=1.53,audio_end=8)])
    plan=motion_plan(clips,audio,30,root=tmp_path,episode_id='nearby',editing=edit)
    assert any(s.graphic=='motion' for s in plan.scenes)


def test_absorbed_fragment_is_plate_not_extended_stock(tmp_path):
    audio=tmp_path/'voice.wav';audio.write_bytes(b'voice')
    stock=tmp_path/'stock.mp4';stock.write_bytes(b'stock')
    clips=[TimelineClip(TimelineSlot(0,'city',0,1.4),1,stock,0),TimelineClip(TimelineSlot(1,'city',1.4,28.6),1,stock,0)]
    edit=SimpleNamespace(sections=[SimpleNamespace(section='Why is this important?',audio_start=1.53,audio_end=8)])
    plan=motion_plan(clips,audio,30,root=tmp_path,episode_id='safe_coverage',editing=edit)
    before=plan.scenes[0];question=plan.scenes[1]
    assert before.end<=clips[0].slot.end
    assert question.graphic=='motion' and question.start==1.4
    assert question.motion_design.delay==pytest.approx(4/30)


def test_automatic_sfx_is_sparse_and_contextual():
    from kitok.editing.motion import automatic_sfx
    text='Why is this important? The cost reached $20 million. Quiet images continue. Why did it happen?'
    edit=build_edit_manifest(text,60,['city'])
    events=automatic_sfx(edit,60)
    assert len(events)<=4
    assert all(b['time']-a['time']>=15 for a,b in zip(events,events[1:]))
    assert automatic_sfx(build_edit_manifest('A quiet landscape continues without any claim.',20,['city']),20)==[]
