"""Restart-safe claims and honest visual acceptance; fixture PNGs are technical only."""
from __future__ import annotations

import pytest
from PIL import Image

from kitok.youtube_stickman_es.files import digest, episode_lock
from kitok.youtube_stickman_es.images import ImageBatch
from kitok.youtube_stickman_es.models import Config, Reference
from kitok.youtube_stickman_es.packaging import prepare_packaging
from kitok.youtube_stickman_es.planner import plan_illustrations


@pytest.fixture
def batch(tmp_path, request):
    episode = tmp_path / 'episode'
    episode.mkdir()
    script = 'Una explicación aprobada sin datos inventados.'
    (episode / 'guion_final.txt').write_text(script)
    Image.new('RGB', (1280, 720), '#eeeedd').save(episode / 'reference.png')
    config = Config(references=[Reference(path='reference.png', role=getattr(request, 'param', 'interior'))])
    narration = {'duration': 30., 'cues': [{'start': i * 2., 'end': (i + 1) * 2.,
                 'text': f'Explicación {i}.'} for i in range(15)], 'audio_sha256': 'audio',
                 'srt_sha256': 'srt', 'alignment_method': 'real_srt'}
    args = dict(title='Título aprobado', script=script, narration=narration, config=config)
    draft = plan_illustrations(episode, **args)
    directions = [{'scene_id': s.id, 'visual_description': 'Un personaje contempla el mecanismo explicado.',
                   'scene_prompt': 'An anonymous stickman examines the approved explanatory mechanism.',
                   'characters': []} for s in draft.scenes]
    plan = plan_illustrations(episode, **args, directions=directions)
    prepare_packaging(episode, title=plan.title, script=script, duration=plan.duration,
                      scenes=[s.model_dump() for s in plan.scenes], references=plan.references)
    # Direct ImageBatch mutations obey the public caller's lock contract.
    with episode_lock(episode):
        yield ImageBatch(episode, plan, config)


def source_image(batch, index=0):
    path = batch.episode / f'technical_fixture_{index}.png'
    Image.new('RGB', (1280, 720), (20 + index, 70, 90)).save(path)
    return path


def complete(batch, ident, index, *, reviewed=True, cost=None):
    claim = batch.claim(ident)
    return batch.import_image(ident, source_image(batch, index), attempt_id=claim['attempt_id'],
                              reviewed=reviewed, reported_cost=cost)


def approve(batch):
    for index, ident in enumerate(batch.samples):
        complete(batch, ident, index)
    return batch.approve_style(reviewer='Visual reviewer')


def test_only_first_middle_last_eligible_before_style_approval(batch):
    assert batch.samples == [batch.plan.scenes[i].id for i in (0, 3, 5)]
    status = batch.status()
    assert {r['id'] for r in status['jobs'] if r['eligible']} == set(batch.samples)
    assert status['generation_cost'] is None
    assert not status['render_images_ready']
    with pytest.raises(ValueError, match='representative style sample'):
        batch.claim(batch.plan.scenes[1].id)
    with pytest.raises(ValueError, match='representative style sample'):
        batch.claim('thumb_A')


def test_claim_persists_across_resume_and_never_automatically_resubmits(batch):
    ident = batch.samples[0]
    request = batch.claim(ident)
    assert request['tool'] == 'image_gen.imagegen'
    assert request['arguments']['referenced_image_paths'] == [str(batch.episode / 'reference.png')]
    resumed = ImageBatch(batch.episode, batch.plan, batch.config)
    assert not next(r for r in resumed.status()['jobs'] if r['id'] == ident)['eligible']
    with pytest.raises(ValueError, match='Previous attempt needs review'):
        resumed.claim(ident)
    resumed.mark_unknown(ident, attempt_id=request['attempt_id'], reason='Tool result interrupted')
    with pytest.raises(ValueError, match='Previous attempt needs review'):
        resumed.claim(ident)
    resumed.import_image(ident, source_image(batch), attempt_id=request['attempt_id'], reviewed=True)
    with pytest.raises(ValueError, match='already complete'):
        resumed.claim(ident)


