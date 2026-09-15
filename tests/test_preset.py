import json, pytest
from pathlib import Path
from kitok.pipeline import load_preset

def test_forbidden(tmp_path:Path):
    p=tmp_path/"p.json"; p.write_text(json.dumps({"video_subject":"bad"}))
    with pytest.raises(ValueError): load_preset(p)

def test_ok(tmp_path:Path):
    p=tmp_path/"p.json"; p.write_text(json.dumps({"video_aspect":"9:16","font_size":85}))
    assert load_preset(p)["font_size"]==85
