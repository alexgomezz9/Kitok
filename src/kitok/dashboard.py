"""Local Streamlit control center. Rendering only reads local files and caches."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from .buffer_client import PLATFORMS
from .buffer_usage import usage_rows
from .control_panel import ControlPanel, disclosure, recommendation
from .publisher import Publisher
from .queue_editor import suggested_id
from .regeneration import skip_reason

PAGES = ["Dashboard", "Calendar / Queue", "Content", "Publishing", "Attention", "Settings"]
ICONS = {"tiktok": "♪", "instagram": "◎", "youtube": "▶"}
PLATFORM_NAMES = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}
LABELS = {"pending": "⚪ Pending", "submitted": "🔵 Generating", "generating": "🔵 Generating",
          "generated": "🔵 Validating", "ready": "🟢 Ready", "scheduled": "🟡 Scheduled",
          "sending": "🟡 Sending", "sent": "✅ Published", "failed": "🔴 Failed",
          "error": "🔴 Failed", "unknown": "⚠ Attention", "creating": "⚠ Attention",
          "needs_attention": "⚠ Attention", "needs_approval": "⚠ Needs approval",
          "draft": "⚠ Draft", "skipped": "⏭ Skipped", "archived": "📦 Archived"}
CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1480px;}
[data-testid="stMetric"] {background: #ffffff; border: 1px solid #e5e9e7;
  border-radius: 15px; padding: 1rem 1.2rem; box-shadow: 0 2px 8px #122b1b08;}
[data-testid="stMetricLabel"] {font-size: .82rem; font-weight: 700; letter-spacing: .03em;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 15px;}
.kicker {color:#247755;font-size:.78rem;font-weight:750;letter-spacing:.11em;text-transform:uppercase}
.subtle {color:#61716a;font-size:.9rem}
</style>
"""


def _label(status: str) -> str:
    return LABELS.get(status, status.replace("_", " ").title())


def _local(value: datetime | str, zone: str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(ZoneInfo(zone))


def _due(day, hour, zone: str) -> str:
    due = datetime.combine(day, hour, tzinfo=ZoneInfo(zone))
    back = due.astimezone(timezone.utc).astimezone(due.tzinfo)
    if back != due or due.replace(fold=1).utcoffset() != due.utcoffset():
        raise ValueError("That local time is missing or ambiguous because of daylight saving. Choose another time.")
    return due.isoformat()


def _next_slot(zone: str, occupied: set[datetime] | None = None) -> datetime:
    now = datetime.now(ZoneInfo(zone))
    occupied_utc = {value.astimezone(timezone.utc) for value in (occupied or set())}
    for offset in range(366):
        day = now.date() + timedelta(days=offset)
        for hour in (13, 19, 22):
            due = datetime.combine(day, datetime.min.time().replace(hour=hour), tzinfo=ZoneInfo(zone))
            if due > now and due.astimezone(timezone.utc) not in occupied_utc:
                return due
    raise ValueError("No open normal publishing slot is available in the next year")


def _queue_action(panel: ControlPanel, kind: str, content_id=None, **kwargs) -> None:
    try:
        st.session_state["pending_action"] = panel.prepare_action(kind, content_id, **kwargs)
        st.rerun()
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))


def _plan_table(rows: list[dict], panel: ControlPanel) -> None:
    queue, _ = panel.load()
    by_id = queue.by_id()
    matrix = {}
    for row in rows:
        cid = row["id"]
        if cid not in matrix:
            matrix[cid] = {"Video": by_id[cid].subject,
                           "Time": _local(row["dueAt"], panel.s.timezone).strftime("%d %b · %H:%M"),
                           "TikTok": "—", "Instagram": "—", "YouTube": "—"}
        matrix[cid][PLATFORM_NAMES[row["platform"]]] = "✓"
    if matrix:
        st.dataframe(list(matrix.values()), hide_index=True, width="stretch")
    else:
        st.info("No ready posts fit the current local plan.")


