from PIL import Image
import pytest

from kitok.editing.visual_cues import VisualPlan, validate_visual_plan
from kitok.editing.manifest import build_edit_manifest
from kitok.editing.motion import motion_plan
from kitok.longform.models import TimelineClip, TimelineSlot


@pytest.fixture
def local_scene(tmp_path):
    image=tmp_path/'episode'/'images'/'real.png'; image.parent.mkdir(parents=True)
    Image.new('RGB',(400,500),'gray').save(image)
    narration=tmp_path/'voice.mp3'; narration.write_bytes(b'voice')
    stock=tmp_path/'stock.mp4'; stock.write_bytes(b'stock')
    script='First we see the city. Then the official document explains the case.'
    editing=build_edit_manifest(script,12.,['city'])
    clips=[TimelineClip(TimelineSlot(index=i,start=float(i*4),duration=4.,query='city'),1,stock,0.) for i in range(3)]
    return tmp_path,image,narration,script,editing,clips


def compile_scene(local_scene, cues, **kw):
    root,image,narration,script,editing,clips=local_scene
    return motion_plan(clips,narration,12.,root=root,episode_id='test',editing=editing,
                       style='basic',script=script,visual_root=image.parents[1],
                       visual_plan={'visual_cues':cues},**kw)


def test_minimal_image_cue_uses_shared_plan_preserving_stock_and_clock(local_scene):
    plan=compile_scene(local_scene,[{'asset':'images/real.png','anchor':{'phrase':'official document'}}])
    photos=[scene for scene in plan.scenes if scene.asset and scene.asset.startswith('visual_')]
    assert len(photos)==1
    assert photos[0].camera.preset=='slow_push_in'
    assert plan.fade_in==.6 and plan.fade_out==.8
    assert plan.scenes[0].start==0 and plan.scenes[-1].end==12
    assert all(abs(scene.start*30-round(scene.start*30))<1e-5 for scene in plan.scenes)
    assert all(scene.end-scene.start>=.4-1e-6 for scene in plan.scenes)
    assert plan.alignment['visual_cues'][0]['timing']=='estimated-script-words'
    assert any(scene.asset.startswith('clip_') for scene in plan.scenes if scene.asset)


def test_valid_full_transcript_alignment_anchors_image_and_foreign_alignment_is_estimated(local_scene):
    root,image,narration,script,editing,clips=local_scene
    words={'words':[{'word':word,'start':i*.8,'end':(i+1)*.8} for i,word in enumerate(script.split())]}
    cue={'asset':'images/real.png','anchor':{'phrase':'official document'},'duration':2}
    plan=compile_scene(local_scene,[cue],word_alignment=words)
    assert plan.alignment['visual_cues'][0]['timing']=='provider-phrase-anchor'
    assert plan.alignment['visual_cues'][0]['start']==pytest.approx(5.6)
    words['words'][0]['word']='foreign'
    plan=compile_scene(local_scene,[cue],word_alignment=words)
    assert plan.alignment['visual_cues'][0]['timing']=='estimated-script-words'


def test_default_durations_fit_next_cue_and_explicit_overlap_fails(local_scene):
    cues=[{'asset':'images/real.png','start':2},{'asset':'images/real.png','start':5}]
    plan=compile_scene(local_scene,cues)
    assert plan.alignment['visual_cues'][0]['end']==5
    cues[0]['duration']=4
    with pytest.raises(ValueError,match='overlap'):
        compile_scene(local_scene,cues)


@pytest.mark.parametrize('bad', [
    {'asset':'../real.png','start':1},
    {'asset':'images/missing.png','start':1},
    {'asset':'images/real.png','anchor':{'phrase':'not spoken'}},
    {'asset':'images/real.png','start':1,'anchor':{'phrase':'city'}},
    {'asset':'images/real.png','start':1,'camera':'parallax'},
    {'asset':'images/real.png','start':1,'effect':'comparison','text':'unfounded'},
])
def test_invalid_local_inputs_rejected_before_render(local_scene,bad):
    root,image,_,script,_,_=local_scene
    with pytest.raises(ValueError):
        validate_visual_plan({'visual_cues':[bad]},script,root,image.parents[1])


def test_symlink_images_and_corrupted_decodes_rejected(local_scene):
    root,image,_,script,_,_=local_scene
    link=image.with_name('link.png'); link.symlink_to(image)
    with pytest.raises(ValueError,match='symlink'):
        validate_visual_plan({'visual_cues':[{'asset':'images/link.png','start':1}]},script,root,image.parents[1])
    image.write_bytes(b'broken')
    with pytest.raises(ValueError,match='decode'):
        validate_visual_plan({'visual_cues':[{'asset':'images/real.png','start':1}]},script,root,image.parents[1])


