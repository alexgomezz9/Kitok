import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import wave

from PIL import Image
import pytest

from kitok.editing.director import DirectorBrief, compile_brief
from kitok.editing.storyboard import EditorialPlan, file_hash


ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('direct_edit', ROOT / 'scripts/direct_edit.py')
cli = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(cli)


@pytest.fixture
def workspace(tmp_path):
    if not shutil.which('ffprobe'):
        pytest.skip('Director preparation measures local audio using ffprobe')
    with wave.open(str(tmp_path / 'approved.wav'), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(bytes(16000 * 2 * 6))
    return tmp_path


def asset(root, *, name='specific', entity='Specific Person', role='portrait', color='red', size=(640, 400)):
    path = root / f'{name}.jpg'
    Image.new('RGB', size, color).save(path)
    return {'id': name, 'title': entity, 'entities': [entity], 'roles': [role],
            'license': 'CC BY 4.0', 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
            'path': path.name, 'sha256': file_hash(path), 'width': size[0], 'height': size[1],
            'source_url': 'https://commons.wikimedia.org/wiki/File:Specific.jpg',
            'attribution': 'Specific photo — Author; CC BY 4.0; https://creativecommons.org/licenses/by/4.0/',
            'usage': 'identity'}


def beat(id='one', start=0, end=2, **kwargs):
    return dict(id=id, start=start, end=end, intent='identify', claim='An explicitly sourced statement.',
                evidence_url='https://example.org/source', composer='photo',
                entity='Specific Person', role='portrait', **kwargs)


def brief(beats=None, **kwargs):
    beats = beats or [beat()]
    return dict(episode_id='test', title='An explicit brief', audio_source='approved.wav',
                audio_approved=True, duration=beats[-1]['end'], beats=beats, **kwargs)


def test_exact_entity_resource_and_approved_audio_survive_compilation(workspace):
    record = asset(workspace)
    result = compile_brief(brief(), [record], root=workspace)
    assert result['status'] == 'ready' and result['provider_requests'] == 0
    plan = EditorialPlan.model_validate(result['plan'])
    assert plan.audio_source == 'approved.wav' and plan.audio_is_final_mix is True
    assert plan.scenes[0].spoken_claim == 'An explicitly sourced statement.'
    assert plan.scenes[0].evidence_url == 'https://example.org/source'
    assert plan.scenes[0].composition == 'photo'
    selected = next(iter(plan.assets.values()))
    assert selected.path == record['path'] and selected.credit == record['attribution']
    assert selected.usage == 'provided'
    assert plan.alignment['director']['decisions'] == result['decisions']


def test_explicit_captions_are_preserved_without_adding_script_inferred_labels(workspace):
    value = beat()
    value.update(headline='$70,000', kicker='Reported summer loss', headline_style='impact')
    result = compile_brief(brief([value]), [asset(workspace)], root=workspace)
    scene = result['plan']['scenes'][0]
    assert scene['headline'] == '$70,000'
    assert scene['kicker'] == 'Reported summer loss'
    assert scene['headline_style'] == 'impact'


def test_selection_is_stable_under_catalog_reordering_and_uses_distinct_sha(workspace):
    records = [asset(workspace, name='one', color='blue'), asset(workspace, name='two', color='red')]
    beats = [beat(end=1), beat('two', 1, 2)]
    first = compile_brief(brief(beats), records, root=workspace)
    second = compile_brief(brief(beats), list(reversed(records)), root=workspace)
    assert first == second
    assert len({d['sha256'] for d in first['decisions']}) == 2


def test_duplicate_records_do_not_evade_repetition_and_missing_blocks_whole_plan(workspace):
    record = asset(workspace)
    beats = [beat(end=1), beat('two', 1, 2)]
    result = compile_brief(brief(beats), [record, {**record, 'id': 'duplicate'}], root=workspace)
    assert result['status'] == 'blocked' and result['plan'] is None
    assert result['missing'][0]['beat'] == 'two'
    assert 'already used' in result['missing'][0]['rejected'][0]
    beats[1]['reuse_asset'] = True
    reused = compile_brief(brief(beats), [record], root=workspace)
    assert reused['status'] == 'ready'
    assert reused['decisions'][1]['explicit_reuse'] is True


@pytest.mark.parametrize('mutation', ['other_person', 'unlicensed', 'stale_hash', 'outside', 'not_image', 'contradictory_license', 'missing_license_url'])
def test_unsafe_or_unrelated_candidates_cannot_be_silent_fallbacks(workspace, tmp_path, mutation):
    record = asset(workspace)
    if mutation == 'other_person':
        record['entities'] = ['Someone Else']
    elif mutation == 'unlicensed':
        record['license'] = 'CC BY-NC 4.0'
    elif mutation == 'stale_hash':
        (workspace / record['path']).write_bytes(b'changed operator data')
    elif mutation == 'outside':
        record['path'] = '/etc/hosts'
    elif mutation == 'contradictory_license':
        record['license_url'] = 'https://creativecommons.org/licenses/by-nc/4.0/'
    elif mutation == 'missing_license_url':
        record.pop('license_url')
    else:
        (workspace / record['path']).write_bytes(b'not a decoded image')
        record['sha256'] = file_hash(workspace / record['path'])
    result = compile_brief(brief(), [record], root=workspace)
    assert result['status'] == 'blocked' and result['plan'] is None
    assert result['missing'][0]['entity'] == 'Specific Person'


def test_explicit_intent_controls_3d_shots_not_script_regex(workspace):
    beats = []
    for index, intent in enumerate(['identify', 'escalate', 'loss', 'conceal', 'reveal']):
        value = beat(str(index), index, index + 1)
        value.update(intent=intent, composer='table', entity=None, role=None,
                     claim='Same claim with $999 and a question? No implicit effects.', reveal_at=.2)
        beats.append(value)
    result = compile_brief(brief(beats, family='ultimatebet',
                                 cast={'player': 'David Paredes', 'opponent': 'NioNio'}), [], root=workspace)
    assert result['status'] == 'ready'
    assert [d['shot'] for d in result['decisions']] == ['opponent', 'chips', 'overhead', 'cards', 'cards']
    assert all(s['composition_data']['engine'] == 'three' for s in result['plan']['scenes'])
    assert all(s['composition_data']['amount'] == '' for s in result['plan']['scenes'])


@pytest.mark.parametrize('family,cast', [
    ('generic', {}), ('ultimatebet', {}),
    ('ultimatebet', {'player': 'Someone Else', 'opponent': 'NioNio'}),
])
def test_hardcoded_poker_cast_is_never_used_for_unrelated_episodes(workspace, family, cast):
    value = beat()
    value.update(composer='table', entity=None, role=None)
    result = compile_brief(brief([value], family=family, cast=cast), [], root=workspace)
    assert result['status'] == 'blocked' and result['plan'] is None
    assert 'exact supported cast' in result['missing'][0]['reason']


def test_audio_coverage_is_checked_before_preparing_a_plan(workspace):
    value = brief(audio_offset=5)
    with pytest.raises(ValueError, match='shorter'):
        compile_brief(value, [asset(workspace)], root=workspace)


def test_auto_composer_selects_real_video_and_checks_source_stream_coverage(workspace):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('Real stock fixture requires FFmpeg')
    path = workspace / 'stock.mp4'
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=blue:s=320x180:r=30:d=3', '-an', '-c:v', 'libx264',
                    '-preset', 'ultrafast', str(path)], check=True, capture_output=True, timeout=15)
    record = asset(workspace, role='context')
    record.update(path=path.name, sha256=file_hash(path))
    value = beat()
    value.update(composer='auto', role='context', source_start=1, intent='investigate')
    compiled = compile_brief(brief([value]), [record], root=workspace)
    assert compiled['status'] == 'ready'
    scene = compiled['plan']['scenes'][0]
    assert scene['composition'] is None and scene['source_start'] == 1
    assert scene['motion'] == 'pan' and compiled['decisions'][0]['composer'] == 'stock'
    value['source_start'] = 1.1
    blocked = compile_brief(brief([value]), [record], root=workspace)
    assert blocked['plan'] is None
    assert 'shorter' in blocked['missing'][0]['rejected'][0]