def _confirmation(panel: ControlPanel) -> None:
    action = st.session_state.get("pending_action")
    if action is None:
        return
    with st.container(border=True):
        st.subheader("Review before continuing")
        summary = action.summary
        if action.kind in {"publish", "fill"}:
            st.write(f"**Will schedule up to {summary['videos']} videos / {summary['posts']} posts.**")
            st.caption(f"Cloudinary uploads: up to {summary['uploads']} · Buffer API requests: about {summary['estimated_requests']}")
            _plan_table(action.rows, panel)
            st.write("Estimated occupancy after scheduling")
            st.caption(" · ".join(f"{PLATFORM_NAMES[name]} {summary['after_estimated'][name]}/{panel.s.buffer_max_scheduled_per_channel}"
                                  for name in PLATFORMS))
            st.info("Buffer occupancy will be checked again before any upload or post is created.")
        else:
            text = summary.get("Topic") or (panel.load()[0].by_id().get(action.content_id).subject
                                            if action.content_id and action.content_id in panel.load()[0].by_id() else action.content_id)
            st.write(f"**{text}** · {action.kind.replace('_', ' ').title()}")
            for key, value in summary.items():
                if key not in {"Action", "Content ID", "Topic", "changes", "publishing state to clear"}:
                    st.caption(f"{key}: {value}")
            if action.kind == "edit":
                names = {"subject": "Topic", "caption": "Caption", "youtube_title": "YouTube title",
                         "keywords": "Video terms", "publish_at": "Publish time", "script": "Script"}
                for key, value in action.changes.items():
                    if key == "script":
                        st.caption("Script: updated")
                    else:
                        st.caption(f"{names.get(key, key)}: {value if value not in (None, '') else 'empty'}")
            if action.kind == "add":
                st.caption("Caption: " + (action.changes.get("caption") or "empty"))
                st.caption("YouTube title: " + (action.changes.get("youtube_title") or "uses topic"))
                st.caption("Video terms: " + ", ".join(action.changes.get("keywords", [])))
            if action.kind == "reset":
                publishing = summary.get("publishing state to clear") or {}
                st.warning(f"Clear {len(publishing.get('buffer', {}))} Buffer platform records and "
                           f"{'a' if publishing.get('cloudinary') else 'no'} Cloudinary record. "
                           "Only after you have manually removed the social posts.")
        if action.kind == "delete":
            st.warning("Destructive queue removal. Local media and state history remain; no remote asset is deleted.")
            typed = st.text_input("Type the content ID to confirm deletion", key="delete-proof")
        else:
            typed = None
        with st.expander("Advanced details"):
            st.json(summary)
            if action.rows:
                st.json(action.rows)
        left, right = st.columns(2)
        if left.button("Cancel", key="cancel-action", width="stretch"):
            st.session_state.pop("pending_action", None)
            st.rerun()
        disabled = ((action.kind in {"publish", "fill"} and not panel.s.publish_enabled)
                    or (action.kind == "delete" and typed != action.content_id))
        label = "Confirm Fill Buffer" if action.kind == "fill" else "Confirm"
        if right.button(label, key="confirm-action", type="primary", disabled=disabled, width="stretch"):
            st.session_state.pop("pending_action", None)
            try:
                with st.spinner("Working…"):
                    st.session_state["action_result"] = panel.execute(action, confirmed=True)
                st.session_state.pop("plan", None)
                st.session_state.pop("plan_scope", None)
            except (ValueError, RuntimeError, OSError) as error:
                st.session_state["action_error"] = str(error)
            st.rerun()


