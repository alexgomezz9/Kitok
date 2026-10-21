from dataclasses import replace

from PIL import Image
import pytest

from test_native_recovery import failed_job
from kitok.editing.visual_cues import VisualPlan
from kitok.native_recovery import digest, inspect_remount_narration


def test_remount_audits_successful_source_without_writes_and_detects_image_changes(failed_job):
    studio,definition,narration,_=failed_job
    source=studio.output_path(definition.item.id)
    source.write_bytes(b'previous finished documentary')
    image=studio.root/'images'/'real.png'; image.parent.mkdir()
    Image.new('RGB',(64,64),'gray').save(image)
    target_item=definition.item.model_copy(update={'id':'new_montage'})
    target=replace(definition,item=target_item,visual_root=studio.root,
                   visual_plan=VisualPlan(visual_cues=[{'asset':'images/real.png','start':1}]))
    output=source.with_name('new_montage.mp4')
    before={p:digest(p) for p in studio.root.rglob('*') if p.is_file()}
    confirmed=inspect_remount_narration(studio.s,definition,source,target,output)
    confirmed.verify(target,output)
    assert confirmed.narration==narration and confirmed.sha256==digest(narration)
    assert before=={p:digest(p) for p in studio.root.rglob('*') if p.is_file()}
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        confirmed.verify(target,output)
    assert source.read_bytes()==b'previous finished documentary'
    assert not output.exists()


@pytest.mark.parametrize('change',['script','voice','rate','same_id','existing_target'])
def test_remount_rejects_changed_paid_identity_or_existing_output(failed_job,change):
    studio,definition,narration,_=failed_job
    source=studio.output_path(definition.item.id)
    item=definition.item.model_copy(update={'id':'new_montage'})
    target=replace(definition,item=item)
    output=source.with_name('new_montage.mp4')
    if change=='script':
        target=replace(target,item=item.model_copy(update={'script':'Different script.'}))
    elif change=='voice':
        target=replace(target,voice_name='fish_audio:other:Other')
    elif change=='rate':
        target=replace(target,voice_rate=.8)
    elif change=='same_id':
        target=definition
    elif change=='existing_target':
        output.write_bytes(b'preserve')
    with pytest.raises(ValueError):
        inspect_remount_narration(studio.s,definition,source,target,output)


@pytest.mark.parametrize('old_image_change',['removed','replaced'])
def test_remount_voice_ignores_previous_visual_assets_but_protects_new_images(failed_job,old_image_change):
    studio,source,narration,_=failed_job
    directory=studio.root/'images'; directory.mkdir()
    old_image=directory/'old.png'; new_image=directory/'new.png'
    Image.new('RGB',(64,64),'gray').save(old_image)
    Image.new('RGB',(64,64),'white').save(new_image)
    source=replace(source,visual_root=studio.root,
                   visual_plan=VisualPlan(visual_cues=[{'asset':'images/old.png','start':1}]))
    source_output=studio.output_path(source.item.id); source_output.write_bytes(b'original documentary')
    target=replace(source,item=source.item.model_copy(update={'id':'new_montage'}),
                   visual_plan=VisualPlan(visual_cues=[{'asset':'images/new.png','start':1}]))
    output=source_output.with_name('new_montage.mp4')
    baseline=inspect_remount_narration(studio.s,source,source_output,target,output)
    if old_image_change=='removed':
        old_image.unlink()
    else:
        old_image.write_bytes(b'old visual replaced, no longer an image')
    audit=inspect_remount_narration(studio.s,source,source_output,target,output)
    assert audit.fingerprint==baseline.fingerprint
    baseline.verify(target,output)
    assert digest(narration)==audit.sha256
    assert source_output.read_bytes()==b'original documentary'
    new_image.write_bytes(b'changed target image')
    with pytest.raises(ValueError,match='changed'):
        audit.verify(target,output)
