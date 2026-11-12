from kitok.youtube.research import public_search, reporting_status


class FakeAPI:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def query(self, request, channel):
        self.calls.append((channel, request['operation'], request['params']))
        return {'result': next(self.replies)}


def test_public_search_batches_stats_and_keeps_hidden_subscribers_unknown():
    search = {'items': [{'id': {'videoId': item}} for item in ['vid-a', 'vid-a', 'vid-b', 'vid-gone']],
              'nextPageToken': 'next'}
    videos = {'items': [
        {'id': 'vid-b', 'snippet': {'channelId': 'b', 'title': 'B'}, 'statistics': {'viewCount': '3000'}},
        {'id': 'vid-a', 'snippet': {'channelId': 'a', 'title': 'A',
                                    'thumbnails': {'high': {'url': 'https://example.invalid/a'}}},
         'statistics': {'viewCount': '9000'}},
    ]}
    channels = {'items': [
        {'id': 'a', 'statistics': {'subscriberCount': '40'}},
        {'id': 'b', 'statistics': {'subscriberCount': '0', 'hiddenSubscriberCount': True}},
    ]}
    api = FakeAPI([search, videos, channels])
    result = public_search(api, 'owner', 'poker', min_views=100)
    assert result['sampled'] == 3 and result['hydrated'] == 2
    assert result['has_more_search_results'] is True
    assert [(row['video_id'], row['subscribers']) for row in result['videos']] == [('vid-a', 40), ('vid-b', None)]
    assert result['videos'][0]['thumbnail_url'] == 'https://example.invalid/a'
    assert api.calls[1][2]['id'] == ['vid-a', 'vid-b', 'vid-gone']
    assert api.calls[2][2]['id'] == ['a', 'b']
    filtered = public_search(FakeAPI([search, videos, channels]), 'owner', 'poker', max_subscribers=100)
    assert [row['video_id'] for row in filtered['videos']] == ['vid-a']


def test_reporting_status_lists_empty_and_available_jobs_without_signed_urls():
    api = FakeAPI([
        {'jobs': [{'id': 'reach', 'reportTypeId': 'channel_reach_combined_a1'},
                  {'id': 'traffic', 'reportTypeId': 'channel_traffic_source_a3'}]},
        {'reports': [{'id': 'new', 'startTime': '2026-11-10', 'downloadUrl': 'https://private.invalid/'}]},
        {},
    ])
    result = reporting_status(api, 'owner')
    assert result['jobs'][0]['recent'] == [{'report_id': 'new', 'start': '2026-11-10', 'end': None}]
    assert result['jobs'][1]['available_on_page'] == 0
    assert 'private.invalid' not in str(result)