def _occupancy(panel: ControlPanel, data: dict, fresh: bool) -> None:
    source = "LIVE" if fresh else ("CACHED" if data["snapshot"] else "LOCAL ESTIMATE")
    st.subheader("Buffer capacity")
    st.caption(f"{source} · Updated {data['snapshot'].get('refreshed_at', 'never')}")
    for column, platform in zip(st.columns(3), PLATFORMS):
        column.metric(f"{ICONS[platform]} {PLATFORM_NAMES[platform]}",
                      f"{data['occupancy'][platform]} / {panel.s.buffer_max_scheduled_per_channel}")


def _usage(panel: ControlPanel, data: dict) -> None:
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.subheader("Buffer API usage")
        rows = usage_rows(data["buffer_usage"])
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
        else:
            st.info("Usage is not cached yet. Refresh Buffer to collect response headers.")
        st.caption("Updated " + data["buffer_usage"].get("refreshed_at", "never"))
    with right, st.container(border=True):
        st.subheader("Cloudinary usage")
        report = data["cloudinary_usage"]
        values = report.get("data", {})
        for name in ("storage", "bandwidth", "transformations", "credits"):
            metric = values.get(name, {})
            st.caption(f"{name.title()}: {metric.get('usage', 'unknown')} / {metric.get('limit', 'unknown')}")
        st.caption("Updated " + report.get("refreshed_at", "never"))
        if panel.s.cloudinary_usage_guard:
            st.caption(f"New uploads stop at {panel.s.cloudinary_usage_threshold:.0%} of a known limit.")
        if st.button("Refresh Cloudinary usage"):
            try:
                panel.cloud_usage.refresh()
                st.rerun()
            except (ValueError, RuntimeError, OSError) as error:
                st.error(str(error))


def _plan(panel: ControlPanel, content_id=None) -> None:
    if st.button("Preview Publish Plan", key=f"preview-{content_id or 'all'}", type="secondary"):
        try:
            st.session_state["plan"] = panel.preview(content_id)
            st.session_state["plan_scope"] = content_id
        except (ValueError, RuntimeError, OSError) as error:
            st.error(str(error))
    plan = st.session_state.get("plan")
    if plan is None or st.session_state.get("plan_scope") != content_id:
        return
    st.subheader(f"Would schedule {len({row['id'] for row in plan.rows})} videos / {len(plan.rows)} posts")
    st.caption(f"OFFLINE PREVIEW · Occupancy {plan.occupancy_source} · snapshot {plan.refreshed_at or 'not available'}")
    _plan_table(plan.rows, panel)
    _, state = panel.load()
    uploads = sum(not state.get(cid).get("publishing", {}).get("cloudinary", {}).get("url")
                  for cid in {row["id"] for row in plan.rows})
    st.caption(f"Cloudinary uploads: up to {uploads} · Estimated Buffer requests: {plan.estimated_requests}")
    after = Counter(plan.counts)
    after.update(row["platform"] for row in plan.rows)
    st.caption("After: " + " · ".join(f"{PLATFORM_NAMES[p]} {after[p]}/{panel.s.buffer_max_scheduled_per_channel}" for p in PLATFORMS))
    if plan.issues:
        with st.expander(f"{len(plan.issues)} items need attention"):
            for issue in plan.issues:
                st.warning(f"{issue.get('platform', 'Item')}: {issue['error']}")
    with st.expander("Advanced plan details"):
        st.json(plan.rows)


