"""Small read-only YouTube research workflows over the verified CLI connection."""
from __future__ import annotations

from .oauth import YouTubeError


def _query(api, channel, operation, **params):
    return api.query({'operation': operation, 'params': params}, channel)['result']


def _count(value):
    return int(value) if isinstance(value, str) and value.isascii() and value.isdecimal() else None


def public_search(api, channel, query, *, limit=20, order='relevance', published_after=None,
                  min_views=None, max_subscribers=None):
    """Search one page, then hydrate public stats in batches. Preserve search order."""
    if not query.strip() or not 1 <= limit <= 50:
        raise YouTubeError('Indica una búsqueda y un límite de 1 a 50 resultados.')
    if any(value is not None and value < 0 for value in (min_views, max_subscribers)):
        raise YouTubeError('Los filtros de vistas y suscriptores deben ser positivos o cero.')
    params = {'part': ['snippet'], 'type': ['video'], 'q': query.strip(), 'maxResults': limit,
              'order': order}
    if published_after:
        params['publishedAfter'] = published_after
    page = _query(api, channel, 'youtube.search.list', **params)
    video_ids = list(dict.fromkeys(item['id']['videoId'] for item in page.get('items', [])))
    videos = {}
    channels = {}
    if video_ids:
        result = _query(api, channel, 'youtube.videos.list', id=video_ids,
                        part=['snippet', 'contentDetails', 'statistics'])
        videos = {item['id']: item for item in result.get('items', [])}
        channel_ids = sorted({item['snippet']['channelId'] for item in videos.values()})
        if channel_ids:
            result = _query(api, channel, 'youtube.channels.list', id=channel_ids, part=['statistics'])
            channels = {item['id']: item['statistics'] for item in result.get('items', [])}

    rows = []
    for video_id in video_ids:
        if video_id not in videos:
            continue
        video = videos[video_id]
        snippet = video['snippet']
        channel_id = snippet['channelId']
        stats = video.get('statistics', {})
        channel_stats = channels.get(channel_id, {})
        views = _count(stats.get('viewCount'))
        subscribers = None if channel_stats.get('hiddenSubscriberCount') else _count(channel_stats.get('subscriberCount'))
        if min_views is not None and (views is None or views < min_views):
            continue
        if max_subscribers is not None and (subscribers is None or subscribers > max_subscribers):
            continue
        thumbnails = snippet.get('thumbnails', {})
        thumbnail = thumbnails.get('high') or thumbnails.get('medium') or thumbnails.get('default') or {}
        rows.append({
            'video_id': video_id,
            'title': snippet['title'],
            'channel_id': channel_id,
            'channel_title': snippet.get('channelTitle'),
            'published_at': snippet.get('publishedAt'),
            'duration': video.get('contentDetails', {}).get('duration'),
            'views': views,
            'subscribers': subscribers,
            'thumbnail_url': thumbnail.get('url'),
        })
    return {'query': query.strip(), 'sampled': len(video_ids), 'hydrated': len(videos),
            'has_more_search_results': bool(page.get('nextPageToken')), 'videos': rows}


def reporting_status(api, channel):
    """List existing private jobs and the latest available dates on the first page."""
    jobs = _query(api, channel, 'youtubereporting.jobs.list')
    entries = []
    for job in jobs.get('jobs', []):
        page = _query(api, channel, 'youtubereporting.jobs.reports.list', jobId=job['id'])
        reports = page.get('reports', [])
        recent = sorted(reports, key=lambda row: row.get('startTime') or '', reverse=True)[:5]
        entries.append({
            'type': job['reportTypeId'],
            'job_id': job['id'],
            'available_on_page': len(reports),
            'has_more_reports': bool(page.get('nextPageToken')),
            'recent': [{'report_id': row['id'], 'start': row.get('startTime'), 'end': row.get('endTime')}
                       for row in recent],
        })
    return {'channel_id': channel, 'has_more_jobs': bool(jobs.get('nextPageToken')), 'jobs': entries}