def test_invalid_visuals_fail_before_fish_or_stock_calls(local_scene):
    from types import SimpleNamespace
    from kitok.rendering.native import NativeLongformRenderer
    root,image,narration,script,_,_=local_scene
    def forbidden(*args,**kwargs):
        pytest.fail('Invalid local visual must stop before providers')
    renderer=NativeLongformRenderer(SimpleNamespace(data_root=root),SimpleNamespace(search_videos=forbidden),
                                    SimpleNamespace(),output_path=root/'new.mp4',fish_factory=forbidden)
    definition=SimpleNamespace(item=SimpleNamespace(script=script),mounting_style='basic',music_mode='off',music_enabled=False,
                               visual_plan={'visual_cues':[{'asset':'images/missing.png','anchor':{'phrase':'city'}}]},
                               visual_root=image.parents[1])
    with pytest.raises(ValueError,match='existing'):
        renderer.render(definition)
    assert not (root/'.native-work').exists()


def test_visual_root_parent_traversal_and_missing_occurrence_are_rejected(local_scene):
    root,image,_,script,_,_=local_scene
    with pytest.raises(ValueError,match='workspace'):
        validate_visual_plan({'visual_cues':[{'asset':'real.png','start':1}]},script,root,image.parent/'..')
    with pytest.raises(ValueError,match='not found'):
        validate_visual_plan({'visual_cues':[{'asset':'images/real.png','anchor':{'phrase':'city','occurrence':1}}]},
                             script,root,image.parents[1])


def test_effect_only_stock_overlay_preserves_boundaries_and_elapsed(local_scene):
    cue={'anchor':{'phrase':'city'},'effect':'amount','text':'$20 million','duration':5}
    plan=compile_scene(local_scene,[cue])
    active=[scene for scene in plan.scenes if scene.motion_design]
    assert len(active)>1
    assert all(scene.asset.startswith('clip_') and scene.graphic is None for scene in active)
    assert active[0].motion_design.elapsed==0
    assert active[1].motion_design.elapsed==pytest.approx(active[1].start-active[0].start)
    assert not any(key.startswith('visual_') for key in plan.assets)
    assert any(scene.camera and scene.camera.preset!='static' for scene in plan.scenes)


def test_effect_only_black_plate_and_requested_timing_record(local_scene):
    plan=compile_scene(local_scene,[{'start':4.1,'duration':2,'background':'black',
                                    'effect':'chapter','text':'La investigación'}])
    scene=next(scene for scene in plan.scenes if scene.graphic=='motion')
    assert scene.graphic_data=={'background':'black'} and scene.asset is None
    receipt=plan.alignment['visual_cues'][0]
    assert receipt['requested_anchor_seconds']==4.1
    assert receipt['requested_duration']==2
    assert receipt['boundary_adjustment'] is True
    assert receipt['start']==4


def test_duplicate_phrase_cues_fail_preflight_and_default_cameras_vary(local_scene):
    root,image,_,script,_,_=local_scene
    with pytest.raises(ValueError,match='same spoken anchor'):
        validate_visual_plan({'visual_cues':[{'asset':'images/real.png','anchor':{'phrase':'city'}},
                                             {'effect':'chapter','text':'City','anchor':{'phrase':'city'}}]},
                             script,root,image.parents[1])
    plan=compile_scene(local_scene,[{'asset':'images/real.png','start':1,'duration':2},
                                   {'asset':'images/real.png','start':6,'duration':2}])
    cameras=[scene.camera.preset for scene in plan.scenes if scene.asset and scene.asset.startswith('visual_')]
    assert len(set(cameras))==2


def test_remount_marker_blocks_new_fish_even_without_confirmation(tmp_path):
    from types import SimpleNamespace
    from kitok.rendering.native import NativeLongformRenderer, NativeRenderError
    renderer=NativeLongformRenderer(SimpleNamespace(),SimpleNamespace(),SimpleNamespace(),output_path=tmp_path/'new.mp4')
    with pytest.raises(NativeRenderError,match='synthesis is disabled'):
        renderer.render(SimpleNamespace(source_narration_id='original'))


