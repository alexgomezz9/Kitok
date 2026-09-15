import json, pytest
from pathlib import Path
from pydantic import ValidationError
from kitok.models import ContentQueue

def base():
    return {"id":"x_1","subject":"Subject","script":"This is a sufficiently long script for validation.",
            "keywords":["one","two"],"caption":"caption","publish_at":"2026-09-16T13:00:00+02:00"}

def test_duplicates(tmp_path:Path):
    p=tmp_path/"q.json"; x=base(); p.write_text(json.dumps([x,x]),encoding="utf-8")
    with pytest.raises(ValidationError): ContentQueue.load(p)

def test_timezone_required(tmp_path:Path):
    p=tmp_path/"q.json"; x=base(); x["publish_at"]="2026-09-16T13:00:00"
    p.write_text(json.dumps([x]),encoding="utf-8")
    with pytest.raises(ValidationError): ContentQueue.load(p)

def test_keyword_normalization(tmp_path:Path):
    p=tmp_path/"q.json"; x=base(); x["keywords"]=[" QR code ","qr code","","phone"]
    p.write_text(json.dumps([x]),encoding="utf-8")
    assert ContentQueue.load(p).items[0].keywords==["QR code","phone"]