def test_retries_need_explicit_reason_and_stop_after_three_attempts(batch):
    ident = batch.samples[0]
    for attempt in range(1, 4):
        request = batch.claim(ident)
        assert batch._read()['jobs'][ident]['attempts'] == attempt
        batch.mark_unknown(ident, attempt_id=request['attempt_id'], reason='Unknown result')
        with pytest.raises(ValueError, match='Retry needs'):
            batch.retry(ident, reason='   ')
        if attempt < 3:
            batch.retry(ident, reason='Reviewed missing result; permit another attempt')
    with pytest.raises(ValueError, match='Retry needs'):
        batch.retry(ident, reason='Fourth request')
    assert len(batch._read()['jobs'][ident]['history']) == 2


def test_retry_invalidates_prior_attempt_result_without_accepting_it(batch):
    ident = batch.samples[0]
    stale = batch.claim(ident)
    batch.retry(ident, reason='Operator reviewed interrupted request')
    active = batch.claim(ident)
    assert active['attempt_id'] != stale['attempt_id']
    with pytest.raises(ValueError, match='active attempt'):
        batch.import_image(ident, source_image(batch), attempt_id=stale['attempt_id'], reviewed=True)
    assert not (batch.episode / batch.jobs[ident]['image_file']).exists()


def test_style_approval_requires_reviewed_images_and_survives_new_imports(batch):
    for index, ident in enumerate(batch.samples):
        complete(batch, ident, index, reviewed=index != 1)
    with pytest.raises(ValueError, match='Review every'):
        batch.approve_style(reviewer='Reviewer')
    # Reject and explicitly retry the image that did not pass human review.
    ident = batch.samples[1]
    batch.reject(ident, reason='Visual inspection incomplete')
    batch.retry(ident, reason='New reviewed illustration required')
    complete(batch, ident, 9)
    receipt = batch.approve_style(reviewer='Reviewer')
    assert receipt['plan_sha256'] == digest(batch.plan.model_dump())
    assert set(receipt['sample_hashes']) == set(batch.samples)
    extra = batch.plan.scenes[1].id
    request = batch.claim(extra)
    assert all(str(batch.episode / batch.jobs[i]['image_file']) in request['arguments']['referenced_image_paths']
               for i in batch.samples)
    batch.import_image(extra, source_image(batch, 20), attempt_id=request['attempt_id'], reviewed=False)
    assert batch.approval() == receipt
    assert not batch.status()['render_images_ready']
    with pytest.raises(ValueError, match='immutable'):
        batch.reject(batch.samples[0], reason='Change approved style')


@pytest.mark.parametrize('changed', ['reference', 'config', 'plan', 'sample'])
def test_changed_pinned_inputs_or_approved_images_block_resume(batch, changed):
    approve(batch)
    if changed == 'reference':
        Image.new('RGB', (1280, 720), 'green').save(batch.episode / 'reference.png')
        with pytest.raises(ValueError, match='reference changed'):
            ImageBatch(batch.episode, batch.plan, batch.config)
    elif changed == 'config':
        config = batch.config.model_copy(update={'style_prompt': 'A different style'})
        with pytest.raises(ValueError, match='configuration changed'):
            ImageBatch(batch.episode, batch.plan, config)
    elif changed == 'plan':
        plan = batch.plan.model_copy(update={'title': 'Different title'})
        with pytest.raises(ValueError, match='stale|different inputs'):
            ImageBatch(batch.episode, plan, batch.config).status()
    else:
        path = batch.episode / batch.jobs[batch.samples[0]]['image_file']
        Image.new('RGB', (1280, 720), 'green').save(path)
        with pytest.raises(ValueError, match='accepted image changed'):
            batch.status()


@pytest.mark.parametrize('kind', ['corrupt', 'aspect', 'small', 'symlink'])
def test_import_rejects_invalid_image_without_changing_original_or_claim(batch, kind):
    ident = batch.samples[0]
    request = batch.claim(ident)
    source = batch.episode / 'invalid.png'
    if kind == 'corrupt':
        source.write_bytes(b'not an image')
    elif kind == 'symlink':
        source.symlink_to(source_image(batch))
    else:
        Image.new('RGB', (1280, 800) if kind == 'aspect' else (640, 360)).save(source)
    before = source.read_bytes()
    with pytest.raises(ValueError):
        batch.import_image(ident, source, attempt_id=request['attempt_id'], reviewed=True)
    assert source.read_bytes() == before
    assert batch._read()['jobs'][ident]['status'] == 'claimed'
    assert not (batch.episode / batch.jobs[ident]['image_file']).exists()


