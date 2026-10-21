"""Controlled image import, offline cue save and explicit new narration reuse."""
import base64
from io import BytesIO
import json
from pathlib import Path
import threading
from types import SimpleNamespace

from PIL import Image
import pytest

from test_simple_studio import BODY, direct_file_io
from test_studio_api import studio
from test_native_recovery import failed_job
from kitok.api.schemas import LongformRequest
from kitok.locks import GenerationBusy, generation_lock
from kitok.motion_studio import MotionStudio
from kitok.native_recovery import digest


def image_data():
    buffer = BytesIO()
    Image.new('RGB', (96, 64), 'navy').save(buffer, format='PNG')
    return buffer.getvalue()


def test_controlled_episode_upload_and_minimal_cue_preview_save(studio):
    client, _, settings = studio
    row = client.post('/api/longform/episodes').json()
    episode = settings.data_root / 'content' / 'longform' / row['id']
    data = image_data()
    upload = {'images': [{'filename': 'real-photo.png', 'data': base64.b64encode(data).decode()}]}
    first = client.post(f"/api/longform/episodes/{row['id']}/images", json=upload)
    second = client.post(f"/api/longform/episodes/{row['id']}/images", json=upload)
    assert first.status_code == second.status_code == 201
    asset = first.json()['images'][0]['asset']
    assert asset != second.json()['images'][0]['asset']
    assert (episode / asset).read_bytes() == data
    body = {**BODY, 'episode_id': row['id'], 'visual_plan': {'visual_cues': [
        {'asset': asset, 'anchor': {'phrase': 'una narración completa'}}]}}
    before = {p: digest(p) for p in settings.data_root.rglob('*') if p.is_file()}
    preview = client.post('/api/longform-preview', json=body)
    assert preview.status_code == 200, preview.text
    assert before == {p: digest(p) for p in settings.data_root.rglob('*') if p.is_file()}
    saved = client.post('/api/longform', json=body)
    assert saved.status_code == 201, saved.text
    config = json.loads(Path(saved.json()['config_path']).read_text())
    assert config['visual_root'] == f"content/longform/{row['id']}"
    assert config['visual_plan']['visual_cues'][0]['asset'] == asset
    assert saved.json()['status'] == 'draft'
    listed = client.get('/api/longform/episodes').json()
    assert len(listed[0]['images']) == 2


def test_partial_effects_do_not_require_an_optional_image_folder(studio):
    client, _, settings = studio
    body={**BODY,'visual_plan':{'visual_cues':[{'effect':'chapter','text':'La investigación',
                      'anchor':{'phrase':'una narración completa'}}]}}
    assert client.post('/api/longform-preview',json=body).status_code==200
    saved=client.post('/api/longform',json=body)
    assert saved.status_code==201,saved.text
    config=json.loads(Path(saved.json()['config_path']).read_text())
    assert 'visual_root' not in config
    assert config['visual_plan']['visual_cues'][0]['effect']=='chapter'


@pytest.mark.parametrize('image', [
    {'filename': '../private.png', 'data': base64.b64encode(image_data()).decode()},
    {'filename': 'data.png', 'data': 'not base64'},
    {'filename': 'data.png', 'data': base64.b64encode(b'not an image').decode()},
    {'filename': 'script.svg', 'data': base64.b64encode(b'<svg onload="alert(1)"></svg>').decode()},
])
def test_upload_rejects_paths_invalid_encoding_and_fake_images(studio, image):
    client, _, settings = studio
    episode = client.post('/api/longform/episodes').json()['id']
    result = client.post(f'/api/longform/episodes/{episode}/images', json={'images': [image]})
    assert result.status_code == 422
    assert list((settings.data_root / 'content' / 'longform' / episode / 'images').iterdir()) == []


def test_episode_listing_and_cues_do_not_follow_symlinks(studio):
    client, _, settings = studio
    episode = settings.data_root / 'content' / 'longform' / 'case'
    images = episode / 'real_images'
    images.mkdir(parents=True)
    (images / 'real.png').write_bytes(image_data())
    (images / 'link.png').symlink_to(images / 'real.png')
    (episode.parent / 'shortcut').symlink_to(episode)
    assert client.get('/api/longform/episodes').json() == [
        {'id': 'case', 'images': [{'asset': 'real_images/real.png', 'filename': 'real.png'}]}]
    for asset in ('real_images/link.png', '../../private.png', '/etc/passwd'):
        body = {**BODY, 'episode_id': 'case', 'visual_plan': {'visual_cues': [{'asset': asset, 'start': 0}]}}
        assert client.post('/api/longform-preview', json=body).status_code == 422
    (episode / 'images').symlink_to(images)
    assert client.post('/api/longform/episodes/case/images', json={'images': [
        {'filename': 'new.png', 'data': base64.b64encode(image_data()).decode()}]}).status_code == 422