def test_records_use_only_the_supported_pillow_comparison(workspace):
    value = beat()
    value.update(composer='records', intent='compare', entity=None, role=None)
    supported = dict(family='ultimatebet', cast={'player': 'David Paredes', 'opponent': 'NioNio'})
    result = compile_brief(brief([value], **supported), [], root=workspace)
    assert result['plan']['scenes'][0]['composition_data']['engine'] == 'pillow'
    value.update(intent='refund', composer='table')
    blocked = compile_brief(brief([value], **supported), [], root=workspace)
    assert blocked['plan'] is None and 'No supported 3D mode' in blocked['missing'][0]['reason']


@pytest.mark.parametrize('duration,offset', [(2, 1), (40, 0)])
def test_auto_filters_ineligible_high_resolution_photo_before_choosing_stock(workspace, duration, offset):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('Real mixed-media fixture requires FFmpeg')
    if duration > 6:
        with wave.open(str(workspace / 'approved.wav'), 'wb') as stream:
            stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            stream.writeframes(bytes(16000 * 2 * (duration + 1)))
    path = workspace / 'footage.mp4'
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    f'color=c=blue:s=320x180:r=30:d={duration + offset + 1}',
                    '-an', '-c:v', 'libx264', '-preset', 'ultrafast', str(path)],
                   check=True, capture_output=True, timeout=15)
    photo = asset(workspace, role='context', size=(1920, 1080))
    video = {**photo, 'id': 'video', 'path': path.name, 'sha256': file_hash(path)}
    value = beat(end=duration)
    value.update(composer='auto', role='context', source_start=offset)
    result = compile_brief(brief([value]), [photo, video], root=workspace)
    assert result['status'] == 'ready'
    assert result['decisions'][0]['composer'] == 'stock'