def test_duplicate_pixels_rejected_across_scene_ids(batch):
    complete(batch, batch.samples[0], 0)
    ident = batch.samples[1]
    request = batch.claim(ident)
    # Different PNG encoding bytes of the same pixels must normalize identically.
    alternate = batch.episode / 'same_pixels.png'
    with Image.open(source_image(batch, 0)) as image:
        image.save(alternate, compress_level=0)
    with pytest.raises(ValueError, match='exact image'):
        batch.import_image(ident, alternate, attempt_id=request['attempt_id'], reviewed=True)
    assert alternate.exists()


def test_rejection_archives_accepted_image_and_preserves_original_input(batch):
    ident = batch.samples[0]
    row = complete(batch, ident, 0)
    original = source_image(batch, 0)
    before = original.read_bytes()
    batch.reject(ident, reason='Character identity does not match reference')
    rejected = batch._read()['jobs'][ident]
    archive = batch.episode / rejected['rejected_file']
    assert rejected['status'] == 'failed' and not rejected['reviewed']
    assert digest(archive) == row['sha256']
    assert original.read_bytes() == before
    assert not (batch.episode / row['file']).exists()
    with pytest.raises(ValueError, match='Previous attempt needs review'):
        batch.claim(ident)


def test_render_readiness_needs_every_scene_review_and_cost_is_not_invented(batch):
    approve(batch)
    for index, scene in enumerate(batch.plan.scenes):
        if scene.id not in batch.samples:
            complete(batch, scene.id, index + 30, cost=.2)
    status = batch.status()
    assert status['render_images_ready']
    assert status['generation_cost'] is None  # Sample tool never reported its cost.
    assert all(r['status'] == 'pending' for r in status['jobs'] if r['kind'] == 'thumbnail')


@pytest.mark.parametrize('cost', [-1, float('nan'), float('inf')])
def test_cost_must_be_real_nonnegative_tool_receipt(batch, cost):
    ident = batch.samples[0]
    request = batch.claim(ident)
    with pytest.raises(ValueError, match='Reported cost'):
        batch.import_image(ident, source_image(batch), attempt_id=request['attempt_id'], reviewed=True,
                           reported_cost=cost)


@pytest.mark.parametrize('batch', ['thumbnail'], indirect=True)
def test_thumbnail_only_reference_cannot_approve_interior_style(batch):
    for index, ident in enumerate(batch.samples):
        complete(batch, ident, index)
    with pytest.raises(ValueError, match='Interior-frame references'):
        batch.approve_style(reviewer='Reviewer')
    assert not batch.approval_path.exists()


def test_import_preserves_preexisting_destination_on_collision(batch):
    ident = batch.samples[0]
    request = batch.claim(ident)
    target = batch.episode / batch.jobs[ident]['image_file']
    target.parent.mkdir(exist_ok=True)
    Image.new('RGB', (1280, 720), 'orange').save(target)
    before = target.read_bytes()
    with pytest.raises(FileExistsError, match='preserved without overwriting'):
        batch.import_image(ident, source_image(batch), attempt_id=request['attempt_id'], reviewed=True)
    assert target.read_bytes() == before
    assert batch._read()['jobs'][ident]['status'] == 'claimed'


def test_explicit_adoption_recovers_result_already_at_destination(batch):
    ident = batch.samples[0]
    request = batch.claim(ident)
    target = batch.episode / batch.jobs[ident]['image_file']
    target.parent.mkdir(exist_ok=True)
    Image.new('RGB', (1280, 720), 'orange').save(target)
    before = target.read_bytes()
    batch.mark_unknown(ident, attempt_id=request['attempt_id'], reason='Receipt was interrupted')
    row = batch.import_image(ident, target, attempt_id=request['attempt_id'], reviewed=True, reported_cost=.3)
    assert row['status'] == 'complete' and row['sha256'] == digest(target)
    assert target.read_bytes() == before
    assert batch.status()['generation_cost'] == pytest.approx(.3)


