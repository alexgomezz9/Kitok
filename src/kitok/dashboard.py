"""Local Streamlit control center. Rendering only reads local files and caches."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from zoneinfo import ZoneInfo

import streamlit as st

from .buffer_client import PLATFORMS
from .buffer_usage import usage_rows
from .control_panel import ControlPanel, disclosure, recommendation
from .dashboard_presenter import (NAMES as PLATFORM_NAMES, STATUS_ICON, content_status,
                                  coverage, grouped_issues, recommendations, status_label)
from .publisher import Publisher
from .batch_import import parse_batch, validate_batch
from .queue_editor import add_batch, queue_digest, suggested_id
from .regeneration import skip_reason
from .thumbnails import ThumbnailService

PAGES = ["Home", "Content", "Calendar", "Attention"]
ICONS = {"tiktok": "♪", "instagram": "◎", "youtube": "▶"}
CSS = """
<style>
.kitok-kicker {color:#247755;font-size:.78rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase}
.kitok-muted {color:#61716a;font-size:.9rem}
</style>
"""


def _label(status: str) -> str:
    return status_label(status)


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
        st.subheader("Review scheduling" if action.kind in {"fill", "publish"} else "Review this change")
        summary = action.summary
        if action.kind in {"publish", "fill"}:
            st.write(f"**You're about to schedule up to {summary['videos']} videos and {summary['posts']} social posts.**")
            st.caption(" · ".join(f"{PLATFORM_NAMES[p]} +{summary['platforms'].get(p, 0)}" for p in PLATFORMS))
            st.caption(f"Up to {summary['uploads']} video uploads · About {summary['estimated_requests']} Buffer requests")
            if action.rows:
                last = max(_local(row["dueAt"], panel.s.timezone) for row in action.rows)
                st.write(f"Your schedule could extend through **{last:%A %d %b, %H:%M}**.")
            _plan_table(action.rows, panel)
            st.caption("Current publishing status is checked again before scheduling begins.")
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
        label = (f"Schedule {summary['videos']} videos" if action.kind == "fill" else
                 "Schedule this video" if action.kind == "publish" else "Confirm change")
        if right.button(label, key="confirm-action", type="primary", disabled=disabled,
                        help="Only this confirmation starts the approved action.", width="stretch"):
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
    if st.button("Preview schedule", key=f"preview-{content_id or 'all'}", type="secondary",
                 help="See exactly what Kitok would schedule. Nothing is uploaded or changed."):
        try:
            st.session_state["plan"] = panel.preview(content_id)
            st.session_state["plan_scope"] = content_id
        except (ValueError, RuntimeError, OSError) as error:
            st.error(str(error))
    plan = st.session_state.get("plan")
    if plan is None or st.session_state.get("plan_scope") != content_id:
        return
    st.subheader("Ready to schedule")
    st.write(f"**{len({row['id'] for row in plan.rows})} videos · {len(plan.rows)} social posts**")
    _plan_table(plan.rows, panel)
    _, state = panel.load()
    uploads = sum(not state.get(cid).get("publishing", {}).get("cloudinary", {}).get("url")
                  for cid in {row["id"] for row in plan.rows})
    st.caption(f"Up to {uploads} video uploads · About {plan.estimated_requests} Buffer requests")
    after = Counter(plan.counts)
    after.update(row["platform"] for row in plan.rows)
    st.caption("Estimated after: " + " · ".join(f"{PLATFORM_NAMES[p]} {after[p]}/{panel.s.buffer_max_scheduled_per_channel}" for p in PLATFORMS))
    if plan.rows:
        last = max(_local(row["dueAt"], panel.s.timezone) for row in plan.rows)
        st.write(f"Schedule could extend through **{last:%A %d %b, %H:%M}**.")
    if plan.issues:
        with st.expander(f"{len(plan.issues)} items need attention"):
            for issue in plan.issues:
                st.warning(f"{issue.get('platform', 'Item')}: {issue['error']}")
    with st.expander("Advanced plan details"):
        st.caption(f"Offline preview · {plan.occupancy_source} occupancy · last checked {plan.refreshed_at or 'never'}")
        st.json(plan.rows)
    left, right = st.columns(2)
    if left.button("Close preview", key=f"close-plan-{content_id or 'all'}"):
        st.session_state.pop("plan", None)
        st.session_state.pop("plan_scope", None)
        st.rerun()
    if right.button("Schedule", key=f"schedule-plan-{content_id or 'all'}", type="primary",
                    disabled=not panel.s.publish_enabled or not plan.rows,
                    help="Review the exact posts again before any upload or remote scheduling starts."):
        _queue_action(panel, "publish" if content_id else "fill", content_id)


def _refresh_publishing(panel: ControlPanel, *, sync: bool = False) -> None:
    """Run a Buffer read only after an explicit button click."""
    try:
        result = panel.refresh_buffer(sync=sync)
        if sync:
            st.session_state["action_result"] = result
        st.session_state["fresh_once"] = True
        st.rerun()
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))


def _navigate(page: str, content_id: str | None = None) -> None:
    if content_id:
        st.session_state["selected_content"] = content_id
    st.session_state["nav_target"] = page
    st.rerun()


def _dashboard(panel: ControlPanel, data: dict) -> None:
    queue, state = panel.load()
    advice = recommendations(data, queue, state, panel.s)
    top = advice[0]
    message = f"**{top.title}**\n\n{top.detail}"
    if top.kind in {"fix", "budget", "cloudinary"}:
        st.warning(message)
    elif top.kind == "none":
        st.success(message)
    else:
        st.info(message)
    if len(advice) > 1:
        st.caption("Also: " + " · ".join(item.title for item in advice[1:3]))

    st.subheader("Today")
    today = datetime.now(ZoneInfo(panel.s.timezone)).date().isoformat()
    rows = [row for row in data["rows"] if row["Date"] == today and row["Editorial"] == "active"]
    if rows:
        for row in rows:
            item = queue.by_id()[row["ID"]]
            overall = content_status(item, state.get(item.id), row)
            time_col, title_col, state_col = st.columns([1, 4, 2], vertical_alignment="center", wrap=True)
            time_col.markdown(f"**{row['Time']}**")
            title_col.write(item.subject)
            state_col.caption(f"{STATUS_ICON[overall]} {overall}")
            st.caption(" · ".join(f"{PLATFORM_NAMES[p]} {STATUS_ICON[status_label(row[p.title()])]} "
                                  f"{status_label(row[p.title()])}" for p in item.platforms))
    else:
        st.caption("No active content is planned for today.")

    st.subheader("Upcoming coverage")
    report = coverage(data, panel.s.buffer_channel_ids, panel.s.timezone)
    st.write(report["text"])
    st.caption(report["source"] + " · Open System details for the latest channel information.")

    if top.action == "Review issues":
        if st.button("Review issues", type="primary", help="Open the items that need action."):
            _navigate("Attention")
    elif top.action == "Fill schedule":
        if st.button("Fill schedule", type="primary", disabled=not panel.s.publish_enabled,
                     help="Upload the next ready videos and schedule posts until the configured target is reached."):
            _queue_action(panel, "fill")
    elif top.action == "Generate video":
        if st.button("Generate a video", type="primary",
                     help="Open the next draft to review its script before generation."):
            next_draft = next(item for item in queue.items if item.editorial_status == "active"
                              and state.get(item.id).get("status", "pending") == "pending")
            _open_content(next_draft.id)
    elif top.action == "Add content":
        if st.button("Prepare more content", type="primary",
                     help="Open your content library to add a new topic and script."):
            st.session_state["open_add"] = True
            _navigate("Content")
    elif top.action == "Refresh publishing status":
        if st.button("Refresh publishing status", type="primary",
                     help="Check the latest schedule from Buffer. This uses a small amount of API quota."):
            _refresh_publishing(panel)
    elif top.action == "Review system":
        if st.button("Review system", type="primary", help="See usage and service warnings."):
            _navigate("Advanced / System")
    if top.kind == "none":
        st.caption("No action is needed right now.")

    with st.expander("More actions"):
        _plan(panel)
        if st.button("Refresh publishing status", key="home-refresh",
                     help="Read Buffer's latest publishing status. This uses API quota."):
            _refresh_publishing(panel)
    st.divider()
    st.caption("SYSTEM · Buffer: " + ("cached" if data["snapshot"] else "not checked") +
               " · Cloudinary: " + ("usage cached" if data["cloudinary_usage"] else "not checked") +
               " · MPT: configured, availability not checked")
    if st.button("View system status", help="Open cached service details and deliberate refresh controls."):
        _navigate("Advanced / System")


def _open_content(content_id: str) -> None:
    _navigate("Content", content_id)


def _add_form(panel: ControlPanel) -> None:
    queue, _ = panel.load()
    slot = _next_slot(panel.s.timezone, {item.publish_at for item in queue.items})
    with st.expander("＋ Add content", expanded=bool(st.session_state.pop("open_add", False))):
        st.markdown("**Import a JSON batch**")
        _batch_import(panel)
        st.divider()
        st.markdown("**Or add one item**")
        st.caption("A new item starts as Draft. Video generation begins only when you choose it.")
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


def _batch_import(panel: ControlPanel) -> None:
    st.caption("Paste a JSON array or upload a .json file. Required: id, subject (or topic), script, "
               "caption, keywords (or video_terms), and publish_at with a timezone offset.")
    source = st.radio("Import source", ["Paste JSON", "Upload .json"], horizontal=True)
    if source == "Paste JSON":
        text = st.text_area("Batch JSON", height=170, placeholder='[{"id":"idea_1","topic":"...",...}]')
    else:
        uploaded = st.file_uploader("Choose a JSON file", type=["json"])
        try:
            text = uploaded.getvalue().decode("utf-8") if uploaded else ""
        except UnicodeDecodeError:
            text = ""
            st.error("File must be UTF-8 JSON.")
    if len(text.encode("utf-8")) > 2_000_000:
        st.error("Batch JSON exceeds the 2 MB preview limit.")
        return
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if st.button("Validate batch", disabled=not bool(text.strip()),
                 help="Check every item, ID and publish time locally. No content is written."):
        try:
            rows = parse_batch(text)
            queue, state = panel.load()
            items, errors = validate_batch(rows, queue, state)
            st.session_state["batch_preview"] = {
                "rows": rows, "items": items, "errors": errors, "source_digest": digest,
                "queue_revision": queue_digest(panel.s.queue_path),
            }
        except ValueError as error:
            st.session_state["batch_preview"] = {"rows": [], "items": [], "errors": [str(error)],
                                                  "source_digest": digest, "queue_revision": None}
    preview = st.session_state.get("batch_preview")
    if not preview:
        return
    if preview["source_digest"] != digest:
        st.info("The JSON changed. Validate the batch again before importing.")
        return
    st.write(f"**{len(preview['rows'])} items detected** · {len(preview['items'])} structurally valid")
    for error in preview["errors"]:
        st.error(error)
    if preview["errors"]:
        return
    st.success("All items valid · Unique IDs · Free scheduling slots · Required fields present")
    st.dataframe([{"Time": _local(item.publish_at, panel.s.timezone).strftime("%d %b %H:%M"),
                   "Topic": item.subject} for item in preview["items"]], hide_index=True, width="stretch")
    if st.button(f"Import {len(preview['items'])} contents", type="primary",
                 help="Add this complete batch to the local queue in one atomic write. No videos are generated."):
        try:
            imported = add_batch(panel.s.queue_path, panel.load()[1], preview["rows"],
                                 expected_revision=preview["queue_revision"])
            st.session_state.pop("batch_preview", None)
            st.session_state["batch_success"] = len(imported)
            st.rerun()
        except ValueError as error:
            st.session_state.pop("batch_preview", None)
            st.error(str(error))


def _calendar(panel: ControlPanel, data: dict) -> None:
    st.caption("Local times in " + panel.s.timezone + ". Open an item for details; use ⋯ to change its order.")
    queue, state = panel.load()
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
        cid = row["ID"]
        item = queue.by_id()[cid]
        overall = content_status(item, state.get(cid), row)
        time_col, title_col, status_col, open_col, more_col = st.columns(
            [1, 3.2, 1.7, 1, .6], vertical_alignment="center", wrap=True)
        time_col.markdown(f"**{row['Time']}**")
        title_col.write(item.subject)
        status_col.caption(f"{STATUS_ICON[overall]} {overall}")
        if open_col.button("Open", key=f"edit-{cid}", help="View and edit this content item."):
            _open_content(cid)
        if more_col.button("⋯", key=f"calendar-menu-{cid}", help="Move or organize this item."):
            st.session_state["calendar_menu"] = None if st.session_state.get("calendar_menu") == cid else cid
            st.rerun()
        if st.session_state.get("calendar_menu") == cid:
            protected = bool(state.get(cid).get("publishing"))
            if protected:
                st.caption("This item has publishing history. Remote rescheduling needs a separate action.")
            actions = st.columns(4)
            if actions[0].button("Move earlier", key=f"up-{cid}", disabled=protected or item.editorial_status != "active",
                                 help="Exchange this item's local publish time with the previous active item."):
                _queue_action(panel, "move_earlier", cid)
            if actions[1].button("Move later", key=f"down-{cid}", disabled=protected or item.editorial_status != "active",
                                 help="Exchange this item's local publish time with the next active item."):
                _queue_action(panel, "move_later", cid)
            if actions[2].button("Skip", key=f"calendar-skip-{cid}", disabled=protected or item.editorial_status != "active",
                                 help="Keep this content and its video, but exclude it from future publishing."):
                _queue_action(panel, "skip", cid)
            if actions[3].button("Archive", key=f"calendar-archive-{cid}", disabled=item.editorial_status == "archived",
                                 help="Hide this item from daily views while preserving its history."):
                _queue_action(panel, "archive", cid)
        st.divider()


def _edit_form(panel: ControlPanel, item, record: dict, *, expanded=False) -> None:
    can_change_script = (record.get("status", "pending") == "pending" and
                         not record.get("attempts") and not record.get("mpt_task_id"))
    with st.expander("Quick edit", expanded=expanded):
        local = _local(item.publish_at, panel.s.timezone)
        normal = {"13:00", "19:00", "22:00"}
        current = local.strftime("%H:%M")
        slot = st.selectbox("Publishing time", ["13:00", "19:00", "22:00", "Custom time"],
                            index=["13:00", "19:00", "22:00", "Custom time"].index(
                                current if current in normal else "Custom time"),
                            help="Use a regular slot or choose a custom local time.")
        with st.form(f"edit-content-{item.id}"):
            caption = st.text_area("Caption", item.caption)
            youtube = st.text_input("YouTube title (optional)", item.youtube_title or "")
            day = st.date_input("Publish date", local.date())
            hour = (st.time_input(f"Custom time · {panel.s.timezone}", local.time().replace(tzinfo=None))
                    if slot == "Custom time" else datetime.strptime(slot, "%H:%M").time())
            if st.form_submit_button("Review changes", type="primary"):
                try:
                    changes = {"caption": caption, "youtube_title": youtube.strip() or None,
                               "publish_at": _due(day, hour, panel.s.timezone)}
                    _queue_action(panel, "edit", item.id, changes=changes)
                except ValueError as error:
                    st.error(str(error))
    with st.expander("Advanced edit"):
        st.caption("Script and video search terms can change before generation starts. The ID is locked to preserve history.")
        st.caption("Content ID: " + item.id)
        with st.form(f"advanced-edit-{item.id}"):
            title = st.text_input("Topic / title", item.subject)
            terms = st.text_input("Video search terms", ", ".join(item.keywords), disabled=not can_change_script)
            script = st.text_area("Script", item.script, height=170, disabled=not can_change_script)
            if st.form_submit_button("Review advanced changes"):
                changes = {"subject": title}
                if can_change_script:
                    changes.update(script=script, keywords=[part.strip() for part in terms.split(",") if part.strip()])
                _queue_action(panel, "edit", item.id, changes=changes)


def _content_detail(panel: ControlPanel) -> None:
    queue, state = panel.load()
    cid = st.session_state.get("selected_content")
    if cid not in queue.by_id():
        st.session_state.pop("selected_content", None)
        return
    if st.button("← Back to content", help="Return to your content library."):
        st.session_state.pop("selected_content", None)
        st.rerun()
    item, record = queue.by_id()[cid], state.get(cid)
    publishing = record.get("publishing") or {}
    st.subheader(item.subject)
    row = next((row for row in panel.view(include_archived=True)["rows"] if row["ID"] == cid), None)
    overall = content_status(item, record, row)
    st.caption(f"{_local(item.publish_at, panel.s.timezone):%d %B %Y · %H:%M %Z} · "
               f"{STATUS_ICON[overall]} {overall}")
    left, right = st.columns([1.6, 1], gap="large")
    with left, st.container(border=True):
        st.markdown('<div class="kitok-kicker">Video preview</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="kitok-kicker">Editorial details</div>', unsafe_allow_html=True)
        st.write(f"**Topic**  {item.subject}")
        st.write(f"**Publish time**  {_local(item.publish_at, panel.s.timezone):%d %b %Y · %H:%M %Z}")
        st.write(f"**Video**  {_label(record.get('status', 'pending'))}")
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
    with st.expander("How this content will be labelled"):
        st.caption(" · ".join(f"{key}: {'on' if value else 'off'}" for key, value in disclosure(panel.s).items()))
    if publishing:
        st.info("This item has publishing history. Changing its schedule on social platforms requires a separate action.")
    else:
        _edit_form(panel, item, record, expanded=bool(st.session_state.pop("open_edit", False)))
    st.subheader("Next step")
    main_actions = st.columns(2)
    if main_actions[0].button("Edit", disabled=bool(publishing), help="Change caption, YouTube title or local publish time."):
        st.session_state["open_edit"] = True
        st.rerun()
    if item.editorial_status == "active" and record.get("status", "pending") == "pending":
        if main_actions[1].button("Generate video", type="primary",
                                  help="Create a video from this script using the current generation settings."):
            _queue_action(panel, "generate", cid)
    elif item.editorial_status == "active" and record.get("status") == "ready":
        if main_actions[1].button("Schedule this video", type="primary", disabled=not panel.s.publish_enabled,
                                  help="Review the posts before any video upload or remote scheduling starts."):
            _queue_action(panel, "publish", cid)
    with st.expander("More actions"):
        _plan(panel, cid)
        a, b, c = st.columns(3)
        if a.button("Regenerate video", disabled=bool(skip_reason(record)) or item.editorial_status != "active",
                    help="Create a fresh MP4 from this script using the current generation settings."):
            _queue_action(panel, "regenerate", cid)
        if b.button("Skip", disabled=item.editorial_status != "active" or bool(publishing),
                    help="Keep this item and its file, but exclude it from future publishing."):
            _queue_action(panel, "skip", cid)
        if c.button("Archive", disabled=item.editorial_status == "archived",
                    help="Hide this item from daily views while preserving its history."):
            _queue_action(panel, "archive", cid)
        if st.button("Restore", disabled=item.editorial_status == "active",
                     help="Return a skipped or archived item to the active workflow."):
            _queue_action(panel, "restore", cid)
        with st.popover("Advanced actions", help="Manual recovery and queue deletion controls."):
            if st.button("Reset internal publishing state", disabled=not bool(publishing),
                         help="Manual recovery only, after you have removed the social posts yourself."):
                _queue_action(panel, "reset", cid)
            if st.button("Delete from queue", disabled=bool(publishing),
                         help="Remove the queue entry after a typed confirmation; local media and state history stay on disk."):
                _queue_action(panel, "delete", cid)


def _content(panel: ControlPanel) -> None:
    """Show a scannable library; one selected item opens the existing safe actions."""
    if st.session_state.get("selected_content"):
        _content_detail(panel)
        return
    queue, state = panel.load()
    st.caption("Your video ideas, ready files and publishing progress in one place.")
    if count := st.session_state.pop("batch_success", None):
        st.success(f"{count} contents imported. They are now waiting for generation.")
    _add_form(panel)
    search, visibility = st.columns([3, 1])
    term = search.text_input("Search content", placeholder="Search by topic", help="Filters this local list only.").casefold().strip()
    scope = visibility.selectbox("Show", ["Active", "Archived", "All"], help="Archived items remain saved.")
    rows = {row["ID"]: row for row in panel.view(include_archived=True)["rows"]}
    items = sorted(queue.items, key=lambda item: item.publish_at)
    items = [item for item in items if (scope == "All" or
             (item.editorial_status == "archived") == (scope == "Archived")) and term in item.subject.casefold()]
    if not items:
        st.info("No content matches this view. Try another filter or add a new item.")
    thumbnails = ThumbnailService(panel.s.state_path.parent / "thumbnails", panel.s.ffmpeg_binary)
    publisher = Publisher(panel.s, queue, state)
    for item in items:
        row = rows[item.id]
        overall = content_status(item, state.get(item.id), row)
        when = _local(item.publish_at, panel.s.timezone)
        icon, title, status, open_col, more = st.columns(
            [.6, 3.4, 2, 1, .6], vertical_alignment="center", wrap=True)
        thumbnail = None
        if state.get(item.id).get("status") == "ready":
            try:
                source = publisher._video_path(item, state.get(item.id))
                if source.stat().st_size >= 1024:
                    thumbnail = thumbnails.get(item.id, source)
            except (ValueError, OSError):
                pass
        if thumbnail:
            icon.image(str(thumbnail), width=72)
        else:
            icon.write("▶" if state.get(item.id).get("status") == "ready" else "○")
        title.markdown(f"**{item.subject}**")
        title.caption(f"{when:%a %d %b · %H:%M} · " + " · ".join(
            f"{PLATFORM_NAMES[p]} {STATUS_ICON[status_label(row[p.title()])]}" for p in item.platforms))
        status.caption(f"{STATUS_ICON[overall]} {overall}")
        if open_col.button("Open", key=f"open-{item.id}", help="View video, details and the next safe action."):
            _open_content(item.id)
        if more.button("⋯", key=f"content-menu-{item.id}", help="Edit, organize or regenerate this item."):
            st.session_state["content_menu"] = None if st.session_state.get("content_menu") == item.id else item.id
            st.rerun()
        if st.session_state.get("content_menu") == item.id:
            record = state.get(item.id)
            protected = bool(record.get("publishing"))
            actions = st.columns(4)
            if actions[0].button("Edit", key=f"library-edit-{item.id}", disabled=protected,
                                 help="Open a short form for caption, YouTube title and publish time."):
                st.session_state["open_edit"] = True
                _open_content(item.id)
            if actions[1].button("Skip", key=f"library-skip-{item.id}", disabled=protected or item.editorial_status != "active",
                                 help="Keep this content but exclude it from future publishing."):
                _queue_action(panel, "skip", item.id)
            if actions[2].button("Archive", key=f"library-archive-{item.id}", disabled=item.editorial_status == "archived",
                                 help="Hide this item while preserving all history."):
                _queue_action(panel, "archive", item.id)
            if actions[3].button("Regenerate video", key=f"library-regenerate-{item.id}",
                                 disabled=bool(skip_reason(record)) or item.editorial_status != "active",
                                 help="Generate a fresh MP4 after reviewing the action."):
                _queue_action(panel, "regenerate", item.id)
        st.divider()


def _system(panel: ControlPanel, data: dict, fresh: bool) -> None:
    st.caption("Technical service status and deliberate refresh controls. Opening this page makes no remote requests.")
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
    st.caption("MPT address: " + panel.settings_view()["MPT URL"] + " · Availability is not checked automatically.")
    actions = st.columns(2)
    if actions[0].button("Refresh publishing status", key="system-refresh",
                         help="Read the latest Buffer schedule. This uses API quota but creates no posts."):
        _refresh_publishing(panel)
    if actions[1].button("Reconcile saved posts", help="Read Buffer and update local saved statuses. No posts are created."):
        _refresh_publishing(panel, sync=True)
    _usage(panel, data)
    with st.expander("Advanced publishing controls"):
        _plan(panel)
        if st.button("Fill schedule", key="system-fill", disabled=not panel.s.publish_enabled,
                     help="Review ready videos and confirm before uploading or scheduling them."):
            _queue_action(panel, "fill")


def _friendly(message: str) -> str:
    value = message.lower()
    if "past" in value:
        return "Scheduled time has already passed. Choose a new time or skip this item."
    if "fail" in value or "error" in value:
        return "The last attempt failed. Open the details and review this item before trying again."
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
    issues = grouped_issues(data)
    plan = st.session_state.get("plan")
    if plan:
        issues.extend({"Content ID": issue.get("id"), "Platform": issue.get("platform"),
                       "What happened": issue["error"], "Recommended action": recommendation(issue["error"])}
                      for issue in plan.issues)
    queue, state = panel.load()
    if not issues:
        st.success("Nothing needs your attention.")
        st.caption("Remote changes appear after you explicitly refresh publishing status.")
        return
    st.caption(f"{len(issues)} items to review · Technical details stay folded away.")
    for index, issue in enumerate(issues):
        cid = issue.get("Content ID")
        item = queue.by_id().get(cid)
        with st.container(border=True):
            title = ("Publishing time passed" if "past" in issue["What happened"].lower() else
                     f"{issue.get('Platform', 'Kitok').title()} failed to publish"
                     if "fail" in issue["What happened"].lower() else
                     f"{issue.get('Platform', 'Kitok').title()} needs attention")
            st.write(f"**{title}**")
            if item:
                st.caption(item.subject + " · " + _local(item.publish_at, panel.s.timezone).strftime("%d %b, %H:%M"))
            st.write(_friendly(issue["What happened"]))
            st.caption(issue["Recommended action"])
            with st.expander("Technical details"):
                for platform in issue.get("platforms", [issue.get("Platform", "Kitok")]):
                    st.code(f"{platform}: {issue['What happened']}")
                if item:
                    st.caption(f"Content ID: {cid}")
            if item:
                buttons = st.columns(3)
                if buttons[0].button("Reschedule", key=f"reschedule-{index}",
                                     disabled=bool(state.get(cid).get("publishing")),
                                     help="Open the local publish time editor. Existing remote posts need separate review."):
                    st.session_state["open_edit"] = True
                    _open_content(cid)
                if buttons[1].button("View video", key=f"attention-view-{index}",
                                     help="Inspect the local video and publishing history."):
                    _open_content(cid)
                if buttons[2].button("Skip", key=f"attention-skip-{index}",
                                     disabled=bool(state.get(cid).get("publishing")) or item.editorial_status != "active",
                                     help="Exclude this item from future publishing; keep its history and file."):
                    _queue_action(panel, "skip", cid)


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
        target = st.session_state.pop("nav_target")
        if target in PAGES:
            st.session_state["page"] = target
            st.session_state.pop("secondary_page", None)
        else:
            st.session_state["secondary_page"] = target
    st.sidebar.radio("Workspace", PAGES, key="page",
                     on_change=lambda: st.session_state.pop("secondary_page", None))
    st.sidebar.divider()
    st.sidebar.caption("MORE")
    if st.sidebar.button("Settings", help="See your current local preferences."):
        st.session_state["secondary_page"] = "Settings"
        st.rerun()
    if st.sidebar.button("Advanced / System", help="View cached service details and deliberate refresh controls."):
        st.session_state["secondary_page"] = "Advanced / System"
        st.rerun()
    with st.sidebar.popover("? How Kitok works", help="A short guide to the content and publishing steps."):
        st.write("1. Add content to your queue.")
        st.write("2. Kitok generates a video.")
        st.write("3. Ready means the video can be scheduled.")
        st.write("4. Scheduled means Buffer has it; your PC can be off.")
        st.write("5. Published means the social platform posted it.")
        st.caption("Cloudinary temporarily hosts the video for Buffer. Buffer schedules and publishes your posts.")
    page = st.session_state.get("secondary_page") or st.session_state["page"]
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
    data = panel.view()
    if page == "Home":
        _dashboard(panel, data)
    elif page == "Calendar":
        _calendar(panel, data)
    elif page == "Content":
        _content(panel)
    elif page == "Advanced / System":
        _system(panel, data, fresh)
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
