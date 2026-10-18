from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageStat
from pydantic import ValidationError
import pytest

from kitok.config import Settings
from kitok.editing.cinema import CinemaData, table_frame, render_cinema
from kitok.editing.storyboard import EditorialPlan
from kitok.media.ffmpeg import EncoderSettings
from kitok.media.ffprobe import probe_media


def test_generated_composition_rejects_residual_stock_offset_before_render():
    data=dict(episode_id='fixture', title='Composition', audio_source='approved.mp4',duration=1,
              scenes=[dict(id='one',start=0,end=1,intention='Explain',spoken_claim='Illustration',
                           composition='table',source_start=.5)])
    with pytest.raises(ValidationError,match='source_start=0'):
        EditorialPlan.model_validate(data)


@pytest.mark.parametrize('mode,width,height,message', [
    ('refunds', 1920, 1080, 'Unsupported 3D table mode'),
    ('private', 3840, 2160, 'at most 1920x1080'),
])
def test_unsupported_3d_inputs_fail_before_creating_a_render(mode, width, height, message):
    data = dict(episode_id='fixture', title='Composition', audio_source='approved.mp4',
                duration=1, width=width, height=height,
                scenes=[dict(id='one', start=0, end=1, intention='Explain',
                             spoken_claim='Illustration', composition='table',
                             composition_data=dict(mode=mode, engine='three'))])
    with pytest.raises(ValidationError, match=message):
        EditorialPlan.model_validate(data)


def test_private_cards_change_only_after_the_approved_reveal():
    private=table_frame(CinemaData(mode='private'),2.8,5)
    exposed=table_frame(CinemaData(mode='exposed',reveal_at=1),2.8,5)
    assert private.size==exposed.size==(1920,1080)
    # Same camera/time: opposing card interiors are dark until revealed.
    region=(1320,710,1500,820)
    assert ImageStat.Stat(exposed.crop(region).convert('L')).mean[0] > ImageStat.Stat(private.crop(region).convert('L')).mean[0]+30
    late=table_frame(CinemaData(mode='exposed',reveal_at=4),2.8,5)
    assert late.tobytes()==private.tobytes()


def test_real_photo_scene_renders_frames_and_reuses_verified_receipt(tmp_path):
    source=tmp_path/'licensed.jpg';Image.new('RGB',(640,480),'#447799').save(source)
    output=tmp_path/'scene.mp4';settings=Settings(_env_file=None,data_root=tmp_path)
    data=CinemaData(mode='profile',label='Fixture identity',credit='Synthetic test image')
    args=dict(duration=.5,width=640,height=480,fps=24,output=output,settings=settings,
              encoder=EncoderSettings(codec='libx264',preset='ultrafast'),photo=source)
    render_cinema(data,'photo',**args)
    stat=output.stat()
    info=probe_media(output,'ffprobe')
    assert abs(info.duration-.5)<.05 and (info.width,info.height)==(640,480)
    render_cinema(data,'photo',**args)
    assert output.stat().st_mtime_ns==stat.st_mtime_ns
