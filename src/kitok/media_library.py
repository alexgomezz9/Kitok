"""Small licensed image library: Commons discovery, bounded downloads, explicit relevance.

A metadata license is evidence from the source, not a guarantee against every
third-party claim. Keep attribution and ShareAlike obligations with the asset.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import httpx
from PIL import Image

from .locks import generation_lock
from .state import write_json_atomic

COMMONS = 'https://commons.wikimedia.org/w/api.php'
LICENSES = {'CC0', 'CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0',
            'CC BY-SA 2.0', 'CC BY-SA 3.0', 'CC BY-SA 4.0'}
MAX_BYTES = 15 * 1024 * 1024


class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self, data):self.parts.append(data)


def plain(value):
    parser=Text();parser.feed(str(value))
    return ' '.join(' '.join(parser.parts).split())


def terms(value):
    return set(re.findall(r'\w+',value.casefold()))


def select_asset(records, *, entity: str, role: str, used=()):
    """Exact annotated entity before style/recency: never silently substitute a person."""
    candidates=[]
    for record in records:
        if record.get('license') not in LICENSES or not record.get('path'):
            continue
        if entity.casefold() not in {x.casefold() for x in record.get('entities',[])}:
            continue
        if role not in record.get('roles',[]):
            continue
        score=(record['sha256'] not in used, record.get('width',0)*record.get('height',0))
        candidates.append((score,record))
    if not candidates:
        return {'status':'missing','entity':entity,'role':role,
                'reason':'No licensed local asset annotated with this exact entity and role'}
    best=max(candidates,key=lambda x:x[0])[1]
    return {'status':'selected','asset':best,
            'reason':f'Exact entity {entity}; annotated role {role}; repetition and resolution break ties'}


class CommonsLibrary:
    def __init__(self, settings, *, client=None):
        self.s=settings
        self.root=(settings.data_root or Path(__file__).resolve().parents[2]).resolve()
        self.folder=self.root/'cache/media-library'
        if any(p.is_symlink() for p in (self.folder, *self.folder.parents)):
            raise ValueError('The media library cannot contain redirected directories')
        self.folder.mkdir(parents=True,exist_ok=True)
        self.client=client or httpx.Client(timeout=30,follow_redirects=False,
            headers={'User-Agent':'Kitok/0.1 (local documentary asset catalog)'})
        self.owned=client is None

    def close(self):
        if self.owned:self.client.close()

    def _metadata(self, title):
        if not title.startswith('File:') or len(title)>300:
            raise ValueError('Use a Commons File: title')
        response=self.client.get(COMMONS,params={'action':'query','format':'json','formatversion':2,
            'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','titles':title}, follow_redirects=False)
        response.raise_for_status()
        pages=response.json().get('query',{}).get('pages',[])
        if len(pages)!=1 or not pages[0].get('imageinfo'):
            raise ValueError('Commons file metadata unavailable')
        return pages[0],pages[0]['imageinfo'][0]

    def search(self, entity, limit=5):
        if not 1<=limit<=10 or not 1<=len(entity)<=150:raise ValueError('Invalid search size')
        response=self.client.get(COMMONS,params={'action':'query','format':'json','formatversion':2,
            'list':'search','srsearch':entity,'srnamespace':6,'srlimit':limit}, follow_redirects=False)
        response.raise_for_status()
        return [{'title':x['title'],'page_id':x['pageid'],'query':entity,'status':'candidate-unreviewed'}
                for x in response.json().get('query',{}).get('search',[])]

    def fetch(self,title,*,entities,roles,usage='context'):
        if not entities or not roles or usage not in {'context','identity','document','illustration'}:
            raise ValueError('Annotate entity, visual role and usage before downloading')
        with generation_lock(self.s,'media-library'):
            page,info=self._metadata(title)
            fields=info.get('extmetadata',{})
            get=lambda key:plain(fields.get(key,{}).get('value',''))
            license=get('LicenseShortName')
            license_url=get('LicenseUrl')
            parsed=urlsplit(license_url)
            if (license not in LICENSES or parsed.scheme not in {'https','http'}
                    or parsed.hostname!='creativecommons.org'):
                raise ValueError('No accepted explicit commercial reuse license; resource not downloaded')
            if license == 'CC0':
                expected = '/publicdomain/zero/1.0/'
            else:
                parts = license.split()
                expected = f'/licenses/{parts[1].lower()}/{parts[2]}/'
            if parsed.path.rstrip('/') != expected.rstrip('/'):
                raise ValueError('License name and URL contradict each other; resource not downloaded')
            url=info.get('url','')
            parsed=urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!='upload.wikimedia.org' or parsed.username or parsed.port not in {None,443}:
                raise ValueError('Commons download must use the fixed Wikimedia host')
            mime=info.get('mime')
            extensions={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}
            if mime not in extensions or info.get('size',MAX_BYTES+1)>MAX_BYTES:
                raise ValueError('Unsupported or oversized image')
            if not 1<=info.get('width',0)*info.get('height',0)<=30_000_000:
                raise ValueError('Image geometry exceeds library limits')
            receipt=self.folder/f"commons-{page['pageid']}.json"
            if receipt.is_file():
                prior=json.loads(receipt.read_text())
                path=(self.root/prior['path']).resolve()
                if (path.is_relative_to(self.folder.resolve()) and path.is_file()
                        and hashlib.sha256(path.read_bytes()).hexdigest()==prior.get('sha256')):
                    prior.update(entities=list(dict.fromkeys(prior.get('entities',[])+entities)),
                                 roles=list(dict.fromkeys(prior.get('roles',[])+roles)),usage=usage)
                    write_json_atomic(receipt,prior)
                    return prior
            fd,name=tempfile.mkstemp(dir=self.folder,suffix='.download')
            import os
            try:
                digest=hashlib.sha256();count=0
                with os.fdopen(fd,'wb') as handle:
                    with self.client.stream('GET',url,follow_redirects=False) as response:
                        response.raise_for_status()
                        if response.is_redirect:raise ValueError('Asset redirects are not followed')
                        for block in response.iter_bytes():
                            count+=len(block)
                            if count>MAX_BYTES:raise ValueError('Asset exceeded download limit')
                            handle.write(block);digest.update(block)
                with Image.open(name) as image:
                    if image.width*image.height>30_000_000:raise ValueError('Decoded image exceeds limits')
                    if (image.width, image.height) != (info['width'], info['height']):
                        raise ValueError('Source metadata and decoded image dimensions differ')
                    image.load()
                fingerprint=digest.hexdigest()
                destination=self.folder/(fingerprint+extensions[mime])
                Path(name).replace(destination)
                record={'id':f"commons-{page['pageid']}",'title':title.removeprefix('File:'),
                    'path':str(destination.relative_to(self.root)),'sha256':fingerprint,
                    'source_url':info.get('descriptionurl',f'https://commons.wikimedia.org/wiki/{title}'),
                    'download_url':url,'author':get('Artist'),'credit':get('Credit'),
                    'license':license,'license_url':license_url,'restrictions':get('Restrictions'),
                    'share_alike':'BY-SA' in license,'content_id':'unknown',
                    'attribution':f'{title} — {get("Artist")}; {license}; {license_url}',
                    'width':info['width'],'height':info['height'],'entities':entities,'roles':roles,
                    'usage':usage,'verified_at':datetime.now(timezone.utc).isoformat()}
                write_json_atomic(receipt,record)
                return record
            finally:Path(name).unlink(missing_ok=True)

    def records(self):
        return [json.loads(path.read_text()) for path in sorted(self.folder.glob('commons-*.json'))]