def _dashboard(panel: ControlPanel, data: dict, fresh: bool) -> None:
    st.markdown('<div class="kicker">Daily overview</div>', unsafe_allow_html=True)
    for col, title, count in zip(st.columns(4), ["READY VIDEOS", "SCHEDULED", "PUBLISHED", "ATTENTION"],
                                 [data["counts"].get("ready", 0), data["counts"].get("scheduled", 0),
                                  data["counts"].get("published", 0), len(data["issues"])]):
        col.metric(title, count)
    _occupancy(panel, data, fresh)
    left, right = st.columns([1.25, 1])
    with left, st.container(border=True):
        st.subheader("Next posts")
        queue, _ = panel.load()
        now = datetime.now(timezone.utc)
        upcoming = [item for item in sorted(queue.items, key=lambda item: item.publish_at)
                    if item.editorial_status == "active" and item.publish_at > now][:5]
        for item in upcoming:
            when = _local(item.publish_at, panel.s.timezone)
            day = "Today" if when.date() == _local(now, panel.s.timezone).date() else (
                "Tomorrow" if when.date() == (_local(now, panel.s.timezone).date() + timedelta(days=1))
                else when.strftime("%a %d %b"))
            st.write(f"**{day} {when:%H:%M}**   {item.subject}")
        if not upcoming:
            st.info("No future active items. Add content or change a publish time.")
    with right, st.container(border=True):
        st.subheader("Daily actions")
        _plan(panel)
        st.caption("See what Kitok would schedule. No external changes.")
        if st.button("Fill Buffer", disabled=not panel.s.publish_enabled, type="primary", width="stretch"):
            _queue_action(panel, "fill")
        st.caption("Upload and schedule enough ready videos to refill Buffer to the configured target.")
        if st.button("Refresh Buffer", key="home-refresh", width="stretch"):
            try:
                panel.refresh_buffer()
                st.session_state["fresh_once"] = True
                st.rerun()
            except (ValueError, RuntimeError, OSError) as error:
                st.error(str(error))
        st.caption("Read current channel counts. Only this click contacts Buffer.")
    with st.expander("Service usage and AI disclosure"):
        st.caption("AI disclosure: " + " · ".join(f"{key}: {'on' if value else 'off'}"
                                                for key, value in disclosure(panel.s).items()))
        _usage(panel, data)


def _open_content(content_id: str) -> None:
    st.session_state["selected_content"] = content_id
    st.session_state["content_picker"] = content_id
    st.session_state["nav_target"] = "Content"
    st.rerun()


def _add_form(panel: ControlPanel) -> None:
    queue, _ = panel.load()
    slot = _next_slot(panel.s.timezone, {item.publish_at for item in queue.items})
    with st.expander("＋ Add Content", expanded=False):
        st.caption("New items enter the editorial queue as Pending. Generation starts only when you choose Generate.")
        with st.form("add-content", clear_on_submit=True):
            topic = st.text_input("Topic / title *")
            cid = st.text_input("Content ID (optional)", help="Leave blank to generate a safe ID from the topic. You can enter your own unique ID.")
            script = st.text_area("Script *", height=150)
            caption = st.text_area("Caption *", height=90)
            youtube = st.text_input("YouTube title (optional)")
            terms = st.text_input("Pexels / video terms *", help="Separate terms with commas")
            day_col, time_col = st.columns(2)
            day = day_col.date_input("Publish date", slot.date())
            hour = time_col.time_input(f"Time · {panel.s.timezone}", slot.time().replace(tzinfo=None))
            if st.form_submit_button("Review new content", type="primary"):
                try:
                    _, state = panel.load()
                    values = {"id": cid.strip() or suggested_id(topic, set(queue.by_id()) | set(state.all())),
                              "subject": topic, "script": script, "caption": caption,
                              "youtube_title": youtube.strip() or None,
                              "keywords": [term.strip() for term in terms.split(",") if term.strip()],
                              "publish_at": _due(day, hour, panel.s.timezone)}
                    _queue_action(panel, "add", changes=values)
                except ValueError as error:
                    st.error(str(error))


