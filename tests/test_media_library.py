import io
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from kitok.config import Settings
from kitok.media_library import CommonsLibrary, select_asset


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


@pytest.mark.parametrize('license',['CC BY-NC 4.0','Unknown','All rights reserved'])
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
