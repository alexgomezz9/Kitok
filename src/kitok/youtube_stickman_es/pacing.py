"""Audit time on distinct illustrations; camera cuts cannot hide a long hold."""
from pathlib import Path

from .files import digest, local_file
from .models import IllustrationPlan


def pacing_report(episode: Path, plan: IllustrationPlan, *, verify_images=False) -> dict:
    identities = {}
    holds = []
    for scene in plan.scenes:
        if scene.image_file not in identities:
            identities[scene.image_file] = (digest(local_file(episode, scene.image_file))
                                            if verify_images else scene.image_file)
        identity = identities[scene.image_file]
        if holds and holds[-1]['identity'] == identity:
            holds[-1]['end'] = scene.end
        else:
            holds.append({'identity': identity, 'start': scene.start, 'end': scene.end})
    bands, violations = [], []
    for start, end, mean_limit, hold_limit in ((0, 30, 2.5, 3.5), (30, 60, 3.5, 5),
                                               (60, plan.duration, 7, 9)):
        end = min(end, plan.duration)
        if end <= start:
            continue
        overlapping = [h for h in holds if h['start'] < end and h['end'] > start]
        # Fractional pieces at band boundaries carry only their actual screen time.
        lengths = [min(h['end'], end)-max(h['start'], start) for h in overlapping]
        mean = sum(lengths)/len(lengths)
        # A band edge cannot turn a long uninterrupted hold into two short ones.
        maximum = max(h['end']-h['start'] for h in overlapping)
        unique = len({h['identity'] for h in overlapping})
        # Repeated non-adjacent images do not provide the requested new illustrations.
        distinct_mean = (end-start)/unique
        row = {'from': start, 'to': end, 'image_runs': len(lengths), 'distinct_images': unique,
               'mean_seconds': round(mean, 3), 'seconds_per_distinct_image': round(distinct_mean, 3),
               'longest_hold_seconds': round(maximum, 3), 'mean_limit': mean_limit,
               'hold_limit': hold_limit}
        bands.append(row)
        if distinct_mean > mean_limit+1e-6 or maximum > hold_limit+1e-6:
            violations.append(f'{start:g}-{end:g}s: {unique} distinct images, '
                              f'{distinct_mean:.2f}s/image, longest hold {maximum:.2f}s; '
                              f'limits {mean_limit:g}s/image and {hold_limit:g}s/hold')
    return {'policy': 'trazo_dynamic_v1', 'identity_basis': 'sha256' if verify_images else 'source_path',
            'images_verified': verify_images, 'status': 'passed' if not violations else 'needs_review',
            'bands': bands, 'violations': violations}


def require_pacing(episode: Path, plan: IllustrationPlan, *, verify_images=False) -> dict:
    report = pacing_report(episode, plan, verify_images=verify_images)
    if report['violations']:
        raise ValueError('Distinct-image pacing requires editorial revision: '
                         + '; '.join(report['violations'])
                         + '. Preserve the voice; split source beats and provide distinct illustrations.')
    return report
