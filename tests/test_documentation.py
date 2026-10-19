"""Keep current manuals navigable and prevent stale examples/root clutter."""
import json
from pathlib import Path

from scripts.check_documentation import inspect_documents, inspect_examples


def put(root, name, text='fixture'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_current_links_report_missing_and_nonportable_targets(tmp_path):
    put(tmp_path, 'README.md', '[good](docs/current.md) [bad](docs/absent.md) [outside](../private.md)')
    put(tmp_path, 'docs/current.md')
    errors = inspect_documents(tmp_path, ['README.md', 'docs/current.md'])
    assert len(errors) == 2
    assert any('missing local link' in value and 'absent.md' in value for value in errors)
    assert any('nonportable' in value for value in errors)


def test_archive_requires_gateway_and_is_not_a_current_operating_manual(tmp_path):
    put(tmp_path, 'README.md', '[archive](docs/archive/README.md)')
    put(tmp_path, 'docs/archive/README.md', '[old](old.md)')
    put(tmp_path, 'docs/archive/old.md', '[stale reference](removed.md)')
    names=['README.md', 'docs/archive/README.md', 'docs/archive/old.md']
    assert inspect_documents(tmp_path, names) == []
    put(tmp_path, 'README.md', '[old instructions](docs/archive/old.md)')
    assert 'link historical material through' in inspect_documents(tmp_path, names)[0]


def test_auxiliary_root_files_are_rejected_but_private_files_are_not_enumerated(tmp_path):
    put(tmp_path, 'NOTES.md')
    put(tmp_path, '.env', 'this must not be read')
    assert len(inspect_documents(tmp_path, ['NOTES.md'])) == 1
    assert inspect_documents(tmp_path, []) == []


def test_public_brief_schema_is_checked_without_fetching_assets(tmp_path):
    root=Path(__file__).resolve().parents[1]
    brief=json.loads((root/'examples/editorial/brief.json').read_text())
    put(tmp_path, 'examples/editorial/brief.json', json.dumps(brief))
    assert inspect_examples(tmp_path) == []
    brief['beats'][1]['start'] += 1
    put(tmp_path, 'examples/editorial/brief.json', json.dumps(brief))
    assert 'invalid public template' in inspect_examples(tmp_path)[0]


def test_short_example_cannot_silently_use_a_historical_voice_or_auto_schedule(tmp_path):
    row=dict(id='example', subject='A synthetic template', script='A deliberately synthetic narration for this fixture.',
             keywords=['city'], schedule_enabled=False)
    put(tmp_path, 'examples/shorts/queue.json', json.dumps([row]))
    assert 'explicit Fish' in inspect_examples(tmp_path)[0]
    row.update(voice_profile='rick_es')
    put(tmp_path, 'examples/shorts/queue.json', json.dumps([row]))
    assert inspect_examples(tmp_path) == []
    row.update(schedule_enabled=True, publish_at='2030-01-01T12:00:00Z')
    put(tmp_path, 'examples/shorts/queue.json', json.dumps([row]))
    assert 'unscheduled' in inspect_examples(tmp_path)[0]
