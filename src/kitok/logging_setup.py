from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from rich.logging import RichHandler

def configure_logging(logs_dir:Path,verbose=False):
    logs_dir.mkdir(parents=True,exist_ok=True)
    path=logs_dir/f"kitok-{datetime.now().strftime('%Y%m%d')}.log"
    root=logging.getLogger(); root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    rh=RichHandler(rich_tracebacks=True,show_path=False,markup=False)
    rh.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(rh)
    fh=logging.FileHandler(path,encoding="utf-8"); fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root.addHandler(fh)
    return path
