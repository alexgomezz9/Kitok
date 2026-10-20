import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from kitok.config import Settings
from kitok.editing.storyboard import EditorialPlan, phrase_time, project_file
from kitok.editing.production import render_editorial_plan
from kitok.editing.quality import decoded_audio_hash, inspect_video


def payload():
    return {"episode_id":"fixture","title":"A fixture","duration":2,"audio_source":"audio.mp4",
            "width":640,"height":480,
            "assets":{"clip":{"path":"source.mp4","description":"Synthetic test media"}},
            "scenes":[{"id":"one","start":0,"end":1,"intention":"Explain an identity","spoken_claim":"A fictional name.",
                       "graphic":"identity","graphic_data":{"name":"Fixture","eyebrow":"EXPLANATION"}},
                      {"id":"two","start":1,"end":2,"intention":"Return to the scene","spoken_claim":"Illustrative stock.",
                       "asset":"clip","motion":"push"}]}


@pytest.mark.parametrize("change",["gap","overlap","duplicate","missing_asset","nan","too_short","odd_geometry","missing_visual"])
def test_plan_rejects_broken_timeline_and_inputs(change):
    data=payload()
    if change=="gap": data["scenes"][1]["start"]=1.5
    if change=="overlap": data["scenes"][1]["start"]=.5
    if change=="duplicate":data["scenes"][1]["id"]="one"
    if change=="missing_asset":data["scenes"][1]["asset"]="absent"
    if change=="nan":data["scenes"][1]["end"]=float("nan")
    if change=="too_short":data["scenes"][0]["end"]=.2
    if change=="odd_geometry":data["width"]=641
    if change=="missing_visual":data["scenes"][1].pop("asset")
    with pytest.raises(ValidationError):
        EditorialPlan.model_validate(data)


def test_provider_anchors_accept_real_zero_length_tokens_without_inventing_alignment():
    words=[{"word":"Twenty-two","start":1.0,"end":1.4},
           {"word":"million","start":1.4,"end":1.4},{"word":"dollars.","start":1.6,"end":2.2}]
    assert phrase_time(words,"twenty two million dollars")== (1.,2.2)
    with pytest.raises(ValueError,match="not found"):
        phrase_time(words,"another amount")


def test_plan_cannot_read_media_outside_project(tmp_path):
    outside=tmp_path/"outside.txt"
    outside.write_text("fixture")
    root=tmp_path/"project";root.mkdir()
    with pytest.raises(ValueError,match="existing project"):
        project_file(root,str(outside))


@pytest.mark.parametrize('changed', ['audio', 'asset'])
def test_approved_input_hash_is_checked_before_any_render_output(tmp_path, monkeypatch, changed):
    from kitok.editing.storyboard import file_hash
    from kitok.editing import production
    for name in ('audio.mp4', 'source.mp4'):
        (tmp_path / name).write_bytes(b'approved bytes')
    data = payload()
    data['alignment'] = {'audio_sha256': file_hash(tmp_path / 'audio.mp4')}
    data['assets']['clip']['sha256'] = file_hash(tmp_path / 'source.mp4')
    (tmp_path / ('audio.mp4' if changed == 'audio' else 'source.mp4')).write_bytes(b'changed resource')
    monkeypatch.setattr(production, 'probe_media', lambda *a: SimpleNamespace(audio_codec='aac', duration=2))
    monkeypatch.setattr(production, 'stream_durations', lambda *a: (2, 2))
    monkeypatch.setattr(production, '_run', lambda *a, **k: pytest.fail('No rendering before hash validation'))
    output = tmp_path / 'outputs' / 'blocked.mp4'
    with pytest.raises(ValueError, match='changed after preparing'):
        render_editorial_plan(EditorialPlan.model_validate(data), root=tmp_path, output=output,
                              settings=Settings(_env_file=None, data_root=tmp_path))
    assert not output.parent.exists()


@pytest.mark.parametrize('racing', ['video', 'receipt'])
def test_exclusive_promotion_preserves_files_created_during_render(tmp_path, racing):
    from kitok.editing.production import _publish_new
    pending, output, receipt = (tmp_path / name for name in ('pending.mp4', 'final.mp4', 'final.editorial.json'))
    pending.write_bytes(b'rendered video')
    protected = output if racing == 'video' else receipt
    protected.write_bytes(b'operator file created during rendering')
    with pytest.raises(FileExistsError):
        _publish_new(pending, output, receipt, {'episode_id': 'new'})
    assert protected.read_bytes() == b'operator file created during rendering'
    assert not (receipt if racing == 'video' else output).exists()
    assert not pending.exists()


