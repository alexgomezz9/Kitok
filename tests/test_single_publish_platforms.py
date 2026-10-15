"""A single-video send must honor the destinations chosen in the studio."""
import pytest

from test_publisher import setup


@pytest.mark.parametrize('selected', [['youtube'], ['instagram'], ['tiktok', 'youtube']])
def test_single_publish_uses_only_selected_platforms_in_preview_and_send(setup, selected):
    publisher, client, host, state, video = setup
    publisher.q.items[0].platforms = selected
    # A paused account not chosen for this video must not block it either.
    for platform, channel in client.discover.return_value[2].items():
        if platform not in selected:
            channel['isQueuePaused'] = True
    plan = publisher.plan_one('one')
    assert {row['platform'] for row in plan.rows} == set(selected)
    assert plan.issues == []
    seen = []
    result = publisher.publish_one('one', before_execute=lambda p: seen.extend(row['platform'] for row in p.rows))
    assert set(seen) == set(selected)
    assert result['created'] == len(selected)
    assert {call.args[0]['channelId'] for call in client.create_post.call_args_list} == {f'channel-{p}' for p in selected}
    assert set(state.get('one')['publishing']['buffer']) == set(selected)