def _calendar(panel: ControlPanel, data: dict) -> None:
    st.caption("Times are shown in " + panel.s.timezone + ". Moving an item exchanges its publish time with its neighbor.")
    _add_form(panel)
    _, state = panel.load()
    show_archived = st.toggle("Show archived", value=False)
    rows = panel.view(include_archived=show_archived)["rows"] if show_archived else data["rows"]
    if not rows:
        st.info("The editorial queue is empty. Add a content item above.")
        return
    today = datetime.now(ZoneInfo(panel.s.timezone)).date()
    previous = None
    for row in rows:
        day = datetime.fromisoformat(row["Date"]).date()
        if day != previous:
            label = "TODAY" if day == today else "TOMORROW" if day == today + timedelta(days=1) else day.strftime("%A · %d %B %Y").upper()
            st.subheader(label)
            previous = day
        with st.container(border=True):
            title, states, actions = st.columns([2.6, 3.1, 3.2], vertical_alignment="center")
            title.markdown(f"**{row['Time']} · {row['Content']}**")
            title.caption(_label(row["Editorial"]) if row["Editorial"] != "active" else _label(row["Generation"]))
            states.caption(" · ".join(f"{ICONS[p]} {_label(row[p.title()])}" for p in PLATFORMS))
            if row["Attention"]:
                states.caption("⚠ Needs review")
            cid = row["ID"]
            protected = bool(state.get(cid).get("publishing"))
            if protected:
                states.caption("Remote schedule protected; rescheduling needs a separate action.")
            buttons = actions.columns(5)
            if buttons[0].button("Edit", key=f"edit-{cid}", width="stretch"):
                _open_content(cid)
            if buttons[1].button("↑", key=f"up-{cid}", help="Move earlier; swap publish times", width="stretch",
                                 disabled=row["Editorial"] != "active" or protected):
                _queue_action(panel, "move_earlier", cid)
            if buttons[2].button("↓", key=f"down-{cid}", help="Move later; swap publish times", width="stretch",
                                 disabled=row["Editorial"] != "active" or protected):
                _queue_action(panel, "move_later", cid)
            if buttons[3].button("Skip", key=f"skip-{cid}", width="stretch",
                                 disabled=row["Editorial"] != "active" or protected):
                _queue_action(panel, "skip", cid)
            if buttons[4].button("Archive", key=f"archive-{cid}", width="stretch",
                                 disabled=row["Editorial"] == "archived"):
                _queue_action(panel, "archive", cid)


def _edit_form(panel: ControlPanel, item, record: dict, *, expanded=False) -> None:
    can_change_script = (record.get("status", "pending") == "pending" and
                         not record.get("attempts") and not record.get("mpt_task_id"))
    editing_script = st.session_state.get("edit_script_for") == item.id
    if not editing_script:
        with st.expander("Read script", expanded=False):
            st.write(item.script)
            if st.button("Edit script", disabled=not can_change_script,
                         help="Script changes are available before video generation begins."):
                st.session_state["edit_script_for"] = item.id
                st.rerun()
    with st.expander("Edit content and schedule", expanded=expanded):
        local = _local(item.publish_at, panel.s.timezone)
        with st.form(f"edit-content-{item.id}"):
            title = st.text_input("Topic / title", item.subject)
            caption = st.text_area("Caption", item.caption)
            youtube = st.text_input("YouTube title (optional)", item.youtube_title or "")
            terms = st.text_input("Pexels / video terms", ", ".join(item.keywords), disabled=not can_change_script)
            script = st.text_area("Script", item.script, height=150) if editing_script and can_change_script else None
            date_col, time_col = st.columns(2)
            day = date_col.date_input("Publish date", local.date())
            hour = time_col.time_input(f"Time · {panel.s.timezone}", local.time().replace(tzinfo=None))
            if st.form_submit_button("Review changes", type="primary"):
                try:
                    changes = {"subject": title, "caption": caption, "youtube_title": youtube.strip() or None,
                               "publish_at": _due(day, hour, panel.s.timezone)}
                    if can_change_script:
                        changes["keywords"] = [term.strip() for term in terms.split(",") if term.strip()]
                    if script is not None:
                        changes["script"] = script
                    _queue_action(panel, "edit", item.id, changes=changes)
                except ValueError as error:
                    st.error(str(error))


