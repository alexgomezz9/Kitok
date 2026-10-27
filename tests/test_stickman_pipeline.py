"""The actual public execution interface, including restart and real Native render."""
import json
import math
from pathlib import Path
import struct
import wave

from PIL import Image,ImageDraw
import pytest

from kitok.config import Settings
from kitok.editing.storyboard import EditorialPlan
from kitok.media.ffprobe import probe_video_clock
from kitok.youtube_stickman_es.files import digest,episode_lock
from kitok.youtube_stickman_es.pipeline import execute,current


@pytest.fixture
def setup_episode(tmp_path):
    folder=tmp_path/'episode'
    settings=Settings(_env_file=None,data_root=tmp_path,ready_dir=tmp_path/'ready')
    execute(tmp_path,folder,'init',settings=settings)
    (folder/'guion_final.txt').write_text('Primera señal de prueba. Segunda señal de prueba.')
    (folder/'titulo.txt').write_text('Título de prueba aprobado\n')
    (folder/'voz.srt').write_text('1\n00:00:00,100 --> 00:00:02,900\nPrimera señal de prueba.\n\n'
                                 '2\n00:00:03,100 --> 00:00:05,900\nSegunda señal de prueba.\n')
    with wave.open(str(folder/'voz.mp3'),'wb') as sound:
        sound.setparams((1,2,8000,0,'NONE','not compressed'))
        sound.writeframes(b''.join(struct.pack('<h',round(2000*math.sin(2*math.pi*220*n/8000))) for n in range(48000)))
    Image.new('RGB',(1280,720),'ivory').save(folder/'referencias/frame.png')
    config=json.loads((folder/'configuracion.json').read_text())
    config['voice']['transcript_verification']='off'  # Synthetic tone fixture has no spoken words.
    config.update(target_scene_seconds=3,music={'mode':'off'},
                  references=[{'path':'referencias/frame.png','role':'interior','notes':'Technical fixture only'}])
    (folder/'configuracion.json').write_text(json.dumps(config))
    return tmp_path,folder,settings


def directed(setup_episode):
    root,folder,settings=setup_episode
    result=execute(root,folder,'prepare',settings=settings)
    assert result['status']=='visual_direction_required'
    directions=json.loads((folder/'direcciones_plantilla.json').read_text())
    for i,row in enumerate(directions):
        row.update(visual_description=f'A technical diagnostic figure points toward test shape {i}.',
                   scene_prompt=f'A clean original diagnostic stick figure points toward shape {i}; no text, light background.')
    (folder/'direccion_visual.json').write_text(json.dumps(directions))
    return execute(root,folder,'prepare',settings=settings)


def accept_fixture(setup_episode, *, thumbs=False):
    root,folder,settings=setup_episode
    result=directed(setup_episode)
    identifiers=result['images']['sample_ids']
    for i,ident in enumerate(identifiers):
        source=folder/f'fixture{i}.png'
        im=Image.new('RGB',(1280,720),'#faf9f3');draw=ImageDraw.Draw(im)
        draw.rectangle((200+i*100,200,500+i*100,500),outline='#263a48',width=12);im.save(source)
        request=execute(root,folder,'request',settings=settings,image_id=ident)
        execute(root,folder,'import-image',settings=settings,image_id=ident,source=source,
                attempt_id=request['attempt_id'],reviewed=True,source_kind='technical_fixture')
    execute(root,folder,'approve-style',settings=settings,reviewer='technical fixture only, not channel style')
    if thumbs:
        for i,key in enumerate('ABC'):
            source=folder/f'thumb{i}.png'
            Image.new('RGB',(1280,720),('#e2c47d','#85b0bc','#adc79e')[i]).save(source)
            request=execute(root,folder,'request',settings=settings,image_id='thumb_'+key)
            execute(root,folder,'import-image',settings=settings,image_id='thumb_'+key,source=source,
                    attempt_id=request['attempt_id'],reviewed=True,source_kind='technical_fixture')


def test_restart_preserves_numeric_model_identity_and_all_completed_images(setup_episode):
    root,folder,settings=setup_episode
    accept_fixture(setup_episode)
    plan,config,batch=current(folder)
    assert digest(plan.model_dump())==digest(type(plan).model_validate_json(plan.model_dump_json()).model_dump())
    image_before={p.name:digest(p) for p in (folder/'imagenes').iterdir()}
    result=execute(root,folder,'prepare',settings=settings)
    assert result['images']['render_images_ready'] and result['images']['style_approved']
    assert result['images']['completed']==2
    assert image_before=={p.name:digest(p) for p in (folder/'imagenes').iterdir()}


def test_prepare_has_no_imagegen_or_paid_synthesis_without_explicit_command(setup_episode,monkeypatch):
    from kitok.youtube_stickman_es import audio
    root,folder,settings=setup_episode
    monkeypatch.setattr(audio,'FishVoiceClient',lambda *a,**k:pytest.fail('No paid call'))
    before=(folder/'guion_final.txt').read_bytes()
    result=execute(root,folder,'produce',settings=settings)
    assert result['status']=='visual_direction_required'
    assert not (folder/'video_final.mp4').exists()
    assert (folder/'guion_final.txt').read_bytes()==before


def test_public_lock_rejects_duplicate_operations(setup_episode):
    root,folder,settings=setup_episode
    with episode_lock(folder):
        with pytest.raises(ValueError,match='already being processed'):
            execute(root,folder,'prepare',settings=settings)


