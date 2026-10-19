"""Small licensed image library: Commons discovery, bounded downloads, explicit relevance.

A metadata license is evidence from the source, not a guarantee against every
third-party claim. Keep attribution and ShareAlike obligations with the asset.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import httpx
from PIL import Image

from .locks import generation_lock
from .media.ffprobe import probe_media, stream_durations
from .state import write_json_atomic

COMMONS = 'https://commons.wikimedia.org/w/api.php'
LICENSES = {'CC0', 'CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0',
            'CC BY-SA 2.0', 'CC BY-SA 3.0', 'CC BY-SA 4.0'}
MAX_BYTES = 15 * 1024 * 1024
PEXELS_LICENSE = 'https://www.pexels.com/license/'
PEXELS_ROLES = {'illustration', 'stock', 'footage', 'context', 'establishing', 'detail', 'background'}


def validate_pexels_page(url, asset_id):
    """Only cached official video pages naming the exact numeric asset are usable."""
    if type(asset_id) is not int or not 1 <= asset_id < 10**12:
        raise ValueError('Pexels asset ID must be a positive integer')
    if not isinstance(url, str):
        raise ValueError('Pexels source page must be a URL naming the exact cached video ID')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in {'www.pexels.com', 'pexels.com'}
            or parsed.username or parsed.password or parsed.port not in {None, 443}
            or parsed.query or parsed.fragment
            or not re.fullmatch(r'/video/(?:[a-zA-Z0-9-]+-)?' + str(asset_id) + r'/?', parsed.path)):
        raise ValueError('Pexels source page must identify the exact cached video ID')
    return url


def validate_record_license(record):
    """Central acceptance contract for local catalog selection, not a legal guarantee."""
    if not isinstance(record, dict):
        raise ValueError('Catalog receipt must be an object')
    license_name = record.get('license')
    if (not isinstance(license_name, str) or not isinstance(record.get('license_url'), str)
            or not isinstance(record.get('source_url', ''), str)):
        raise ValueError('Catalog license and source URLs must be text')
    parsed = urlsplit(record.get('license_url', ''))
    if (record.get('provider') == 'pexels' or urlsplit(record.get('source_url', '')).hostname in {'pexels.com', 'www.pexels.com'}) and license_name != 'Pexels':
        raise ValueError('Pexels media cannot be relabelled as Creative Commons')
    if license_name == 'Pexels':
        if record.get('license_url') != PEXELS_LICENSE:
            raise ValueError('Pexels records need the official Pexels license URL')
        validate_pexels_page(record.get('source_url', ''), record.get('asset_id'))
        if record.get('path') != f"cache/pexels/videos/{record['asset_id']}.mp4":
            raise ValueError('Pexels catalog media must remain bound to its cached asset ID')
        if record.get('usage') != 'illustration':
            raise ValueError('Pexels stock can only be an illustration, never identity or historical evidence')
        roles = record.get('roles', [])
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in PEXELS_ROLES for role in roles):
            raise ValueError('Pexels roles must describe illustrative stock, not identity or documents')
        return
    if (license_name not in LICENSES or parsed.scheme not in {'http', 'https'}
            or parsed.hostname != 'creativecommons.org' or parsed.username or parsed.password):
        raise ValueError('No accepted commercial reuse license and matching URL')
    parts = license_name.split()
    expected = '/publicdomain/zero/1.0/' if license_name == 'CC0' else f'/licenses/{parts[1].lower()}/{parts[2]}/'
    if parsed.path.rstrip('/') != expected.rstrip('/'):
        raise ValueError('Asset license name and URL contradict each other')


def _local_file(root, path):
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Media library paths cannot escape the workspace or use symlinks')
    if not path.is_file():
        raise ValueError('Required cached media or metadata is missing')
    return path


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def local_records(root):
    """Read both local sources without creating an HTTP client."""
    root = root.resolve()
    folder = root / 'cache/media-library'
    if not folder.exists():
        return []
    if not folder.resolve().is_relative_to(root) or any(p.is_symlink() for p in (folder, *folder.parents)):
        raise ValueError('The media library cannot contain redirected directories')
    paths = sorted([*folder.glob('commons-*.json'), *folder.glob('source-pexels-*.json')])
    return [json.loads(_local_file(root, path).read_text(encoding='utf-8')) for path in paths]


def register_cached_pexels(settings, asset_id, *, entities, roles, accept_lower_resolution=False):
    """Annotate a verified existing cache entry. No search, download or provider call."""
    validate_pexels_page(f'https://www.pexels.com/video/{asset_id}/', asset_id)
    if (not isinstance(entities, list) or not entities or any(not isinstance(x, str) or not x.strip() or len(x) > 150 for x in entities)
            or not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in PEXELS_ROLES for role in roles)):
        raise ValueError('Annotate exact illustrative entities and supported stock roles')
    root = (settings.data_root or Path(__file__).resolve().parents[2]).resolve()
    cache = root / 'cache/pexels'
    video = _local_file(root, cache / 'videos' / f'{asset_id}.mp4')
    metadata = json.loads(_local_file(root, cache / 'videos' / f'{asset_id}.json').read_text())
    if not isinstance(metadata, dict):
        raise ValueError('Pexels cache metadata must be an object')
    if metadata.get('asset_id') != asset_id or type(metadata.get('asset_id')) is not int:
        raise ValueError('Pexels cache metadata identifies a different asset')
    download = metadata.get('url')
    if not isinstance(download, str):
        raise ValueError('Pexels cache needs its original downloaded variant URL')
    parsed_download = urlsplit(download)
    if (parsed_download.scheme != 'https' or parsed_download.hostname != 'videos.pexels.com'
            or parsed_download.username or parsed_download.password or parsed_download.port not in {None, 443}
            or not re.fullmatch(r'/video-files/' + str(asset_id) + r'/[A-Za-z0-9_-]+\.mp4', parsed_download.path)):
        raise ValueError('Cached variant must identify the same asset on the Pexels video host')
    info = probe_media(video, settings.ffprobe_binary)
    video_duration, _ = stream_durations(video, settings.ffprobe_binary)
    duration = metadata.get('duration')
    declared = (metadata.get('width'), metadata.get('height'))
    measured = (info.width, info.height)
    if any(type(value) is not int or value <= 0 for value in declared):
        raise ValueError('Pexels API geometry must contain positive integer dimensions')
    lower_resolution = measured != declared
    if lower_resolution:
        # One output pixel permits normal integer rounding during downscaling.
        proportional = (bool(info.width and info.height)
                        and abs(info.width - declared[0] * info.height / declared[1]) <= 1)
        smaller = bool(info.width and info.height and info.width <= declared[0] and info.height <= declared[1])
        if not (accept_lower_resolution is True and proportional and smaller):
            raise ValueError('Pexels declared and measured geometry differ; an explicit lower-resolution review is required')
    if (not info.video_codec or not info.width or not info.height or video_duration is None
            or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0
            or abs(duration - video_duration) > 1):
        raise ValueError('Pexels cache metadata and measured video stream differ')
    pages = []
    searches = cache / 'searches'
    if not searches.resolve().is_relative_to(root) or any(p.is_symlink() for p in (searches, *searches.parents)):
        raise ValueError('Pexels search cache cannot be redirected')
    for path in sorted(searches.glob('*.json')):
        payload = json.loads(_local_file(root, path).read_text())
        if not isinstance(payload, dict) or not isinstance(payload.get('assets'), list):
            raise ValueError('Pexels search cache must contain an asset list')
        for candidate in payload.get('assets', []):
            if not isinstance(candidate, dict):
                raise ValueError('Pexels search assets must be objects')
            if candidate.get('asset_id') != asset_id or type(candidate.get('asset_id')) is not int:
                continue
            variants = candidate.get('variants', [])
            if not isinstance(variants, list) or any(not isinstance(v, dict) for v in variants):
                raise ValueError('Pexels search variants must be objects')
            matching = any(variant.get('url') == metadata.get('url')
                           and (variant.get('width'), variant.get('height')) == declared
                           for variant in variants)
            if matching:
                pages.append(validate_pexels_page(candidate.get('page_url', ''), asset_id))
    if not pages:
        raise ValueError('No matching Pexels page and downloaded variant in the local search cache')
    source = sorted(set(pages))[0]
    fingerprint = _file_hash(video)
    with generation_lock(settings, 'media-library'):
        folder = root / 'cache/media-library'
        if any(p.is_symlink() for p in (folder, *folder.parents)):
            raise ValueError('The media library cannot contain redirected directories')
        folder.mkdir(parents=True, exist_ok=True)
        receipt = folder / f'source-pexels-{asset_id}.json'
        if receipt.is_symlink():
            raise ValueError('The catalog receipt cannot be redirected')
        if receipt.is_file():
            prior = json.loads(receipt.read_text())
            validate_record_license(prior)
            if prior.get('sha256') != fingerprint or prior.get('asset_id') != asset_id:
                raise ValueError('Registered Pexels bytes changed; review before replacing the receipt')
            entities = list(dict.fromkeys(prior['entities'] + entities))
            roles = list(dict.fromkeys(prior['roles'] + roles))
        record = {'id': f'pexels-{asset_id}', 'asset_id': asset_id, 'provider': 'pexels',
                  'title': f'Pexels video {asset_id}', 'path': str(video.relative_to(root)),
                  'sha256': fingerprint, 'source_url': source, 'author': 'unknown',
                  'license': 'Pexels', 'license_url': PEXELS_LICENSE, 'usage': 'illustration',
                  'attribution': f'Pexels video {asset_id}; creator unknown in local cache; {source}',
                  'restrictions': 'No implied endorsement; do not portray identifiable people negatively; '
                                  'not historical footage or evidence; review Pexels license before publishing',
                  'share_alike': False, 'content_id': 'unknown', 'width': info.width, 'height': info.height,
                  'declared_geometry': {'width': declared[0], 'height': declared[1]},
                  'measured_geometry': {'width': info.width, 'height': info.height},
                  'lower_resolution_accepted': lower_resolution,
                  'warnings': (['Operator accepted a lower-resolution cached file after review; original API metadata preserved']
                               if lower_resolution else []),
                  'duration': video_duration, 'fps': info.fps, 'entities': entities, 'roles': roles,
                  'verified_at': datetime.now(timezone.utc).isoformat()}
        validate_record_license(record)
        write_json_atomic(receipt, record)
        return record


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
        try:
            validate_record_license(record)
        except (ValueError, TypeError):
            continue
        if not record.get('path'):
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
        return local_records(self.root)
