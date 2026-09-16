"""Thin Streamlit UI: rendering is local; services own all confirmed actions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from .buffer_client import PLATFORMS
from .buffer_usage import usage_rows
from .control_panel import ControlPanel, disclosure
from .publisher import Publisher
from .regeneration import skip_reason

STATUS_LABELS = {"pending": "⚪ Pending", "submitted": "🔵 Generating", "generating": "🔵 Generating",
                 "generated": "🔵 Validating", "ready": "🟢 Ready", "scheduled": "🟡 Scheduled",
                 "sending": "🟡 Sending", "sent": "✅ Published", "failed": "🔴 Failed",
                 "error": "🔴 Failed", "unknown": "⚠ Attention", "creating": "⚠ Attention",
                 "needs_attention": "⚠ Attention", "needs_approval": "⚠ Needs approval",
                 "draft": "⚠ Draft", "skipped": "⏭ Skipped"}


def _queue_action(panel: ControlPanel, kind: str, content_id=None, **kwargs) -> None:
    try:
        st.session_state["pending_action"] = panel.prepare_action(kind, content_id, **kwargs)
        st.rerun()
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))


def _confirmation(panel: ControlPanel) -> None:
    action = st.session_state.get("pending_action")
    if action is None:
        return
    with st.container(border=True):
        st.subheader("Review before continuing")
        st.json(action.summary)
        if action.rows:
            st.dataframe([{key: row.get(key) for key in ("id", "platform", "local_publish_at", "caption", "disclosure")}
                          for row in action.rows], hide_index=True, use_container_width=True)
        left, right = st.columns(2)
        if left.button("Cancel", key="cancel-action", use_container_width=True):
            st.session_state.pop("pending_action", None)
            st.rerun()
        disabled = action.kind in {"publish", "fill"} and not panel.s.publish_enabled
        if right.button("Confirm", key="confirm-action", type="primary", disabled=disabled, use_container_width=True):
            # Consume before execution so a rerun cannot repeat the write.
            st.session_state.pop("pending_action", None)
            try:
                with st.spinner("Working…"):
                    st.session_state["action_result"] = panel.execute(action, confirmed=True)
            except (ValueError, RuntimeError, OSError) as error:
                st.session_state["action_error"] = str(error)
            st.rerun()


def _usage(panel: ControlPanel, data: dict) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Buffer API usage")
        rows = usage_rows(data["buffer_usage"])
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
        else:
            st.info("No cached usage yet. Refresh Buffer to read response headers.")
        st.caption("Updated: " + data["buffer_usage"].get("refreshed_at", "never"))
    with right:
        st.subheader("Cloudinary")
        st.caption(f"Known uploaded videos: {data['counts'].get('uploaded', 0)}")
        report = data["cloudinary_usage"]
        values = report.get("data", {})
        st.dataframe([{"Metric": name.title(), "Usage": str(values.get(name, {}).get("usage", "unknown")),
                       "Limit": str(values.get(name, {}).get("limit", "shared credits / unknown"))}
                      for name in ("storage", "bandwidth", "transformations", "credits")], hide_index=True)
        st.caption("Updated: " + report.get("refreshed_at", "never") + " · Storage/bandwidth are bytes; usage is reported periodically.")
        if panel.s.cloudinary_usage_guard:
            st.caption(f"Upload guard enabled · stop at {panel.s.cloudinary_usage_threshold:.0%}; fresh usage required.")
        if st.button("Refresh Cloudinary usage"):
            try:
                panel.cloud_usage.refresh()
                st.rerun()
            except (ValueError, RuntimeError, OSError) as error:
                st.error(str(error))


def _occupancy(panel: ControlPanel, data: dict, fresh: bool) -> None:
    source = "LIVE" if fresh else ("CACHED" if data["snapshot"] else "LOCAL ESTIMATE")
    st.subheader("Buffer queue")
    st.caption(f"{source} · Updated: {data['snapshot'].get('refreshed_at', 'never')} · Target {panel.s.buffer_max_scheduled_per_channel} per channel")
    for column, platform in zip(st.columns(3), PLATFORMS):
        column.metric(platform.title(), f"{data['occupancy'][platform]} / {panel.s.buffer_max_scheduled_per_channel}")


def _plan(panel: ControlPanel, content_id=None) -> None:
    if st.button("Preview publishing plan", key=f"preview-{content_id or 'all'}"):
        try:
            st.session_state["plan"] = panel.preview(content_id)
            st.session_state["plan_scope"] = content_id
        except (ValueError, RuntimeError, OSError) as error:
            st.error(str(error))
    plan = st.session_state.get("plan")
    if plan is not None and st.session_state.get("plan_scope") == content_id:
        st.info("OFFLINE DRY-RUN — remote Buffer occupancy is not refreshed")
        st.caption(f"Occupancy: {plan.occupancy_source} · snapshot {plan.refreshed_at or 'not available'}")
        st.dataframe([{key: row.get(key) for key in ("id", "platform", "local_publish_at", "dueAt", "caption", "title", "video_path", "disclosure")}
                      for row in plan.rows], hide_index=True, use_container_width=True)
        if plan.issues:
            st.dataframe(plan.issues, hide_index=True, use_container_width=True)


def _detail(panel: ControlPanel) -> None:
    queue, state = panel.load()
    if not queue.items:
        st.info("The content queue is empty.")
        return
    content_id = st.selectbox("Content item", list(queue.by_id()),
                              format_func=lambda cid: f"{cid} — {queue.by_id()[cid].subject}")
    item = queue.by_id()[content_id]
    record = state.get(content_id)
    st.subheader(item.subject)
    local = item.publish_at.astimezone(ZoneInfo(panel.s.timezone))
    st.caption(f"{content_id} · {local:%d %B %Y, %H:%M %Z}")
    st.write(item.caption)
    st.write(disclosure(panel.s))
    video_tab, publishing_tab, script_tab = st.tabs(["Video & generation", "Publishing", "Script"])
    with video_tab:
        try:
            path = Publisher(panel.s, queue, state)._video_path(item, record)
        except ValueError:
            path = None
        st.write({"Generation": STATUS_LABELS.get(record.get("status", "pending"), record.get("status")),
                  "Attempts": record.get("attempts", 0), "MPT task": record.get("mpt_task_id"),
                  "MPT progress": record.get("mpt_progress"), "MP4 path": str(path) if path else "missing",
                  "File size": path.stat().st_size if path else None,
                  "Last error": record.get("last_error")})
        st.json(record.get("validation", {"status": "not validated yet"}))
        if path:
            st.video(str(path))
    with publishing_tab:
        publishing = record.get("publishing", {})
        st.write("Cloudinary")
        st.json(publishing.get("cloudinary", {"status": "not uploaded"}))
        for platform in PLATFORMS:
            st.write(platform.title())
            st.json(publishing.get("buffer", {}).get(platform, {"status": "not scheduled"}))
    with script_tab:
        st.text(item.script)
    _plan(panel, content_id)
    publish, regenerate, reset = st.columns(3)
    if publish.button("Publish selected video", disabled=not panel.s.publish_enabled or record.get("status") != "ready"):
        _queue_action(panel, "publish", content_id)
    reason = skip_reason(record)
    if regenerate.button("Regenerate selected video", disabled=bool(reason), help=reason):
        _queue_action(panel, "regenerate", content_id)
    if reset.button("Reset publishing state"):
        _queue_action(panel, "reset", content_id)
    if reason:
        st.caption("Regeneration unavailable: " + reason)
    with st.expander("Change publish time / edit title and caption"):
        if record.get("publishing"):
            st.info("Publishing has started. Review remote posts and publishing state before editing.")
        else:
            with st.form(f"edit-content-{content_id}"):
                title = st.text_input("Title / topic", item.subject)
                caption = st.text_area("Caption", item.caption)
                day = st.date_input("Publish date", local.date())
                hour = st.time_input(f"Publish time ({panel.s.timezone})", local.time().replace(tzinfo=None))
                if st.form_submit_button("Review changes"):
                    due = datetime.combine(day, hour, tzinfo=ZoneInfo(panel.s.timezone))
                    roundtrip = due.astimezone(timezone.utc).astimezone(due.tzinfo)
                    if roundtrip != due or due.replace(fold=1).utcoffset() != due.utcoffset():
                        st.error("This local time is missing or ambiguous because of daylight saving. Choose another time.")
                    else:
                        _queue_action(panel, "edit", content_id,
                                      changes={"subject": title, "caption": caption, "publish_at": due.isoformat()})


def main() -> None:
    """Render local pages; remote calls run only in explicit button handlers."""
    st.set_page_config(page_title="Kitok · Control panel", page_icon="🎬", layout="wide")
    try:
        panel = ControlPanel()
        panel.load()
    except (ValueError, RuntimeError, OSError):
        st.error("Kitok configuration, queue or state could not be loaded. Check .env and the local JSON files.")
        return
    st.sidebar.title("🎬 Kitok")
    page = st.sidebar.radio("Workspace", ["Overview", "Upcoming Content", "Content Detail", "Buffer", "Attention", "Settings"])
    st.sidebar.caption(f"Local workspace · {panel.s.timezone}")
    if panel.s.publish_enabled:
        st.sidebar.success("PUBLISH_ENABLED · ON")
    else:
        st.sidebar.warning("PUBLISH_ENABLED · OFF")
        st.sidebar.caption("Publishing is disabled. Preview remains available. Change PUBLISH_ENABLED in .env to enable publishing.")
    st.title(page)
    st.caption("Ready videos are local files. Scheduled posts are in Buffer. Published posts have been sent.")
    _confirmation(panel)
    if "action_result" in st.session_state:
        st.success("Action finished")
        st.json(st.session_state.pop("action_result"))
    if "action_error" in st.session_state:
        st.error(st.session_state.pop("action_error"))
    fresh = False
    left, right = st.columns([1, 1])
    if left.button("Refresh status", help="Reload local queue, files and state; no service requests."):
        st.rerun()
    if right.button("Refresh Buffer", help="Read current Buffer channels and occupancy; no posts are created."):
        try:
            with st.spinner("Refreshing Buffer…"):
                panel.refresh_buffer()
            fresh = True
        except (ValueError, RuntimeError, OSError) as error:
            st.error(str(error))
    data = panel.view()
    if page == "Overview":
        for column, label, value in zip(st.columns(4), ["READY VIDEOS", "SCHEDULED POSTS", "PUBLISHED", "ATTENTION / ERRORS"],
                                         [data["counts"].get("ready", 0), data["counts"].get("scheduled", 0),
                                          data["counts"].get("published", 0), len(data["issues"])]):
            column.metric(label, value)
        _occupancy(panel, data, fresh)
        st.write(disclosure(panel.s))
        _plan(panel)
        if st.button("Fill Buffer", disabled=not panel.s.publish_enabled, type="primary"):
            _queue_action(panel, "fill")
        _usage(panel, data)
    elif page == "Upcoming Content":
        rows = [{key: STATUS_LABELS.get(value, value) if key in ("Generation", "Tiktok", "Instagram", "Youtube") else value
                 for key, value in row.items()} for row in data["rows"]]
        st.dataframe(rows, hide_index=True, use_container_width=True)
    elif page == "Content Detail":
        _detail(panel)
    elif page == "Buffer":
        _occupancy(panel, data, fresh)
        st.subheader("Connected channels")
        st.dataframe(list(data["snapshot"].get("channels", {}).values()), hide_index=True, use_container_width=True)
        st.subheader("Next scheduled posts · cached")
        st.dataframe(data["scheduled_posts"], hide_index=True, use_container_width=True)
        st.caption("Last state sync: " + data["last_sync"])
        if st.button("Sync state", help="Read Buffer and reconcile saved IDs; updates local state only."):
            try:
                st.session_state["action_result"] = panel.refresh_buffer(sync=True)
                st.rerun()
            except (ValueError, RuntimeError, OSError) as error:
                st.error(str(error))
        if st.button("Fill Buffer", disabled=not panel.s.publish_enabled, type="primary"):
            _queue_action(panel, "fill")
        _usage(panel, data)
    elif page == "Attention":
        from .control_panel import recommendation
        last_plan = st.session_state.get("plan")
        if last_plan:
            for issue in last_plan.issues:
                data["issues"].append({"Content ID": issue.get("id"), "Platform": issue.get("platform"),
                                       "What happened": issue["error"],
                                       "Recommended action": recommendation(issue["error"])})
        if data["issues"]:
            st.dataframe(data["issues"], hide_index=True, use_container_width=True)
        else:
            st.success("No known local issues. Remote status is refreshed only when requested.")
    else:
        st.info("Settings are read-only here. Values come from environment variables and the project .env file.")
        st.table([{"Setting": key, "Value": str(value)} for key, value in panel.settings_view().items()])


if __name__ == "__main__":
    main()