def _content(panel: ControlPanel) -> None:
    queue, state = panel.load()
    if not queue.items:
        _add_form(panel)
        return
    ids = list(queue.by_id())
    selected = st.session_state.get("selected_content")
    if selected in ids and "content_picker" not in st.session_state:
        st.session_state["content_picker"] = selected
    cid = st.selectbox("Content item", ids, key="content_picker",
                       format_func=lambda value: queue.by_id()[value].subject)
    st.session_state["selected_content"] = cid
    item, record = queue.by_id()[cid], state.get(cid)
    publishing = record.get("publishing") or {}
    st.subheader(item.subject)
    st.caption(f"{_local(item.publish_at, panel.s.timezone):%d %B %Y · %H:%M %Z} · {item.editorial_status.title()}")
    left, right = st.columns([1.15, 1], gap="large")
    with left, st.container(border=True):
        st.markdown('<div class="kicker">Video preview</div>', unsafe_allow_html=True)
        try:
            video = Publisher(panel.s, queue, state)._video_path(item, record)
        except ValueError:
            video = None
        if video:
            st.video(str(video))
        else:
            st.info("No local ready video yet. Use Generate after reviewing the content.")
        with st.expander("Advanced / Debug"):
            st.caption(f"Content ID: {cid} · MP4: {video or 'missing'}")
            st.caption(f"MPT task: {record.get('mpt_task_id') or 'none'} · Attempts: {record.get('attempts', 0)}")
            st.json(record.get("validation") or {})
            st.json(publishing)
    with right, st.container(border=True):
        st.markdown('<div class="kicker">Editorial details</div>', unsafe_allow_html=True)
        st.write(f"**Topic**  {item.subject}")
        st.write(f"**Publish time**  {_local(item.publish_at, panel.s.timezone):%d %b %Y · %H:%M %Z}")
        st.write(f"**Generation**  {_label(record.get('status', 'pending'))}")
        st.write(f"**Duration**  {record.get('validation', {}).get('duration') or 'Not measured'} seconds")
        st.write(f"**File size**  {f'{video.stat().st_size / 1024 / 1024:.1f} MB' if video else 'No local file'}")
        validation = record.get("validation") or {}
        st.write("**Media compatibility**  " + ("✅ Validated" if validation.get("ok") else "⚠ Not validated / needs review"))
        st.write(f"**YouTube title**  {item.youtube_title or item.subject}")
        st.write(f"**Caption**  {item.caption or '—'}")
        if record.get("last_error"):
            st.warning("Generation needs review. Open Advanced / Debug for the technical details.")
    with st.container(border=True):
        st.subheader("Platforms")
        for col, platform in zip(st.columns(3), PLATFORMS):
            post = publishing.get("buffer", {}).get(platform, {})
            status = post.get("status", "skipped" if item.editorial_status == "skipped" else
                              ("ready" if record.get("status") == "ready" else "pending"))
            col.write(f"**{ICONS[platform]} {PLATFORM_NAMES[platform]}**")
            col.caption(_label(status))
    st.caption("AI disclosure: " + " · ".join(f"{key}: {'on' if value else 'off'}" for key, value in disclosure(panel.s).items()))
    _plan(panel, cid)
    if publishing:
        st.info("Publishing metadata exists. Local edits, skipping and moving are protected. Remote rescheduling requires a separate explicit action.")
    else:
        _edit_form(panel, item, record, expanded=bool(st.session_state.pop("open_edit", False)))
    st.subheader("Actions")
    first = st.columns(5)
    if first[0].button("Edit content", disabled=bool(publishing)):
        st.session_state["open_edit"] = True
        st.rerun()
    if first[1].button("Generate", disabled=item.editorial_status != "active" or record.get("status", "pending") == "ready"):
        _queue_action(panel, "generate", cid)
    if first[2].button("Regenerate", disabled=bool(skip_reason(record)) or item.editorial_status != "active"):
        _queue_action(panel, "regenerate", cid)
    if first[3].button("Publish Selected", disabled=not panel.s.publish_enabled or record.get("status") != "ready" or item.editorial_status != "active"):
        _queue_action(panel, "publish", cid)
    if first[4].button("Reset Publishing State", disabled=not bool(publishing)):
        _queue_action(panel, "reset", cid)
    second = st.columns(4)
    if second[0].button("Skip", disabled=item.editorial_status != "active" or bool(publishing)):
        _queue_action(panel, "skip", cid)
    if second[1].button("Archive", disabled=item.editorial_status == "archived"):
        _queue_action(panel, "archive", cid)
    if second[2].button("Restore", disabled=item.editorial_status == "active"):
        _queue_action(panel, "restore", cid)
    if second[3].button("Delete from queue", disabled=bool(publishing)):
        _queue_action(panel, "delete", cid)
    st.caption("Archive hides an item from daily views. Delete removes its queue entry only; media and state history stay on disk.")


