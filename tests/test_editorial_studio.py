"""Isolated editorial HTTP lifecycle; no real render or provider requests."""
import json
import threading
import time

import pytest

from test_studio_api import studio
from kitok.editorial_studio import EditorialStudio
from kitok.locks import generation_lock
from kitok.state import write_json_atomic


@pytest.fixture(autouse=True)
def direct_file_io(monkeypatch):
    async def direct(func, *args, **kwargs):
        return func(*args)
    monkeypatch.setattr('anyio.to_thread.run_sync', direct)


def comparison(settings):
    root = settings.data_root
    folder = root / 'outputs/evaluation/sample_ab'
    folder.mkdir(parents=True)
    (folder / 'A_current.mp4').write_bytes(b'approved-A')
    (folder / 'B_improved.mp4').write_bytes(b'previous-B')
    audio = root / 'existing.wav'
    audio.write_bytes(b'approved-audio')
    plan = {'episode_id': 'sample', 'title': 'My saved comparison', 'audio_source': 'existing.wav',
            'duration': 2, 'scenes': [{'id': 'one', 'start': 0, 'end': 2, 'intention': 'Explain',
                                     'spoken_claim': 'An approved fact', 'graphic': 'identity'}]}
    (folder / 'plan.json').write_text(json.dumps(plan))
    return folder, audio, plan


def wait(service):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        row = service.detail('sample_ab')
        if row['status'] not in {'queued', 'running'}:
            return row
        time.sleep(.01)
    raise AssertionError('Editorial job did not finish')


def fake_qa(video, output, **kwargs):
    assert kwargs['comparison'].name == 'A_current.mp4'
    output.with_suffix('.contact.jpg').write_bytes(b'contact')
    report = {'duration': 2, 'geometry': [1920, 1080], 'fps': 30, 'full_decode': 'passed',
              'comparison': {'audio_identical': True}, 'black_intervals': []}
    write_json_atomic(output, report)
    return report


