from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..config import PROJECT_ROOT
from .pipeline import execute
from .progress import TerminalProgress


def main(argv=None):
    parser = argparse.ArgumentParser(description='Kitok youtube_stickman_es: episode preparation, resumable images and shared Native render.')
    parser.add_argument('command', choices=['init','prepare','produce','resume','render','status','request','request-next',
                                           'import-image','review-image','approve-style','reject','retry','unknown','package'])
    parser.add_argument('episode',type=Path,help='Episode folder inside the Kitok workspace')
    parser.add_argument('--quiet', action='store_true', help='Hide human progress on stderr; keep final JSON')
    parser.add_argument('--generate-voice',action='store_true',help='Explicitly allow configured Fish only if voz.mp3 is absent')
    parser.add_argument('--revision',help='prepare/produce/resume: isolated episode snapshot; render: new MP4 suffix')
    parser.add_argument('--reuse-images',action='store_true',help='Authorize assembly of supplied images using plan_visual.json or the original visual plan; no generation or visual QA')
    parser.add_argument('--image-id')
    parser.add_argument('--source',type=Path,help='Actual output from Codex image generation; no provider is contacted')
    parser.add_argument('--attempt-id')
    parser.add_argument('--reviewed',action='store_true',help='Record actual visual inspection; not automatic model QA')
    parser.add_argument('--reported-cost',type=float,help='Only if the tool actually supplies a cost; otherwise unknown')
    parser.add_argument('--source-kind',choices=['builtin_imagegen','provided','technical_fixture'],default='provided')
    parser.add_argument('--reviewer',help='Identified reviewer who approved the representative style sample')
    parser.add_argument('--reason')
    args = vars(parser.parse_args(argv))
    command, episode = args.pop('command'), args.pop('episode')
    required = {'request':['image_id'],'import-image':['image_id','source','attempt_id'],
                'approve-style':['reviewer'],'reject':['image_id','reason'],'retry':['image_id','reason'],
                'review-image':['image_id','reviewer'],
                'unknown':['image_id','attempt_id','reason']}
    for name in required.get(command,[]):
        if args.get(name) is None:
            parser.error('--'+name.replace('_','-')+' is required for '+command)
    quiet = args.pop('quiet')
    try:
        with TerminalProgress(enabled=not quiet) as progress:
            progress(f'Kitok · {command} · {episode.name}')
            result = execute(PROJECT_ROOT,episode,command,on_stage=progress,**args)
            progress(f'Comando terminado · estado: {result.get("status", result.get("technical_status", "consulta completada"))}')
    except (ValueError,OSError,RuntimeError) as error:
        print(json.dumps({'status':'blocked','error':str(error)},ensure_ascii=False),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
