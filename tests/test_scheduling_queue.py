from datetime import datetime, timedelta, timezone
import json

import pytest

from kitok.application import Application
from kitok.batch_import import validate_batch
from kitok.models import ContentItem, ContentQueue
from kitok.queue_editor import add_batch, queue_digest
from kitok.scheduling import ScheduleService
from kitok.state import StateStore


@pytest.fixture
def scheduler(local_kitok):
    settings, _, state, video = local_kitok
    app = Application(settings)
    service = ScheduleService(app)
    try:
        yield service, app, settings, state, video
    finally:
        app.close()


def unschedule_all(service, settings):
    for item in ContentQueue.load(settings.queue_path).items:
        service.change(item.id, None)


def test_ready_item_can_be_unscheduled_without_touching_generation_or_media(scheduler):
    service, _, settings, state, video = scheduler
    service.change('one', None)
    item = ContentQueue.load(settings.queue_path).by_id()['one']
    assert item.publish_at is None and not item.schedule_enabled
    assert state.get('one')['status'] == 'ready'
    assert service.view()['unscheduled'][0]['schedule_status'] == 'unscheduled'
    assert video.read_bytes() == b'test-media'


def test_queue_add_remove_and_fifo_manual_reordering(scheduler):
    service, _, settings, _, _ = scheduler
    unschedule_all(service, settings)
    service.queue_add('one')
    service.queue_add('two')
    assert [row['item']['id'] for row in service.view()['queued']] == ['one', 'two']
    service.queue_move('two', 'up')
    assert [row['item']['id'] for row in service.view()['queued']] == ['two', 'one']
    service.queue_move('two', 'down')
    assert [row['item']['id'] for row in service.view()['queued']] == ['one', 'two']
    service.queue_move('two', 'top')
    assert [row['item']['id'] for row in service.view()['queued']] == ['two', 'one']
    service.queue_move('two', 'bottom')
    assert [row['item']['id'] for row in service.view()['queued']] == ['one', 'two']
    service.queue_remove('one')
    assert [row['item']['id'] for row in service.view()['queued']] == ['two']
    assert service.app.content('one')['schedule_status'] == 'unscheduled'


def test_auto_fill_skips_past_and_occupied_slots_and_preserves_timezone(local_kitok):
    settings, _, _, _ = local_kitok
    app = Application(settings)
    now = datetime.fromisoformat('2026-09-21T17:50:00+02:00')
    service = ScheduleService(app, now=lambda: now)
    try:
        unschedule_all(service, settings)
        service.change('one', datetime.fromisoformat('2026-09-21T19:00:00+02:00'))
        service.queue_add('two')
        # Add a third READY item without any publish_at.
        created = app.create({
            'id': 'three', 'subject': 'Three', 'script': 'A sufficiently long narration script.',
            'caption': 'Three', 'keywords': ['three'],
        })
        StateStore(settings.state_path).upsert(created['item']['id'], status='ready')
        service.queue_add('three')

        preview = service.fill(confirm=False)
        assert preview['assignments'] == [
            {'id': 'two', 'at': '2026-09-21T22:00:00+02:00'},
            {'id': 'three', 'at': '2026-09-22T13:00:00+02:00'},
        ]
        assert service.app.content('two')['schedule_status'] == 'queued'
        service.fill(confirm=True)
        assert service.app.content('two')['scheduled_at'] == '2026-09-21T22:00:00+02:00'
        assert service.app.content('three')['scheduled_at'] == '2026-09-22T13:00:00+02:00'
        assert not service.view()['queued']
    finally:
        app.close()


def test_scheduled_items_can_swap_earlier_and_later_without_touching_generation(scheduler):
    service, _, settings, state, _ = scheduler
    before = {item.id: item.publish_at for item in ContentQueue.load(settings.queue_path).items}
    service.schedule_move('two', 'earlier')
    moved = {item.id: item.publish_at for item in ContentQueue.load(settings.queue_path).items}
    assert moved['two'] == before['one'] and moved['one'] == before['two']
    service.schedule_move('two', 'later')
    restored = {item.id: item.publish_at for item in ContentQueue.load(settings.queue_path).items}
    assert restored == before
    assert state.get('one')['status'] == state.get('two')['status'] == 'ready'