def test_import_then_explicit_review_does_not_require_regeneration(batch):
    ident=batch.samples[0]
    row=complete(batch,ident,0,reviewed=False)
    before=digest(batch.episode/row['file'])
    batch.review(ident,reviewer='Actual visual inspection')
    assert batch._read()['jobs'][ident]['reviewed']
    assert digest(batch.episode/row['file'])==before
    assert batch._read()['jobs'][ident]['attempts']==1


def test_rejected_attempt_costs_are_retained_when_reported(batch):
    ident=batch.samples[0]
    complete(batch,ident,0,cost=.1)
    batch.reject(ident,reason='Wrong pose')
    batch.retry(ident,reason='Explicitly approve another image attempt')
    assert batch.status()['generation_cost']==pytest.approx(.1)
    complete(batch,ident,2,cost=.2)
    assert batch.status()['generation_cost']==pytest.approx(.3)


def test_active_thumbnail_attempt_is_bound_to_its_concept_and_destination(batch):
    import json
    approve(batch)
    request=batch.claim('thumb_A')
    path=batch.episode/'miniaturas/conceptos.json'
    data=json.loads(path.read_text())
    data['concepts'][0]['prompt']='Changed instructions after the image request was reserved.'
    data['concepts'][0]['background_file']='miniaturas/changed_destination.png'
    path.write_text(json.dumps(data))
    changed=ImageBatch(batch.episode,batch.plan,batch.config)
    with pytest.raises(ValueError,match='different inputs'):
        changed.import_image('thumb_A',source_image(batch,20),attempt_id=request['attempt_id'],reviewed=True)
    assert not (batch.episode/'miniaturas/changed_destination.png').exists()


@pytest.mark.parametrize('damage',['missing','corrupt'])
def test_non_sample_damage_can_be_quarantined_and_retried_without_regenerating_valid_images(batch,damage):
    for index,ident in enumerate(batch.samples):complete(batch,ident,index)
    batch.approve_style(reviewer='Visual sample reviewed')
    ident=next(s.id for s in batch.plan.scenes if s.id not in batch.samples)
    complete(batch,ident,20)
    path=batch.episode/batch.jobs[ident]['image_file']
    if damage=='missing':path.unlink()
    else:path.write_bytes(b'corrupt image, retain this evidence')
    batch.reject(ident,reason='Corrupt or missing generated resource')
    batch.retry(ident,reason='Explicit repair of only this resource')
    complete(batch,ident,21)
    assert batch.status()['style_approved']
    assert all(batch._read()['jobs'][sample]['attempts']==1 for sample in batch.samples)


def test_unknown_image_id_does_not_create_state(batch):
    with pytest.raises(ValueError, match='Unknown planned image'):
        batch.claim('../../outside')
    assert not batch.state_path.exists()


def test_native_small_source_is_supported_without_weakening_generated_delivery(tmp_path):
    path = tmp_path / 'small.png'
    Image.new('RGB', (549, 305), 'white').save(path)
    before = path.read_bytes()
    info = ImageBatch.inspect(path, require_delivery_size=False)
    assert (info['width'], info['height']) == (549, 305)
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match='1280x720'):
        ImageBatch.inspect(path)
    path.write_bytes(b'invalid')
    with pytest.raises(ValueError):
        ImageBatch.inspect(path, require_delivery_size=False)


def test_provided_collection_keeps_native_bytes_and_reports_small_sources(batch):
    originals = {}
    for scene in batch.plan.scenes:
        path = batch.episode / scene.image_file
        path.parent.mkdir(exist_ok=True)
        Image.new('RGB', (549, 305), 'ivory').save(path)
        originals[path] = path.read_bytes()
    result = batch.adopt_provided()
    assert result['render_images_ready'] and result['assembly_authorized']
    assert len(result['resolution_warnings']) == len(batch.plan.scenes)
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert batch.status()['render_images_ready']