def _publishing(panel: ControlPanel, data: dict, fresh: bool) -> None:
    _occupancy(panel, data, fresh)
    st.caption("Connection details and queue flags come from the last explicit Buffer refresh.")
    for platform in PLATFORMS:
        channel = data["snapshot"].get("channels", {}).get(platform, {})
        with st.container(border=True):
            st.write(f"**{ICONS[platform]} {PLATFORM_NAMES[platform]}** · " + ("Cached connection" if channel else "Connection unknown"))
            flags = [name for name, key in (("Disconnected", "isDisconnected"), ("Locked", "isLocked"),
                                            ("Queue paused", "isQueuePaused")) if channel.get(key)]
            st.caption(" · ".join(flags) if flags else "No cached connection warning")
            with st.expander("Advanced / Debug"):
                st.caption("Channel ID: " + str(channel.get("id", "not cached")))
    st.subheader("Next scheduled posts")
    for post in data["scheduled_posts"][:10]:
        when = _local(post["dueAt"], panel.s.timezone).strftime("%d %b · %H:%M") if post.get("dueAt") else "Time unknown"
        st.write(f"**{when}** · {post.get('text') or 'Scheduled post'}")
    if not data["scheduled_posts"]:
        st.info("No scheduled posts in the local/cached snapshot.")
    st.caption("Last state sync: " + data["last_sync"])
    actions = st.columns(2)
    if actions[0].button("Sync state", help="Read Buffer and reconcile saved IDs locally. No posts are created."):
        try:
            st.session_state["action_result"] = panel.refresh_buffer(sync=True)
            st.rerun()
        except (ValueError, RuntimeError, OSError) as error:
            st.error(str(error))
    if actions[1].button("Fill Buffer", disabled=not panel.s.publish_enabled, type="primary"):
        _queue_action(panel, "fill")
    _usage(panel, data)


def _friendly(message: str) -> str:
    value = message.lower()
    if "past" in value:
        return "Scheduled time has already passed. Choose a new time or skip this item."
    if "missing" in value or "not found" in value:
        return "A needed file or remote post could not be found. Review the saved status."
    if "unknown" in value or "ambiguous" in value:
        return "The previous result is uncertain. Sync state and inspect it before another publish."
    if "rate" in value or "cooldown" in value:
        return "Buffer is limiting requests. Wait for the next available window."
    if "cloudinary" in value:
        return "Video hosting needs attention. Check usage or the saved asset."
    if "mp4" in value or "media" in value or "video" in value:
        return "The video needs review before it can be published."
    return "This item needs review before the next action."