def test_exclusive_promotion_keeps_a_receipt_replaced_by_another_writer(tmp_path, monkeypatch):
    from kitok.editing.production import _publish_new
    import os
    pending, output, receipt = (tmp_path / name for name in ('pending.mp4', 'final.mp4', 'final.editorial.json'))
    pending.write_bytes(b'rendered video')
    link = os.link
    def concurrent(source, destination):
        if destination == output:
            replacement = tmp_path / 'other.json'
            replacement.write_bytes(b'another writer receipt')
            replacement.replace(receipt)
            raise FileExistsError('Output appeared concurrently')
        return link(source, destination)
    monkeypatch.setattr('kitok.editing.production.os.link', concurrent)
    with pytest.raises(FileExistsError):
        _publish_new(pending, output, receipt, {'episode_id': 'new'})
    assert receipt.read_bytes() == b'another writer receipt'


def test_quality_samples_long_scene_lists_instead_of_failing_after_render(tmp_path, monkeypatch):
    from kitok.editing import quality
    monkeypatch.setattr(quality, 'probe_media', lambda *args: SimpleNamespace(
        video_codec='h264', audio_codec='aac', duration=100, width=1920, height=1080, fps=30))
    monkeypatch.setattr(quality.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stderr=''))
    monkeypatch.setattr(quality, 'measure_loudness', lambda *args: {})
    monkeypatch.setattr(quality, 'stream_durations', lambda *args: (100, 100))
    monkeypatch.setattr(quality, 'decoded_audio_hash', lambda *args: 'same')
    monkeypatch.setattr(quality, 'file_hash', lambda *args: 'media-digest')
    captured = []
    def contact(video, output, times, **kwargs):
        assert 1 <= len(times) <= 80
        captured.extend(times)
        return output
    monkeypatch.setattr(quality, 'contact_sheet', contact)
    report = inspect_video(tmp_path/'fixture.mp4', tmp_path/'qa.json',
             settings=Settings(_env_file=None, data_root=tmp_path),
             scene_boundaries=[i+.5 for i in range(100)])
    assert captured[0] == .5 and captured[-1] == 99.5
    assert report['contact_sampling'] == dict(available_points=100, sampled_points=80, exhaustive=False)


def test_real_render_uses_existing_audio_reuses_scenes_and_repair_invalidates_only_changed_scene(tmp_path):
    source=tmp_path/"source.mp4"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc2=s=640x480:r=30:d=3",
                    "-f","lavfi","-i","sine=frequency=440:duration=3","-c:v","libx264","-preset","ultrafast",
                    "-threads","1","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(source)],check=True,timeout=30)
    reference=tmp_path/"audio.mp4"
    subprocess.run(["ffmpeg","-v","error","-i",str(source),"-t","2","-c","copy",str(reference)],check=True,timeout=30)
    settings=Settings(_env_file=None,data_root=tmp_path)
    plan=EditorialPlan.model_validate(payload())
    output=tmp_path/"first.mp4"
    result=render_editorial_plan(plan,root=tmp_path,output=output,settings=settings,encoder_name="libx264")
    assert result["provider_requests"]==0 and result["rendered_scenes"]==["one","two"]
    assert decoded_audio_hash(output)==decoded_audio_hash(reference)
    second=render_editorial_plan(plan,root=tmp_path,output=tmp_path/"second.mp4",settings=settings,encoder_name="libx264")
    assert second["reused_scenes"]==["one","two"] and second["rendered_scenes"]==[]
    revised=plan.model_copy(deep=True)
    revised.scenes[1].motion="none"
    third=render_editorial_plan(revised,root=tmp_path,output=tmp_path/"third.mp4",settings=settings,encoder_name="libx264")
    assert third["reused_scenes"]==["one"] and third["rendered_scenes"]==["two"]
    before=source.read_bytes()
    with pytest.raises(ValueError,match="replace an input"):
        render_editorial_plan(plan,root=tmp_path,output=source,settings=settings,encoder_name="libx264")
    assert source.read_bytes()==before
    report=inspect_video(output,tmp_path/"qa.json",settings=settings,comparison=reference,scene_boundaries=[.5,1.5])
    assert report["full_decode"]=="passed" and report["comparison"]["audio_identical"]
    assert Path(report["contact_sheet"]).is_file()