@pytest.mark.parametrize('start,duration',[(3.7,2.),(4.1,2.),(2.,2.2),(2.,1.7),(3.9,4.2)])
def test_stock_overlay_edges_keep_whole_stock_scenes_and_original_effect_clock(local_scene,start,duration):
    cue={'start':start,'duration':duration,'effect':'amount','text':'20 million'}
    plan=compile_scene(local_scene,[cue])
    timing=plan.alignment['visual_cues'][0]
    assert timing['requested_anchor_seconds']==start
    assert timing['requested_duration']==duration
    assert all(scene.end-scene.start>=.4-1e-6 for scene in plan.scenes)
    assert {4.,8.}.issubset({scene.end for scene in plan.scenes})
    active=[scene for scene in plan.scenes if scene.motion_design]
    for scene in active:
        design=scene.motion_design
        assert scene.start+design.delay-design.elapsed==pytest.approx(start)
        assert design.hold==pytest.approx(duration)
        i=int(scene.asset.split('_')[-1])
        assert scene.source_start==pytest.approx(scene.start-4*i)


def test_overlay_crossing_multiple_stock_cuts_preserves_explicit_delay(local_scene):
    cue={'start':.2,'duration':10.,'effect':'amount','text':'20 million','motion_data':{'delay':.6}}
    plan=compile_scene(local_scene,[cue])
    active=[scene for scene in plan.scenes if scene.motion_design]
    assert len(active)>=3
    for scene in active:
        design=scene.motion_design
        assert scene.start+design.delay-design.elapsed==pytest.approx(.8)
        assert design.hold==pytest.approx(9.4)
        assert scene.start+design.delay+design.hold-design.elapsed==pytest.approx(10.2)
    assert active[1].motion_design.elapsed==4


@pytest.mark.parametrize('effect',['dissolve','wipe'])
def test_transition_names_are_rejected_as_visual_effects_before_render(local_scene,effect):
    root,image,_,script,_,_=local_scene
    with pytest.raises(ValueError,match='use the transition field'):
        validate_visual_plan({'visual_cues':[{'asset':'images/real.png','start':1,'effect':effect}]},
                             script,root,image.parents[1])


def test_visual_plan_with_legacy_music_is_rejected_before_paid_synthesis(tmp_path):
    from types import SimpleNamespace
    from kitok.rendering.native import NativeLongformRenderer, NativeRenderError
    renderer=NativeLongformRenderer(SimpleNamespace(data_root=tmp_path),SimpleNamespace(),SimpleNamespace(),
                                    output_path=tmp_path/'new.mp4')
    definition=SimpleNamespace(visual_plan={'visual_cues':[]},music_mode=None,music_enabled=True,
                               mounting_style='basic')
    with pytest.raises(NativeRenderError,match='explicit music_mode'):
        renderer.render(definition)


@pytest.mark.parametrize('second_start',[1.,1.2,1.39])
def test_duplicate_or_too_close_starts_fail_before_fish_even_without_durations(local_scene,second_start):
    from types import SimpleNamespace
    from kitok.rendering.native import NativeLongformRenderer
    root,image,_,script,_,_=local_scene
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append('paid-call')
        pytest.fail('Static cue validation must happen before Fish')
    definition=SimpleNamespace(item=SimpleNamespace(script=script),mounting_style='basic',music_mode='off',
                               music_enabled=False,visual_root=image.parents[1],
                               visual_plan={'visual_cues':[{'asset':'images/real.png','start':1},
                                                          {'asset':'images/real.png','start':second_start}]})
    renderer=NativeLongformRenderer(SimpleNamespace(data_root=root),SimpleNamespace(),SimpleNamespace(),
                                    output_path=root/'new.mp4',fish_factory=forbidden)
    with pytest.raises(ValueError,match='0.4s between explicit starts'):
        renderer.render(definition)
    assert calls==[] and not (root/'.native-work').exists()


def test_effect_delay_and_hold_stay_inside_the_reserved_cue(local_scene):
    root,image,_,script,_,_=local_scene
    with pytest.raises(ValueError,match='hold must fit'):
        validate_visual_plan({'visual_cues':[{'start':1,'duration':3,'effect':'amount',
            'text':'20 million','motion_data':{'delay':1,'hold':3}}]},script,root)
    # The minimum cue duration is useful without having to override the
    # MotionDesign standalone default delay.
    assert validate_visual_plan({'visual_cues':[{'start':1,'duration':.4,
        'effect':'amount','text':'20 million'}]},script,root)
    plan=compile_scene(local_scene,[{'start':3.7,'duration':2,'effect':'amount',
                                   'text':'20 million','motion_data':{'hold':None}}])
    active=[scene for scene in plan.scenes if scene.motion_design]
    assert active and all(scene.motion_design.hold==2 for scene in active)
