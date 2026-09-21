"""Small local FIFO queue and calendar, with explicit Buffer boundaries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo


class ScheduleService:
    def __init__(self, application, *, now=None):
        self.app = application
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _local_now(self):
        return self.now().astimezone(ZoneInfo(self.app.s.timezone))

    @staticmethod
    def _buffer_locked(row):
        return bool(row.get('buffer'))

    def _require_local(self, row):
        if self._buffer_locked(row):
            raise ValueError(
                'Este vídeo ya tiene estado en Buffer. Revisa o cancela el envío remoto antes de cambiar su calendario local.'
            )
        if row.get('schedule_status') == 'published':
            raise ValueError('Un vídeo publicado no se puede desprogramar')

    def change(self, cid, when, platforms=None):
        row = self.app.content(cid)
        self._require_local(row)
        if when is not None:
            if when.tzinfo is None or when.utcoffset() is None:
                raise ValueError('La fecha debe incluir zona horaria')
            if when <= self.now():
                raise ValueError('Elige una fecha futura')
            if row['generation_status'] != 'ready':
                raise ValueError('Genera el vídeo antes de programarlo')
        changes = {'schedule_enabled': when is not None, 'publish_at': when.isoformat() if when else None}
        if platforms is not None:
            if not platforms or set(platforms) - {'tiktok', 'instagram', 'youtube'}:
                raise ValueError('Selecciona plataformas válidas')
            changes['platforms'] = platforms
        self.app.edit(cid, changes)
        from .state import StateStore
        StateStore(self.app.s.state_path).upsert(
            cid, schedule_status='scheduled' if when else 'unscheduled', queue_position=None,
        )
        return self.app.content(cid)

    def _queued(self):
        rows = [row for row in self.app.content() if row['schedule_status'] == 'queued']
        return sorted(rows, key=lambda row: (
            row['queue_position'] if row['queue_position'] is not None else 10**9,
            row['item']['id'],
        ))

    def _rewrite_positions(self, ordered_ids):
        from .state import StateStore
        state = StateStore(self.app.s.state_path)
        for position, cid in enumerate(ordered_ids, 1):
            state.upsert(cid, schedule_status='queued', queue_position=position)

    def queue_add(self, cid):
        row = self.app.content(cid)
        self._require_local(row)
        if row['generation_status'] != 'ready':
            raise ValueError('Solo los vídeos READY pueden entrar en la cola')
        if row['schedule_status'] == 'scheduled':
            self.change(cid, None)
            row = self.app.content(cid)
        if row['schedule_status'] == 'queued':
            return row
        ordered = [entry['item']['id'] for entry in self._queued()]
        ordered.append(cid)
        self._rewrite_positions(ordered)
        return self.app.content(cid)

    def queue_remove(self, cid):
        row = self.app.content(cid)
        self._require_local(row)
        if row['schedule_status'] != 'queued':
            raise ValueError('El vídeo no está en la cola')
        ordered = [entry['item']['id'] for entry in self._queued() if entry['item']['id'] != cid]
        from .state import StateStore
        StateStore(self.app.s.state_path).upsert(cid, schedule_status='unscheduled', queue_position=None)
        self._rewrite_positions(ordered)
        return self.app.content(cid)

    def queue_move(self, cid, direction):
        if direction not in {'up', 'down', 'top', 'bottom'}:
            raise ValueError('Movimiento de cola desconocido')
        ordered = [entry['item']['id'] for entry in self._queued()]
        if cid not in ordered:
            raise ValueError('El vídeo no está en la cola')
        index = ordered.index(cid)
        if direction == 'up' and index > 0:
            ordered[index - 1], ordered[index] = ordered[index], ordered[index - 1]
        elif direction == 'down' and index < len(ordered) - 1:
            ordered[index + 1], ordered[index] = ordered[index], ordered[index + 1]
        elif direction == 'top':
            ordered.insert(0, ordered.pop(index))
        elif direction == 'bottom':
            ordered.append(ordered.pop(index))
        self._rewrite_positions(ordered)
        return self.view()

    def schedule_move(self, cid, direction):
        """Swap a local scheduled item with its chronological neighbour."""
        if direction not in {'earlier', 'later'}:
            raise ValueError('Movimiento de calendario desconocido')
        row = self.app.content(cid)
        self._require_local(row)
        if row['schedule_status'] != 'scheduled':
            raise ValueError('El vídeo no está programado localmente')
        from .queue_editor import queue_digest, reorder_item
        from .state import StateStore
        reorder_item(
            self.app.s.queue_path,
            StateStore(self.app.s.state_path),
            cid,
            -1 if direction == 'earlier' else 1,
            expected_revision=queue_digest(self.app.s.queue_path),
        )
        return self.view()

    def queue_all_ready(self, *, confirm=False):
        state = self.app.load()[1]
        candidates = [row for row in self.app.content()
                      if row['generation_status'] == 'ready'
                      and row['schedule_status'] == 'unscheduled'
                      and not self._buffer_locked(row)]
        candidates.sort(key=lambda row: (
            state.get(row['item']['id']).get('created_at', ''), row['item']['id']))
        result = {'ids': [row['item']['id'] for row in candidates], 'count': len(candidates),
                  'confirmed': confirm}
        if confirm:
            for row in candidates:
                self.queue_add(row['item']['id'])
        return result

    def _future_slots(self, occupied, count):
        zone = ZoneInfo(self.app.s.timezone)
        cursor = self._local_now().date()
        now = self._local_now()
        result = []
        while len(result) < count:
            for value in sorted(self.app.s.default_posting_slots):
                slot = datetime.combine(cursor, time.fromisoformat(value), tzinfo=zone)
                if slot > now and slot.astimezone(timezone.utc) not in occupied:
                    result.append(slot)
                    if len(result) == count:
                        break
            cursor += timedelta(days=1)
        return result

    def fill(self, *, confirm=False):
        queued = self._queued()
        rows = self.app.content()
        occupied = {
            datetime.fromisoformat(row['scheduled_at']).astimezone(timezone.utc)
            for row in rows if row.get('scheduled_at')
        }
        slots = self._future_slots(occupied, len(queued))
        assignments = [{'id': row['item']['id'], 'at': slot.isoformat()}
                       for row, slot in zip(queued, slots)]
        if confirm:
            for assignment in assignments:
                self.change(assignment['id'], datetime.fromisoformat(assignment['at']))
        return {'assignments': assignments, 'count': len(assignments), 'confirmed': confirm,
                'timezone': self.app.s.timezone}

    def unschedule_future(self, *, confirm=False, queue_after=False):
        now = self.now()
        candidates, attention = [], []
        for row in self.app.content():
            if not row.get('scheduled_at') or datetime.fromisoformat(row['scheduled_at']) <= now:
                continue
            if self._buffer_locked(row) or row['schedule_status'] == 'published':
                attention.append(row['item']['id'])
            else:
                candidates.append(row['item']['id'])
        if confirm:
            for cid in candidates:
                self.change(cid, None)
                if queue_after and self.app.content(cid)['generation_status'] == 'ready':
                    self.queue_add(cid)
        return {'ids': candidates, 'count': len(candidates), 'attention': attention,
                'queue_after': queue_after, 'confirmed': confirm}

    def view(self):
        rows = self.app.content()
        scheduled = sorted((row for row in rows if row['schedule_status'] in {'scheduled', 'published'}),
                           key=lambda row: row['scheduled_at'] or '')
        conflicts = []
        for index, first in enumerate(scheduled):
            for second in scheduled[index + 1:]:
                if (first['scheduled_at'] and second['scheduled_at']
                        and datetime.fromisoformat(first['scheduled_at']) == datetime.fromisoformat(second['scheduled_at'])):
                    common = set(first['item']['platforms']) & set(second['item']['platforms'])
                    if common:
                        conflicts.append({'ids': [first['item']['id'], second['item']['id']],
                                          'platforms': sorted(common)})
        return {
            'timezone': self.app.s.timezone,
            'items': scheduled,
            'queued': self._queued(),
            'conflicts': conflicts,
            'unscheduled': [row for row in rows if row['generation_status'] == 'ready'
                            and row['schedule_status'] == 'unscheduled'
                            and not self._buffer_locked(row)],
            'slots': self.available_slots(rows),
            'remote_changes_supported': False,
        }

    def available_slots(self, rows, days=7):
        zone = ZoneInfo(self.app.s.timezone)
        now = self._local_now()
        result = []
        for day in range(days):
            for value in sorted(self.app.s.default_posting_slots):
                slot = datetime.combine(now.date() + timedelta(days=day), time.fromisoformat(value), tzinfo=zone)
                if slot <= now:
                    continue
                occupied = sorted({platform for row in rows
                                   if row['scheduled_at']
                                   and datetime.fromisoformat(row['scheduled_at']) == slot
                                   for platform in row['item']['platforms']})
                result.append({'at': slot.isoformat(), 'occupied_platforms': occupied})
        return result