def test_each_scene_uses_one_global_frame_grid_and_no_per_seam_gap_tolerance():
    from kitok.editing.storyboard import frame_time
    data=payload()
    data["scenes"][0]["end"]=.99
    data["scenes"][1]["start"]=1.0
    with pytest.raises(ValidationError):
        EditorialPlan.model_validate(data)
    data=payload()
    data["duration"]=.41*15
    template=data["scenes"][0]
    data["scenes"]=[{**template,"id":f"s{i}","start":i*.41,"end":(i+1)*.41} for i in range(15)]
    with pytest.raises(ValidationError,match="frame grid"):
        EditorialPlan.model_validate(data)
    assert frame_time(.41)==12/30
    # Quantizing shared boundaries produces one exact total instead of cumulative drift.
    boundaries=[frame_time(i*.41) for i in range(16)]
    assert sum(b-a for a,b in zip(boundaries,boundaries[1:]))==pytest.approx(boundaries[-1])


def test_video_container_duration_cannot_hide_short_audio(tmp_path):
    source=tmp_path/"audio.mp4"
    subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc2=s=640x480:r=30:d=3",
                    "-f","lavfi","-i","sine=frequency=440:duration=0.5","-c:v","libx264",
                    "-preset","ultrafast","-threads","1","-c:a","aac",str(source)],check=True,timeout=30)
    (tmp_path/"source.mp4").write_bytes(source.read_bytes())
    with pytest.raises(ValueError,match="audio does not cover"):
        render_editorial_plan(EditorialPlan.model_validate(payload()),root=tmp_path,
          output=tmp_path/"must-not-exist.mp4",settings=Settings(_env_file=None,data_root=tmp_path),
          encoder_name="libx264")
    assert not (tmp_path/"must-not-exist.mp4").exists()


def test_quantized_minimum_scenes_render_without_float_drift(tmp_path):
    from kitok.editing.storyboard import frame_time
    from kitok.media.ffprobe import stream_durations
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=640x480:r=30:d=7',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=7', '-c:v', 'libx264',
                    '-preset', 'ultrafast', '-threads', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    '-shortest', str(source)], check=True, timeout=30)
    boundaries = [frame_time(i * .41) for i in range(16)]
    data = payload()
    data.update(duration=boundaries[-1], audio_source='source.mp4')
    data['scenes'] = [dict(id=f's{i}', start=a, end=b, intention='Short shot',
                           spoken_claim='Illustrative fixture', asset='clip')
                      for i, (a, b) in enumerate(zip(boundaries, boundaries[1:]))]
    plan = EditorialPlan.model_validate(data)
    output = tmp_path / 'quantized.mp4'
    result = render_editorial_plan(plan, root=tmp_path, output=output,
              settings=Settings(_env_file=None, data_root=tmp_path), encoder_name='libx264')
    video, audio = stream_durations(output, 'ffprobe')
    assert len(result['rendered_scenes']) == 15
    assert abs(video - plan.duration) < 1 / plan.fps + .02
    assert audio >= plan.duration - .05


@pytest.mark.parametrize('suffix,codec', [('.wav','pcm_s16le'),('.m4a','aac')])
def test_approved_audio_has_browser_aac_delivery_without_changing_master(tmp_path,suffix,codec):
    source=tmp_path/f'approved{suffix}'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=230:duration=2',
                    '-c:a',codec,str(source)],check=True,timeout=30)
    original=source.read_bytes()
    plan=EditorialPlan.model_validate(dict(episode_id='browser',title='Browser delivery',
        audio_source=source.name,audio_is_final_mix=True,duration=2,width=640,height=480,
        scenes=[dict(id='one',start=0,end=2,intention='Known identity',spoken_claim='A test name',
                     graphic='identity',graphic_data={'name':'Test'})]))
    output=tmp_path/'delivery.mp4'
    result=render_editorial_plan(plan,root=tmp_path,output=output,
        settings=Settings(_env_file=None,data_root=tmp_path),encoder_name='libx264')
    from kitok.media.ffprobe import probe_media
    assert probe_media(output,'ffprobe').audio_codec=='aac'
    assert source.read_bytes()==original
    if codec=='aac':
        assert decoded_audio_hash(source)==decoded_audio_hash(output)
        assert result['audio_delivery']=='copied-aac'
    else:
        assert result['audio_delivery']=='encoded-aac-without-normalization'