@pytest.mark.parametrize('change', [
    {'audio_approved': False}, {'duration': 3},
    {'beats': [beat(start=.1)]}, {'beats': [beat(end=2.01)]},
])
def test_invalid_approval_and_timeline_are_rejected(change):
    with pytest.raises(ValueError):
        DirectorBrief.model_validate({**brief(), **change})


def test_prepare_cli_writes_only_local_plan_and_preserves_existing_files(workspace, capsys):
    record = asset(workspace)
    folder = workspace / 'cache/media-library'
    folder.mkdir(parents=True)
    (folder / 'commons-1.json').write_text(json.dumps(record))
    source = workspace / 'brief.json'
    source.write_text(json.dumps(brief()))
    before = source.read_bytes()
    assert cli.main([str(source), '--output', 'prepared.json'], root=workspace) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['provider_requests'] == 0
    plan = EditorialPlan.load(workspace / 'prepared.json')
    assert plan.scenes[0].composition == 'photo'
    assert cli.main([str(source), '--output', str(source)], root=workspace) == 1
    assert source.read_bytes() == before
    assert cli.main([str(source), '--output', 'prepared.json'], root=workspace) == 1
    assert not list(workspace.glob('.director-*'))


def test_blocked_cli_reports_missing_without_writing_partial_plan(workspace, capsys):
    source = workspace / 'brief.json'
    source.write_text(json.dumps(brief()))
    assert cli.main([str(source), '--output', 'prepared.json'], root=workspace) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'blocked' and report['plan'] is None
    assert not (workspace / 'prepared.json').exists()


def test_atomic_output_cannot_escape_root_or_follow_dangling_symlink(workspace):
    dangling = workspace / 'alias.json'
    dangling.symlink_to(workspace / 'new.json')
    with pytest.raises(ValueError, match='symlink'):
        cli.write_new_json(workspace, dangling, {})
    with pytest.raises(ValueError, match='symlink'):
        cli.write_new_json(workspace, Path('alias.json'), {})
    with pytest.raises(ValueError, match='inside'):
        cli.write_new_json(workspace, Path('/tmp/director-escape.json'), {})
    assert not (workspace / 'new.json').exists()
