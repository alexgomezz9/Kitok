from kitok.file_manager import output_filename
from kitok.models import ContentItem

def test_filename():
    i=ContentItem.model_validate({"id":"voz_001","subject":"s",
       "script":"This is a sufficiently long script for validation.","keywords":["x"],
       "publish_at":"2026-09-16T13:00:00+02:00"})
    assert output_filename(i)=="2026-09-16_13-00__voz_001.mp4"