def _attention(panel: ControlPanel, data: dict) -> None:
    issues = list(data["issues"])
    plan = st.session_state.get("plan")
    if plan:
        issues.extend({"Content ID": issue.get("id"), "Platform": issue.get("platform"),
                       "What happened": issue["error"], "Recommended action": recommendation(issue["error"])}
                      for issue in plan.issues)
    queue, state = panel.load()
    if not issues:
        st.success("No known local issues. Remote status changes appear after an explicit refresh.")
        return
    st.caption(f"{len(issues)} issues · Technical details are available inside each card.")
    for index, issue in enumerate(issues):
        cid = issue.get("Content ID")
        item = queue.by_id().get(cid)
        with st.container(border=True):
            st.write(f"**⚠ {item.subject if item else issue.get('Platform', 'Service')}**")
            st.write(_friendly(issue["What happened"]))
            st.caption(f"{issue.get('Platform', 'Kitok').title()} · {issue['Recommended action']}")
            with st.expander("Technical details"):
                st.code(issue["What happened"])
                if item:
                    st.caption(f"Content ID: {cid}")
            if item:
                buttons = st.columns(3)
                if buttons[0].button("Reschedule", key=f"reschedule-{index}", disabled=bool(state.get(cid).get("publishing"))):
                    st.session_state["open_edit"] = True
                    _open_content(cid)
                if buttons[1].button("Skip", key=f"attention-skip-{index}",
                                     disabled=bool(state.get(cid).get("publishing")) or item.editorial_status != "active"):
                    _queue_action(panel, "skip", cid)
                if buttons[2].button("Archive", key=f"attention-archive-{index}",
                                     disabled=item.editorial_status == "archived"):
                    _queue_action(panel, "archive", cid)


def main() -> None:
    """Render local views. External reads and all actions need explicit clicks."""
    st.set_page_config(page_title="Kitok · Social control center", page_icon="🎬", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        panel = ControlPanel()
        panel.load()
    except (ValueError, RuntimeError, OSError):
        st.error("Kitok could not load the local queue or configuration. Check .env and content_queue.json.")
        return
    st.sidebar.title("🎬 Kitok")
    if "nav_target" in st.session_state:
        st.session_state["page"] = st.session_state.pop("nav_target")
    page = st.sidebar.radio("Workspace", PAGES, key="page")
    st.sidebar.caption(f"Local workspace · {panel.s.timezone}")
    if panel.s.publish_enabled:
        st.sidebar.success("Publishing enabled")
    else:
        st.sidebar.warning("Publishing disabled")
        st.sidebar.caption("Preview is available. Change PUBLISH_ENABLED in .env to enable publishing.")
    st.title(page)
    st.caption("Ready = video on disk · Scheduled = in Buffer · Published = sent")
    _confirmation(panel)
    if "action_result" in st.session_state:
        st.success("Action finished")
        result = st.session_state.pop("action_result")
        st.caption(" · ".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in result.items()
                              if isinstance(value, (str, int, float))))
        with st.expander("Advanced action result"):
            st.json(result)
    if "action_error" in st.session_state:
        st.error(st.session_state.pop("action_error"))
    fresh = bool(st.session_state.pop("fresh_once", False))
    if st.button("Refresh status", help="Reload local data only; no service request."):
        st.rerun()
    if page != "Dashboard" and st.button("Refresh Buffer", help="Read current channels and occupancy; no posts are created."):
        try:
            panel.refresh_buffer()
            st.session_state["fresh_once"] = True
            st.rerun()
        except (ValueError, RuntimeError, OSError) as error:
            st.error(str(error))
    data = panel.view()
    if page == "Dashboard":
        _dashboard(panel, data, fresh)
    elif page == "Calendar / Queue":
        _calendar(panel, data)
    elif page == "Content":
        _content(panel)
    elif page == "Publishing":
        _publishing(panel, data, fresh)
    elif page == "Attention":
        _attention(panel, data)
    else:
        st.info("Settings are read only here. Edit environment variables or .env to change them.")
        for key, value in panel.settings_view().items():
            with st.container(border=True):
                st.write(f"**{key.replace('_', ' ').title()}**")
                st.caption(str(value))


if __name__ == "__main__":
    main()