def test_minimal_cue_rejects_missing_anchor_without_creating_draft(studio):
    client, _, settings = studio
    row = client.post('/api/longform/episodes').json()
    directory = settings.data_root / 'content' / 'longform' / row['id'] / 'images'
    (directory / 'photo.png').write_bytes(image_data())
    body = {**BODY, 'episode_id': row['id'], 'visual_plan': {'visual_cues': [
        {'asset': 'images/photo.png', 'anchor': {'phrase': 'this phrase is not spoken'}}]}}
    assert client.post('/api/longform', json=body).status_code == 422
    assert client.get('/api/longform').json() == []


def new_remount(studio, definition):
    return studio.create(LongformRequest(subject='Another montage', script=definition.item.script,
                                         keywords=definition.item.keywords, narrator_voice=definition.voice_name,
                                         music_enabled=False, music_mode='off',
                                         source_narration_id=definition.item.id))['id']


def test_new_montage_audit_and_execution_preserve_original_and_lock_both(failed_job, monkeypatch):
    service, source, narration, _ = failed_job
    original = service._read(source.item.id)
    original.update(status='succeeded', error=None)
    service._write(original)
    service.output_path(source.item.id).write_bytes(b'original-finished-video')
    target = new_remount(service, source)
    before = {p: digest(p) for p in service.root.rglob('*') if p.is_file()}
    audit = service.remount_audit(target, source.item.id)
    assert before == {p: digest(p) for p in service.root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='sin Fish'):
        service.start(target)
    with generation_lock(service.s, f'longform-{source.item.id}'):
        with pytest.raises(GenerationBusy):
            service.remount(target, source.item.id, audit['narration_sha256'], audit['audit_fingerprint'])
    entered, release = threading.Event(), threading.Event()
    def render(record, definition, stage, *, confirmed_narration):
        confirmed_narration.verify(definition, service.output_path(target))
        assert definition.item.id == target and confirmed_narration.sha256 == digest(narration)
        entered.set()
        assert release.wait(5)
        service.output_path(target).write_bytes(b'new-montage')
    monkeypatch.setattr(service, '_render', render)
    service.remount(target, source.item.id, audit['narration_sha256'], audit['audit_fingerprint'])
    try:
        assert entered.wait(5)
        for cid in (target, source.item.id):
            with pytest.raises(GenerationBusy):
                with generation_lock(service.s, f'longform-{cid}'):
                    pass
    finally:
        release.set()
    service.application._executor.shutdown(wait=True)
    assert service.detail(target)['status'] == 'succeeded'
    assert service._read(source.item.id) == original
    for path, expected in before.items():
        if path != service.records / f'{target}.json':
            assert digest(path) == expected


def test_remount_changed_script_fails_before_enqueue(failed_job):
    service, source, _, _ = failed_job
    target = new_remount(service, source)
    audit = service.remount_audit(target, source.item.id)
    (service.folder / f'{target}.txt').write_text('A different voice narration.')
    with pytest.raises(ValueError, match='guion'):
        service.remount(target, source.item.id, audit['narration_sha256'], audit['audit_fingerprint'])
    assert service.detail(target)['status'] == 'draft'


def test_active_gallery_collection_filters_without_deleting_history(tmp_path):
    gallery = tmp_path / 'outputs' / 'motion-gallery'
    for name, collection in [('old', 'legacy'), ('new', 'editor-final-20261021')]:
        folder = gallery / name
        folder.mkdir(parents=True)
        (folder / 'item.json').write_text(json.dumps({'id': name, 'kind': 'effect', 'title': name,
            'duration': 4, 'family': 'typography', 'collection': collection, 'effect_status': 'new'}))
        (folder / 'preview.mp4').write_bytes(b'video')
    service = MotionStudio(SimpleNamespace(s=SimpleNamespace(data_root=tmp_path)))
    assert len(service.list()) == 2
    (gallery / 'active.json').write_text(json.dumps({'collection': 'editor-final-20261021'}))
    assert [item['id'] for item in service.list()] == ['new']
    assert service.list()[0]['effect_status'] == 'new'
    assert service.file('old', 'preview.mp4').read_bytes() == b'video'


def test_studio_remount_loads_voice_source_after_old_image_is_removed(failed_job):
    service,source,narration,_=failed_job
    episode=service.root/'content'/'longform'/'source_episode'
    (episode/'images').mkdir(parents=True)
    image=episode/'images'/'old.png'; image.write_bytes(image_data())
    record=service._read(source.item.id)
    record['request'].update(episode_id='source_episode',visual_plan={'visual_cues':[
        {'asset':'images/old.png','start':1}]})
    record['status']='succeeded'
    service._write(record)
    body=LongformRequest.model_validate(record['request'])
    config=service._definition_values(body,source.item.id)[1]
    config['script_file']=str((service.folder/f'{source.item.id}.txt').relative_to(service.root))
    config_path=service.folder/f'{source.item.id}.json'
    config_path.write_text(json.dumps(config))
    original=service.output_path(source.item.id); original.write_bytes(b'original montage')
    image.unlink()
    # Ordinary generation still validates its images; only the voice source skips them.
    with pytest.raises(ValueError,match='existing JPG'):
        service._saved_definition(source.item.id)
    target=new_remount(service,source)
    audit=service.remount_audit(target,source.item.id)
    assert audit['narration_sha256']==digest(narration)
    assert original.read_bytes()==b'original montage'