def test_published_or_buffer_scheduled_item_cannot_be_unscheduled(scheduler):
    service, _, _, state, _ = scheduler
    state.update_publishing('one', 'buffer', 'tiktok', post_id='remote', status='sent')
    with pytest.raises(ValueError, match='Buffer'):
        service.change('one', None)
    assert service.app.content('one')['generation_status'] == 'ready'
    assert service.app.content('one')['schedule_status'] == 'published'


def test_bulk_unschedule_reports_buffer_items_as_attention(scheduler):
    service, _, _, state, _ = scheduler
    state.update_publishing('one', 'buffer', 'tiktok', post_id='remote', status='scheduled')
    preview = service.unschedule_future(confirm=False)
    assert 'one' in preview['attention'] and 'one' not in preview['ids']
    result = service.unschedule_future(confirm=True)
    assert 'one' in result['attention']
    assert service.app.content('one')['scheduled_at'] is not None


def test_old_rows_and_explicit_publish_at_remain_scheduled():
    old = ContentItem.model_validate({
        'id': 'old', 'subject': 'Old', 'script': 'A sufficiently long narration script.',
        'caption': 'Old', 'keywords': ['old'], 'publish_at': '2030-01-01T13:00:00+01:00',
    })
    assert old.schedule_enabled and old.publish_at.isoformat() == '2030-01-01T13:00:00+01:00'
    fresh = ContentItem.model_validate({
        'id': 'fresh', 'subject': 'Fresh', 'script': 'A sufficiently long narration script.',
        'caption': 'Fresh', 'keywords': ['fresh'],
    })
    assert fresh.publish_at is None and not fresh.schedule_enabled


def test_batch_without_publish_at_imports_unscheduled_and_conflicts_do_not_block(local_kitok):
    settings, queue, state, _ = local_kitok
    rows = [{
        'id': f'new-{index}', 'subject': f'New {index}',
        'script': 'A sufficiently long narration script.', 'caption': 'New',
        'keywords': ['new'],
    } for index in range(2)]
    items, errors = validate_batch(rows, queue, state)
    assert not errors and all(item.publish_at is None for item in items)
    imported = add_batch(settings.queue_path, state, rows,
                         expected_revision=queue_digest(settings.queue_path))
    assert all(not item.schedule_enabled for item in imported)

    conflict = [{**rows[0], 'id': 'explicit-conflict',
                 'publish_at': queue.items[0].publish_at.isoformat()}]
    assert not validate_batch(conflict, ContentQueue.load(settings.queue_path), state)[1]


def test_bulk_future_unschedule_dry_run_then_confirm_keeps_files(scheduler):
    service, _, settings, state, video = scheduler
    future = datetime.now(timezone.utc) + timedelta(days=5)
    service.change('one', future)
    service.change('two', future + timedelta(hours=1))
    before = settings.queue_path.read_bytes()
    preview = service.unschedule_future(confirm=False)
    assert preview['ids'] == ['one', 'two']
    assert settings.queue_path.read_bytes() == before
    result = service.unschedule_future(confirm=True)
    assert result['count'] == 2
    assert all(item.publish_at is None for item in ContentQueue.load(settings.queue_path).items)
    assert state.get('one')['status'] == 'ready' and video.exists()
    assert not state.get('one').get('publishing')


def test_scheduling_cli_dry_runs_and_batch_import_without_services(local_kitok, tmp_path, monkeypatch):
    from kitok import cli

    settings, _, _, _ = local_kitok
    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    before = settings.queue_path.read_bytes()
    assert cli.main(['--unschedule-future', '--dry-run']) == 0
    assert settings.queue_path.read_bytes() == before
    assert cli.main(['--unschedule-future', '--confirm']) == 0
    assert cli.main(['--queue']) == 0

    batch = tmp_path / 'rick_morty_30.json'
    batch.write_text(json.dumps([{
        'id': 'batch-one', 'subject': 'Batch one',
        'script': 'A sufficiently long narration script.', 'caption': 'Batch',
        'keywords': ['batch'],
    }]))
    assert cli.main(['--import-batch', str(batch), '--dry-run']) == 0
    assert 'batch-one' not in ContentQueue.load(settings.queue_path).by_id()
    assert cli.main(['--import-batch', str(batch), '--confirm']) == 0
    imported = ContentQueue.load(settings.queue_path).by_id()['batch-one']
    assert imported.publish_at is None and not imported.schedule_enabled
