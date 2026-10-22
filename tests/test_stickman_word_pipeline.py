"""Public recovery flow: supplied word-aligned assets, no manual SRT repair."""
import json

import pytest
from PIL import Image

from test_stickman_pipeline import setup_episode
from kitok.youtube_stickman_es.files import digest
from kitok.youtube_stickman_es.pipeline import execute, current


def supplied(setup_episode):
    root, folder, settings = setup_episode
    script = (folder/'guion_final.txt').read_text()
    words = script.split()
    alignment = {'method':'fish_provider_timestamps','words':[
        {'word':word,'start':.1 + i*.75,'end':.6 + i*.75} for i,word in enumerate(words)]}
    (folder/'voz.alignment.json').write_text(json.dumps(alignment))
    spans = []
    for i, text in enumerate(('Primera señal de prueba.', 'Segunda señal de prueba.')):
        image = f'imagenes/escena_{i+1:03d}.png'
        Image.new('RGB',(1280,720),('tan','ivory')[i]).save(folder/image)
        start = script.index(text)
        spans.append({'id':f'original_{i}','source_char_start':start,'source_char_end':start+len(text),
            'narration':text,'image_file':image,'image_sha256':digest(folder/image),
            'visual_description':'An original diagnostic illustration for this exact narrated span.',
            'scene_prompt':'An original technical diagnostic illustration with an ivory background and a unique simple scene.'})
    (folder/'plan_visual.json').write_text(json.dumps({'script_source':'guion_final.txt',
        'script_sha256':digest(folder/'guion_final.txt'),'scenes':spans}))
    return root,folder,settings


def test_revision_reuses_original_names_and_spans_without_fake_review(setup_episode,monkeypatch):
    root,folder,settings = supplied(setup_episode)
    from kitok.youtube_stickman_es import audio
    monkeypatch.setattr(audio,'FishVoiceClient',lambda *a,**k:pytest.fail('No provider'))
    before = {p.relative_to(folder).as_posix():digest(p) for p in folder.rglob('*') if p.is_file()}
    result = execute(root,folder,'prepare',settings=settings,revision='aligned',reuse_images=True)
    revised = folder/'revisiones/aligned'
    plan,config,batch = current(revised)
    assert [s.image_file for s in plan.scenes] == ['imagenes/escena_001.png','imagenes/escena_002.png']
    assert [s.narration for s in plan.scenes] == ['Primera señal de prueba.','Segunda señal de prueba.']
    assert plan.scenes[1].start == pytest.approx(3.1)
    assert plan.timing_method == 'fish_provider_word_timestamps_full_transcript'
    assert result['images']['assembly_authorized'] and result['images']['render_images_ready']
    assert not result['images']['style_approved']
    assert not any(r['reviewed'] for r in result['images']['jobs'])
    assert all(digest(folder/name)==sha for name,sha in before.items())
    assert execute(root,folder,'prepare',settings=settings,revision='aligned',reuse_images=True)==result
    data = json.loads((revised/'voz.alignment.json').read_text())
    data['words'][0]['start'] = .2
    (revised/'voz.alignment.json').write_text(json.dumps(data))
    with pytest.raises(ValueError,match='changed'):
        current(revised)
    with pytest.raises(ValueError,match='changed'):
        execute(root,folder,'prepare',settings=settings,revision='aligned',reuse_images=True)


def test_provided_authorization_pins_images_and_never_overrides_attempts(setup_episode):
    root,folder,settings = supplied(setup_episode)
    execute(root,folder,'prepare',settings=settings,reuse_images=True)
    _,_,batch = current(folder)
    with pytest.raises(ValueError,match='immutable'):
        batch.reject(batch.plan.scenes[0].id,reason='Use another illustration')
    path = folder/'imagenes/escena_001.png'
    Image.new('RGB',(1280,720),'red').save(path)
    with pytest.raises(ValueError,match='changed'):
        batch.status()


def test_status_revision_does_not_create_a_snapshot(setup_episode):
    root,folder,settings = setup_episode
    with pytest.raises(ValueError,match='existing episode'):
        execute(root,folder,'status',settings=settings,revision='missing')
    assert not (folder/'revisiones').exists()


def test_real_native_recovery_uses_supplied_images_without_generation(setup_episode,monkeypatch):
    root,folder,settings = supplied(setup_episode)
    from kitok.youtube_stickman_es import audio
    monkeypatch.setattr(audio,'FishVoiceClient',lambda *a,**k:pytest.fail('No provider'))
    before = {p.name:digest(p) for p in (folder/'imagenes').iterdir()}
    report = execute(root,folder,'produce',settings=settings,revision='aligned',reuse_images=True)
    assert report['technical_status']=='passed'
    assert report['render']['provider_requests']==0
    assert report['render']['video_frames']==180
    assert report['production_status']=='thumbnail_images_required'
    assert all(digest(folder/'imagenes'/name)==sha for name,sha in before.items())
    assert not (folder/'video_final.mp4').exists()
    assert (folder/'revisiones/aligned/video_final.mp4').exists()


def test_revision_accepts_windows_bom_configuration(setup_episode):
    root,folder,settings = supplied(setup_episode)
    path=folder/'configuracion.json'
    path.write_bytes(b'\xef\xbb\xbf'+path.read_bytes())
    result=execute(root,folder,'prepare',settings=settings,revision='windows',reuse_images=True)
    assert result['images']['render_images_ready']
    assert (folder/'revisiones/windows/configuracion.json').read_bytes()==path.read_bytes()


def test_word_plan_draft_can_be_completed_without_changing_timing_receipt(setup_episode):
    root,folder,settings=supplied(setup_episode)
    first=execute(root,folder,'prepare',settings=settings)
    assert first['status']=='visual_direction_required'
    before=(folder/'.stickman/word_timing.borrador.json').read_bytes()
    directions=json.loads((folder/'direcciones_plantilla.json').read_text())
    for row in directions:
        row.update(visual_description='An original diagnostic figure points toward its exact signal.',
                   scene_prompt='An original diagnostic illustration shows a stick figure inspecting the exact signal, no text.')
    (folder/'direccion_visual.json').write_text(json.dumps(directions))
    second=execute(root,folder,'prepare',settings=settings)
    assert second['status']=='images_required'
    assert (folder/'.stickman/word_timing.borrador.json').read_bytes()==before
    assert current(folder)[0].direction_complete
    assert execute(root,folder,'prepare',settings=settings)==second