def test_next_image_request_and_status_recover_active_attempt_token(setup_episode):
    root,folder,settings=setup_episode
    assert execute(root,folder,'status',settings=settings)['status']=='preparation_required'
    execute(root,folder,'prepare',settings=settings)
    assert execute(root,folder,'status',settings=settings)['status']=='visual_direction_required'
    directions=json.loads((folder/'direcciones_plantilla.json').read_text())
    for row in directions:
        row.update(visual_description='A diagnostic stick figure inspects the signal.',
                   scene_prompt='An original diagnostic stick figure inspects a simple signal, clean light background, no text.')
    (folder/'direccion_visual.json').write_text(json.dumps(directions))
    execute(root,folder,'prepare',settings=settings)
    request=execute(root,folder,'request-next',settings=settings)
    status=execute(root,folder,'status',settings=settings)
    row=next(row for row in status['images']['jobs'] if row['id']==request['id'])
    assert row['attempt_id']==request['attempt_id'] and not row['eligible']
    assert request['tool']=='image_gen.imagegen' and request['arguments']['transparent_background'] is False


def test_render_requires_assets_and_style_without_synthesizing(setup_episode):
    root,folder,settings=setup_episode
    directed(setup_episode)
    with pytest.raises(ValueError,match='Approve the style'):
        execute(root,folder,'render',settings=settings)
    assert not (folder/'video_final.mp4').exists()


def test_real_shared_native_render_resume_and_rerender(setup_episode,monkeypatch):
    root,folder,settings=setup_episode
    accept_fixture(setup_episode,thumbs=True)
    before={p.name:digest(p) for p in (folder/'imagenes').iterdir()}
    stages=[]
    report=execute(root,folder,'produce',settings=settings,on_stage=stages.append)
    assert any('Plano 1/2' in s for s in stages)
    assert any('Plano 2/2: renderizado' in s for s in stages)
    assert any('Ensamblaje:' in s for s in stages)
    assert any('Calidad:' in s for s in stages)
    assert report['technical_status']=='passed'
    assert report['packaging']['thumbnails_ready']
    assert report['render']['provider_requests']==0
    assert report['render']['video_frames']==180
    assert probe_video_clock(folder/'video_final.mp4').frames==180
    timeline=EditorialPlan.load(folder/'montaje.json')
    assert timeline.transition_duration==.4
    assert all(s.image_fit=='cover' for s in timeline.scenes)
    workspace=folder/'.editorial-work'/timeline.episode_id
    assert probe_video_clock(workspace/(timeline.scenes[0].id+'.handle.mp4')).frames==12
    original=digest(folder/'video_final.mp4')
    # Simulate a crash after renderer promotion and before outer QA publication.
    (folder/'qa.json').unlink()
    stages.clear()
    resumed=execute(root,folder,'resume',settings=settings,on_stage=stages.append)
    assert any('Vídeo existente:' in s for s in stages)
    assert resumed['technical_status']=='passed' and digest(folder/'video_final.mp4')==original
    rerender=execute(root,folder,'render',settings=settings,revision='v2')
    assert len(rerender['render']['reused_scenes'])==2
    assert before=={p.name:digest(p) for p in (folder/'imagenes').iterdir()}
    assert (folder/'video_final.mp4').is_file() and (folder/'video_final__v2.mp4').is_file()
    assert digest(folder/'video_final.mp4')==original
    qa=json.loads((folder/'qa.json').read_text())
    assert qa['decoded_frames']==180 and qa['max_pts_error']<1e-5
    assert qa['loudness']['true_peak_dbtp']<=-1.5


def test_changed_title_or_image_blocks_instead_of_overwriting(setup_episode):
    root,folder,settings=setup_episode
    accept_fixture(setup_episode)
    (folder/'titulo.txt').write_text('Un título cambiado sin revisión')
    with pytest.raises(ValueError,match='approved title'):
        execute(root,folder,'status',settings=settings)


def test_corrected_thumbnail_keeps_previous_composition_and_resumes_after_composition_crash(setup_episode):
    root,folder,settings=setup_episode
    accept_fixture(setup_episode,thumbs=True)
    execute(root,folder,'package',settings=settings)
    first=digest(folder/'miniaturas/miniatura_A.png')
    other=digest(folder/'miniaturas/miniatura_B.png')
    execute(root,folder,'reject',settings=settings,image_id='thumb_A',reason='Improve visual focus')
    execute(root,folder,'retry',settings=settings,image_id='thumb_A',reason='Explicit next attempt')
    claim=execute(root,folder,'request',settings=settings,image_id='thumb_A')
    source=folder/'corrected.png'
    Image.new('RGB',(1280,720),'#aa8866').save(source)
    execute(root,folder,'import-image',settings=settings,image_id='thumb_A',source=source,
            attempt_id=claim['attempt_id'],reviewed=True,source_kind='technical_fixture')
    result=execute(root,folder,'package',settings=settings)
    assert result['thumbnails_ready']
    assert digest(folder/'miniaturas/miniatura_A.png')!=first
    assert digest(folder/'miniaturas/miniatura_B.png')==other
    archive=list((folder/'.stickman/thumbnail-history').glob('miniatura_A-*.png'))
    assert len(archive)==1 and digest(archive[0])==first
    receipt=folder/'.stickman/thumbnail_A.json'
    value=json.loads(receipt.read_text());value['status']='planned';value.pop('output_sha256')
    receipt.write_text(json.dumps(value))
    assert execute(root,folder,'package',settings=settings)['thumbnails_ready']