def test_reads_only_valid_saved_comparisons_and_allowlisted_files(studio):
    client, app, settings = studio
    folder, audio, plan = comparison(settings)
    bad = folder.parent / 'invalid'
    bad.mkdir()
    (bad / 'plan.json').write_text('{}')
    before = {p: p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    rows = client.get('/api/editorial').json()
    assert [row['id'] for row in rows] == ['sample_ab']
    assert rows[0]['title'] == plan['title'] and rows[0]['scene_count'] == 1
    assert client.get('/api/editorial/sample_ab/files/A_current.mp4').content == b'approved-A'
    for name in ('plan.json', 'existing.wav', 'B_improved.previous-test.mp4'):
        assert client.get(f'/api/editorial/sample_ab/files/{name}').status_code == 422
    assert client.get('/api/editorial/not.valid').status_code == 422
    after = {p: p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    assert before == after


def test_editorial_credits_are_plain_text_and_cannot_redirect_to_private_files(studio):
    client, _, settings = studio
    folder, audio, _ = comparison(settings)
    credits = folder / 'CREDITS.md'
    credits.write_text('Author / CC BY-SA 2.0 / source URL / adapted crop')
    row = client.get('/api/editorial/sample_ab').json()
    response = client.get(row['files']['CREDITS.md'])
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    assert 'CC BY-SA' in response.text
    credits.unlink()
    credits.symlink_to(audio)
    assert client.get('/api/editorial/sample_ab/files/CREDITS.md').status_code == 422


def test_success_preserves_inputs_and_previous_b_and_exposes_qa(studio, monkeypatch):
    client, app, settings = studio
    folder, audio, _ = comparison(settings)
    def render(plan, **kwargs):
        assert kwargs['root'] == settings.data_root
        kwargs['output'].write_bytes(b'reviewed-B')
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan', render)
    monkeypatch.setattr('kitok.editorial_studio.inspect_video', fake_qa)
    assert client.post('/api/editorial/sample_ab/jobs').status_code == 202
    row = wait(client.app.state.editorial)
    assert row['status'] == 'succeeded' and row['stats']['comparison']['audio_identical'] is True
    assert (folder / 'B_improved.mp4').read_bytes() == b'reviewed-B'
    assert list(folder.glob('B_improved.previous-*.mp4'))[0].read_bytes() == b'previous-B'
    assert audio.read_bytes() == b'approved-audio' and (folder / 'A_current.mp4').read_bytes() == b'approved-A'
    assert client.get(row['files']['B_improved.contact.jpg']).content == b'contact'
    assert client.get(row['files']['B_improved.qa.json']).json()['video'] == str(folder / 'B_improved.mp4')
    record = json.loads((settings.state_path.parent / 'editorial/sample_ab.json').read_text())
    assert record['status'] == 'succeeded'


def test_failed_qa_keeps_previous_b_and_never_retries(studio, monkeypatch):
    client, app, settings = studio
    folder, audio, _ = comparison(settings)
    calls = []
    def render(plan, **kwargs):
        calls.append(plan)
        kwargs['output'].write_bytes(b'bad-B')
    def fail(*args, **kwargs):
        raise RuntimeError('A/B audio differs')
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan', render)
    monkeypatch.setattr('kitok.editorial_studio.inspect_video', fail)
    assert client.post('/api/editorial/sample_ab/jobs').status_code == 202
    assert wait(client.app.state.editorial)['status'] == 'failed'
    assert (folder / 'B_improved.mp4').read_bytes() == b'previous-B'
    assert not list(folder.glob('*.previous-*'))
    assert len(calls) == 1 and audio.read_bytes() == b'approved-audio'
    EditorialStudio(app)
    assert len(calls) == 1


def test_start_holds_shared_executor_and_cross_process_lease(studio, monkeypatch):
    client, app, settings = studio
    comparison(settings)
    entered, release = threading.Event(), threading.Event()
    def render(plan, **kwargs):
        entered.set()
        assert release.wait(3)
        kwargs['output'].write_bytes(b'new-B')
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan', render)
    monkeypatch.setattr('kitok.editorial_studio.inspect_video', fake_qa)
    try:
        assert client.post('/api/editorial/sample_ab/jobs').status_code == 202
        assert entered.wait(2)
        assert client.post('/api/editorial/sample_ab/jobs').status_code == 409
        duplicate_service = EditorialStudio(app)
        assert duplicate_service.detail('sample_ab')['status'] == 'running'
        with pytest.raises(RuntimeError, match='already'):
            with generation_lock(settings, 'editorial-sample_ab'):
                pass
    finally:
        release.set()
    assert wait(client.app.state.editorial)['status'] == 'succeeded'


def test_restart_marks_unowned_work_interrupted_without_render(studio, monkeypatch):
    client, app, settings = studio
    comparison(settings)
    service = client.app.state.editorial
    service._write({'id': 'sample_ab', 'status': 'running', 'stage': 'Old job'})
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan', lambda *args, **kwargs: pytest.fail('Restart must not render'))
    restarted = EditorialStudio(app)
    assert restarted.detail('sample_ab')['status'] == 'interrupted'


def test_invalid_or_escaping_plan_fails_before_job_and_symlink_files_are_blocked(studio):
    client, _, settings = studio
    folder, audio, plan = comparison(settings)
    plan['audio_source'] = '../outside.wav'
    (folder / 'plan.json').write_text(json.dumps(plan))
    assert client.post('/api/editorial/sample_ab/jobs').status_code == 422
    assert not (settings.state_path.parent / 'editorial/sample_ab.json').exists()
    plan['audio_source'] = 'outputs/evaluation/sample_ab/B_improved.mp4'
    (folder / 'plan.json').write_text(json.dumps(plan))
    assert client.post('/api/editorial/sample_ab/jobs').status_code == 422
    (folder / 'B_improved.mp4').unlink()
    (folder / 'B_improved.mp4').symlink_to(audio)
    assert client.get('/api/editorial/sample_ab/files/B_improved.mp4').status_code == 422


def test_short_defaults_are_fish_stock_checks_both_keys_and_edge_is_history_only(studio):
    client, _, settings = studio
    body = {'subject': 'Native short', 'script': 'A sufficiently long native short script.', 'keywords': ['science']}
    result = client.post('/api/content-preview', json=body)
    assert result.status_code == 200
    assert result.json()['uses_mpt'] is False
    checks = {row['label']: row['ok'] for row in result.json()['checks']}
    assert checks['FISH_API_KEY configurada'] is False
    assert checks['PEXELS_API_KEY configurada'] is False
    assert client.post('/api/content', json=body).json()['item']['voice_profile'] == 'rick_es'
    bad = client.post('/api/content-preview', json=body | {'voice_profile': 'alvaro'})
    assert bad.status_code == 422 and 'Fish' in bad.json()['detail']
    assert client.post('/api/health/mpt').status_code == 404


def test_incomplete_qa_artifacts_leave_current_comparison_intact(studio, monkeypatch):
    client, _, settings = studio
    folder, _, _ = comparison(settings)
    def render(plan, **kwargs):
        kwargs['output'].write_bytes(b'new-B')
    def incomplete(video, output, **kwargs):
        write_json_atomic(output, {'full_decode': 'passed'})
        return {'full_decode': 'passed'}  # Missing contact sheet must not promote the MP4.
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan', render)
    monkeypatch.setattr('kitok.editorial_studio.inspect_video', incomplete)
    assert client.post('/api/editorial/sample_ab/jobs').status_code == 202
    assert wait(client.app.state.editorial)['status'] == 'failed'
    assert (folder / 'B_improved.mp4').read_bytes() == b'previous-B'


@pytest.mark.parametrize('destination', ['A_current.mp4', 'plan.json'])
def test_internal_output_symlink_cannot_replace_approved_inputs(studio, monkeypatch, destination):
    client, _, settings = studio
    folder, audio, _ = comparison(settings)
    before = (folder / destination).read_bytes()
    (folder / 'B_improved.mp4').unlink()
    (folder / 'B_improved.mp4').symlink_to(destination)
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan',
                        lambda *args, **kwargs: pytest.fail('Unsafe plan must not render'))
    assert client.post('/api/editorial/sample_ab/jobs').status_code == 422
    assert client.get('/api/editorial/sample_ab/files/B_improved.mp4').status_code == 422
    assert (folder / destination).read_bytes() == before
    assert audio.read_bytes() == b'approved-audio'
    assert not (settings.state_path.parent / 'editorial/sample_ab.json').exists()


@pytest.mark.parametrize('crash_file', ['B_improved.contact.jpg', 'B_improved.qa.json'])
def test_interrupted_promotion_hides_mismatched_qa_and_contacts_after_restart(studio, monkeypatch, crash_file):
    client, app, settings = studio
    folder, _, plan_data = comparison(settings)
    from kitok.editing.storyboard import file_hash
    (folder/'B_improved.contact.jpg').write_bytes(b'old-contact')
    write_json_atomic(folder/'B_improved.qa.json', {
        'video_sha256': file_hash(folder/'B_improved.mp4'),
        'contact_sheet_sha256': file_hash(folder/'B_improved.contact.jpg'),
        'loudness': {'integrated': -16}})
    from kitok.editing.storyboard import EditorialPlan
    service = client.app.state.editorial
    lease = type('Lease', (), {'close': lambda self: None})()
    record = {'id': 'sample_ab', 'status': 'queued', 'run_id': 'interrupted', 'stage': 'Queued', 'error': None}
    def render(plan, **kwargs):
        kwargs['output'].write_bytes(b'new-B')
    monkeypatch.setattr('kitok.editorial_studio.render_editorial_plan', render)
    monkeypatch.setattr('kitok.editorial_studio.inspect_video', fake_qa)
    from pathlib import Path
    replace = Path.replace
    def crash_after_metadata(path, target):
        result = replace(path, target)
        if Path(target).name == crash_file:
            raise SystemExit('Simulated process interruption')
        return result
    with monkeypatch.context() as context:
        context.setattr(Path, 'replace', crash_after_metadata)
        with pytest.raises(SystemExit):
            service._run(record, EditorialPlan.model_validate(plan_data), lease)
    restarted = EditorialStudio(app)
    row = restarted.detail('sample_ab')
    assert row['status'] == 'interrupted' and row['stats'] is None
    assert row['qa_warning'] and 'B_improved.qa.json' not in row['files']
    assert 'B_improved.contact.jpg' not in row['files']
    assert (folder/'B_improved.mp4').read_bytes() == b'previous-B'
    for name in ('B_improved.qa.json', 'B_improved.contact.jpg'):
        assert client.get(f'/api/editorial/sample_ab/files/{name}').status_code == 422
    assert list(folder.glob('B_improved.previous-*.mp4'))[0].read_bytes() == b'previous-B'
