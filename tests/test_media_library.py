import io
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import wave

import httpx
from PIL import Image
import pytest

from kitok.config import Settings
from kitok.media_library import CommonsLibrary, local_records, register_cached_pexels, select_asset, validate_record_license


def fixture(tmp_path, license='CC BY-SA 2.0', url='https://upload.wikimedia.org/wikipedia/commons/photo.jpg'):
    buffer=io.BytesIO();Image.new('RGB',(320,200),'blue').save(buffer,format='JPEG')
    body=buffer.getvalue();calls=[]
    def handler(request):
        calls.append(request)
        if request.url.host=='commons.wikimedia.org':
            return httpx.Response(200,json={'query':{'pages':[{'pageid':42,'imageinfo':[{
                'url':url,'mime':'image/jpeg','size':len(body),'width':320,'height':200,
                'extmetadata':{'LicenseShortName':{'value':license},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/2.0/'},'Artist':{'value':'<a>Named author</a>'}}}]}]}})
        return httpx.Response(200,content=body)
    return CommonsLibrary(Settings(_env_file=None,data_root=tmp_path),client=httpx.Client(transport=httpx.MockTransport(handler))),calls


def test_fetch_records_rights_hash_entities_and_reuses_without_another_media_download(tmp_path):
    library,calls=fixture(tmp_path)
    one=library.fetch('File:Specific person.jpg',entities=['Specific person'],roles=['portrait'],usage='identity')
    two=library.fetch('File:Specific person.jpg',entities=['Specific person'],roles=['portrait'],usage='identity')
    assert one['sha256']==two['sha256'] and one['share_alike'] is True
    assert one['author']=='Named author' and one['content_id']=='unknown'
    assert sum(r.url.host=='upload.wikimedia.org' for r in calls)==1
    selected=select_asset(library.records(),entity='Specific person',role='portrait')
    assert selected['status']=='selected'
    assert select_asset(library.records(),entity='Someone else',role='portrait')['status']=='missing'


@pytest.mark.parametrize('license',['CC BY-NC 4.0','Unknown','All rights reserved','Pexels'])
def test_unclear_or_noncommercial_license_never_downloads(tmp_path,license):
    library,calls=fixture(tmp_path,license=license)
    with pytest.raises(ValueError,match='commercial reuse'):
        library.fetch('File:Photo.jpg',entities=['Actor'],roles=['portrait'])
    assert len(calls)==1 and library.records()==[]


def test_image_download_cannot_redirect_to_other_hosts(tmp_path):
    library,calls=fixture(tmp_path,url='https://127.0.0.1/private')
    with pytest.raises(ValueError,match='Wikimedia host'):
        library.fetch('File:Photo.jpg',entities=['Actor'],roles=['portrait'])
    assert len(calls)==1


def test_license_name_cannot_override_noncommercial_url(tmp_path):
    library,calls=fixture(tmp_path,license='CC BY 4.0')
    # The fixture URL is by-sa/2.0: any conflicting license evidence is rejected.
    with pytest.raises(ValueError,match='contradict'):
        library.fetch('File:Photo.jpg',entities=['Actor'],roles=['portrait'])
    assert len(calls)==1


def test_injected_follow_redirect_client_never_reaches_private_host(tmp_path):
    library,_=fixture(tmp_path)
    original=library.client
    requests=[]
    def handler(request):
        requests.append(request)
        if request.url.host=='upload.wikimedia.org':
            return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
        if request.url.host=='127.0.0.1':pytest.fail('Redirect reached a private host')
        return original.send(request)
    library.client=httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=True)
    with pytest.raises(httpx.HTTPStatusError):
        library.fetch('File:Photo.jpg',entities=['Actor'],roles=['portrait'])
    assert [r.url.host for r in requests]==['commons.wikimedia.org','upload.wikimedia.org']


def test_library_rejects_jpeg_that_has_headers_but_cannot_fully_decode(tmp_path):
    library,_=fixture(tmp_path)
    original=library.client
    def handler(request):
        response=original.send(request)
        if request.url.host=='upload.wikimedia.org':
            return httpx.Response(200,content=response.content[:-50])
        return response
    library.client=httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(OSError,match='truncated'):
        library.fetch('File:Photo.jpg',entities=['Actor'],roles=['portrait'])
    assert library.records()==[]


@pytest.fixture
def cached_pexels(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Cache registration measures a real local video')
    folder = tmp_path / 'cache/pexels/videos'
    folder.mkdir(parents=True)
    video = folder / '42.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=blue:s=320x180:r=24:d=3', '-an', '-c:v', 'libx264',
                    '-preset', 'ultrafast', str(video)], check=True, capture_output=True, timeout=15)
    url = 'https://videos.pexels.com/video-files/42/42-hd_320_180_24fps.mp4'
    metadata = {'asset_id': 42, 'duration': 3, 'width': 320, 'height': 180, 'fps': 24,
                'url': url, 'local_cache_path': str(video)}
    (folder / '42.json').write_text(json.dumps(metadata))
    searches = tmp_path / 'cache/pexels/searches'
    searches.mkdir()
    search = {'assets': [{'asset_id': 42, 'page_url': 'https://www.pexels.com/video/typing-on-laptop-42/',
                          'variants': [{'url': url, 'width': 320, 'height': 180}]}]}
    (searches / 'search.json').write_text(json.dumps(search))
    return Settings(_env_file=None, data_root=tmp_path), video, folder / '42.json', searches / 'search.json'


def test_registers_existing_pexels_without_http_or_modifying_cached_media(cached_pexels, monkeypatch):
    settings, video, metadata, search = cached_pexels
    original = {p: p.read_bytes() for p in (video, metadata, search)}
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('Offline registration constructed an HTTP client'))
    first = register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    second = register_cached_pexels(settings, 42, entities=['computer'], roles=['context'])
    assert first['license'] == 'Pexels' and first['author'] == 'unknown'
    assert first['license_url'] == 'https://www.pexels.com/license/'
    assert first['usage'] == 'illustration' and first['content_id'] == 'unknown'
    assert second['entities'] == ['typing', 'computer'] and second['roles'] == ['stock', 'context']
    assert {p: p.read_bytes() for p in original} == original
    assert local_records(settings.data_root) == [second]
    assert select_asset([second], entity='typing', role='stock')['status'] == 'selected'
    assert (settings.data_root / 'cache/media-library/source-pexels-42.json').is_file()


@pytest.mark.parametrize('page', [
    'https://www.pexels.com/video/wrong-43/', 'https://evil.test/video/typing-42/',
    'https://www.pexels.com.evil.test/video/typing-42/', 'http://www.pexels.com/video/typing-42/',
    'https://user:password@www.pexels.com/video/typing-42/',
    'https://www.pexels.com/video/%2e%2e-42/', 'https://www.pexels.com/video/typing-42/?redirect=evil',
    'https://www.pexels.com/video/typing-42/#fragment',
])
def test_pexels_registration_requires_exact_official_cached_source_page(cached_pexels, page):
    settings, _, _, search = cached_pexels
    payload = json.loads(search.read_text())
    payload['assets'][0]['page_url'] = page
    search.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='exact cached video ID'):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    assert local_records(settings.data_root) == []


@pytest.mark.parametrize('mutation', ['id', 'dimensions', 'duration', 'variant', 'missing_search', 'missing_url', 'foreign_url'])
def test_pexels_registration_rejects_mismatched_cache_receipts(cached_pexels, mutation):
    settings, _, metadata, search = cached_pexels
    payload = json.loads(metadata.read_text())
    if mutation == 'id':
        payload['asset_id'] = 43
    elif mutation == 'dimensions':
        payload['width'] = 1920
    elif mutation == 'duration':
        payload['duration'] = 90
    elif mutation == 'variant':
        payload['url'] = 'https://videos.pexels.com/another.mp4'
    elif mutation == 'missing_url':
        payload.pop('url')
    elif mutation == 'foreign_url':
        payload['url'] = 'https://evil.test/video-files/42/42-hd_320_180_24fps.mp4'
    else:
        search.unlink()
    metadata.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    assert local_records(settings.data_root) == []


@pytest.mark.parametrize('role', ['identity', 'portrait', 'document', 'evidence', 'historical'])
def test_pexels_cannot_be_registered_as_identity_or_historical_evidence(cached_pexels, role):
    settings, _, _, _ = cached_pexels
    with pytest.raises(ValueError, match='illustrative entities'):
        register_cached_pexels(settings, 42, entities=['person'], roles=[role])
    assert local_records(settings.data_root) == []


def test_pexels_cache_symlinks_and_changed_registered_bytes_are_not_trusted(cached_pexels):
    settings, video, _, _ = cached_pexels
    register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    receipt = settings.data_root / 'cache/media-library/source-pexels-42.json'
    before = receipt.read_bytes()
    with video.open('ab') as stream:
        stream.write(b'changed bytes')
    with pytest.raises(ValueError, match='bytes changed'):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    assert receipt.read_bytes() == before
    saved = video.with_name('original.mp4')
    video.rename(saved)
    video.symlink_to(saved)
    with pytest.raises(ValueError, match='symlinks'):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])


@pytest.mark.parametrize('mutation', ['usage', 'license', 'page', 'fake_cc', 'path_swap'])
def test_pexels_catalog_license_policy_cannot_be_relabelled(cached_pexels, mutation):
    settings, _, _, _ = cached_pexels
    record = register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    if mutation == 'usage':
        record['usage'] = 'document'
    elif mutation == 'license':
        record['license_url'] = 'https://creativecommons.org/licenses/by/4.0/'
    elif mutation == 'page':
        record['source_url'] = 'https://www.pexels.com/video/other-99/'
    elif mutation == 'fake_cc':
        record.update(license='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0/')
    else:
        record['path'] = 'cache/pexels/videos/43.mp4'
    with pytest.raises(ValueError):
        validate_record_license(record)
    assert select_asset([record], entity='typing', role='stock')['status'] == 'missing'


def test_offline_pexels_cli_and_catalog_list_do_not_construct_http_client(cached_pexels, monkeypatch, capsys):
    settings, _, _, _ = cached_pexels
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('media_library_cli', root / 'scripts/media_library.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('Offline CLI constructed HTTP client'))
    assert module.main(['register-pexels', '42', '--entity', 'typing', '--role', 'stock'], settings=settings) == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered['asset_id'] == 42
    assert module.main(['list'], settings=settings) == 0
    assert json.loads(capsys.readouterr().out)[0]['license'] == 'Pexels'


def pexels_brief(settings):
    with wave.open(str(settings.data_root / 'approved.wav'), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(bytes(16000 * 2 * 6))
    return {'episode_id': 'illustration', 'title': 'Illustrative footage', 'audio_source': 'approved.wav',
            'audio_approved': True, 'duration': 2, 'beats': [{
                'id': 'one', 'start': 0, 'end': 2, 'intent': 'investigate', 'composer': 'stock',
                'claim': 'A historical statement supported by a separate source.',
                'evidence_url': 'https://example.org/report', 'entity': 'typing', 'role': 'stock'}]}


def test_director_uses_registered_pexels_only_as_illustration_and_checks_hash(cached_pexels):
    from kitok.editing.director import compile_brief, load_records
    settings, video, _, _ = cached_pexels
    register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    value = pexels_brief(settings)
    result = compile_brief(value, load_records(settings.data_root), root=settings.data_root)
    assert result['status'] == 'ready' and result['provider_requests'] == 0
    chosen = next(iter(result['plan']['assets'].values()))
    assert chosen['usage'] == 'illustration'
    assert result['decisions'][0]['license'] == 'Pexels'
    assert result['decisions'][0]['content_id'] == 'unknown'
    with video.open('ab') as stream:
        stream.write(b'changed bytes')
    blocked = compile_brief(value, load_records(settings.data_root), root=settings.data_root)
    assert blocked['plan'] is None and 'differ' in blocked['missing'][0]['rejected'][0]


@pytest.mark.parametrize('misuse', ['identity', 'profile', 'historical_source'])
def test_director_cannot_turn_pexels_stock_into_identity_or_historical_evidence(cached_pexels, misuse):
    from kitok.editing.director import compile_brief
    settings, _, _, _ = cached_pexels
    record = register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    value = pexels_brief(settings)
    if misuse == 'historical_source':
        value['beats'][0]['evidence_url'] = record['source_url']
    else:
        value['beats'][0]['intent'] = 'identify' if misuse == 'identity' else 'profile'
    result = compile_brief(value, [record], root=settings.data_root)
    assert result['status'] == 'blocked' and result['plan'] is None


def test_director_does_not_repeat_pexels_sha_without_explicit_reuse(cached_pexels):
    from kitok.editing.director import compile_brief
    settings, _, _, _ = cached_pexels
    record = register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    value = pexels_brief(settings)
    value['beats'][0]['end'] = 1
    value['beats'].append({**value['beats'][0], 'id': 'two', 'start': 1, 'end': 2})
    result = compile_brief(value, [record, {**record, 'id': 'duplicate'}], root=settings.data_root)
    assert result['plan'] is None and result['missing'][0]['beat'] == 'two'
    value['beats'][1]['reuse_asset'] = True
    reused = compile_brief(value, [record], root=settings.data_root)
    assert reused['status'] == 'ready' and reused['decisions'][1]['explicit_reuse'] is True


@pytest.mark.parametrize('asset_id', [-1, 0, True, '../escape', '42', 42.0])
def test_pexels_asset_id_cannot_choose_arbitrary_paths(tmp_path, asset_id):
    with pytest.raises(ValueError, match='positive integer'):
        register_cached_pexels(Settings(_env_file=None, data_root=tmp_path), asset_id,
                               entities=['typing'], roles=['stock'])
    assert list(tmp_path.iterdir()) == []


def change_declared_geometry(metadata, search, width, height):
    payload = json.loads(metadata.read_text())
    payload.update(width=width, height=height)
    metadata.write_text(json.dumps(payload))
    payload = json.loads(search.read_text())
    payload['assets'][0]['variants'][0].update(width=width, height=height)
    search.write_text(json.dumps(payload))


def test_lower_resolution_requires_explicit_review_and_preserves_source_metadata(cached_pexels):
    settings, _, metadata, search = cached_pexels
    change_declared_geometry(metadata, search, 640, 360)
    original = metadata.read_bytes()
    with pytest.raises(ValueError, match='explicit lower-resolution'):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    record = register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'], accept_lower_resolution=True)
    assert record['declared_geometry'] == {'width': 640, 'height': 360}
    assert record['measured_geometry'] == {'width': 320, 'height': 180}
    assert record['width'] == 320 and record['height'] == 180
    assert record['lower_resolution_accepted'] is True and record['warnings']
    assert metadata.read_bytes() == original


@pytest.mark.parametrize('geometry', [(640, 400), (160, 90), (640, 180)])
def test_lower_resolution_review_cannot_accept_changed_aspect_ratio_or_upscaled_files(cached_pexels, geometry):
    settings, _, metadata, search = cached_pexels
    change_declared_geometry(metadata, search, *geometry)
    with pytest.raises(ValueError, match='geometry differ'):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'], accept_lower_resolution=True)


def test_lower_resolution_review_does_not_override_bad_duration(cached_pexels):
    settings, _, metadata, search = cached_pexels
    change_declared_geometry(metadata, search, 640, 360)
    payload = json.loads(metadata.read_text())
    payload['duration'] = 99
    metadata.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='measured video stream'):
        register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'], accept_lower_resolution=True)


@pytest.mark.parametrize('field,value', [('license_url', 123), ('license_url', None), ('source_url', []), ('source_url', None)])
def test_corrupt_catalog_url_types_fail_clearly_instead_of_crashing_selection(cached_pexels, field, value):
    settings, _, _, _ = cached_pexels
    record = register_cached_pexels(settings, 42, entities=['typing'], roles=['stock'])
    record[field] = value
    with pytest.raises(ValueError, match='URLs must be text'):
        validate_record_license(record)
    assert select_asset([record], entity='typing', role='stock')['status'] == 'missing'
