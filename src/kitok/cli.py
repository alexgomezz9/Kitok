from __future__ import annotations
import argparse
from rich.console import Console
from rich.table import Table
from .config import PROJECT_ROOT, Settings
from .logging_setup import configure_logging
from .models import ContentQueue
from .mpt_client import MPTClient, MPTError
from .pipeline import Pipeline, load_preset
from .publish_plan import generate_publish_plan
from .regeneration import ReadyRegenerator
from .state import StateStore
from .video_validator import VideoValidator

console=Console()

def parser():
    p=argparse.ArgumentParser(description="Kitok -> MoneyPrinterTurbo pipeline")
    p.add_argument("--id",action="append",dest="ids")
    p.add_argument("--publish-id",metavar="CONTENT_ID")
    p.add_argument("--reset-publish-id",metavar="CONTENT_ID",action="append")
    p.add_argument("--confirm",action="store_true")
    p.add_argument("--live",action="store_true")
    p.add_argument("--refresh",action="store_true")
    mode=p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run",action="store_true")
    p.add_argument("--retry-failed",action="store_true")
    p.add_argument("--regenerate-all-ready",action="store_true")
    mode.add_argument("--status",action="store_true")
    mode.add_argument("--check-mpt",action="store_true")
    mode.add_argument("--plan",action="store_true")
    for flag in ("buffer-usage", "cloudinary-usage", "dashboard"):
        mode.add_argument(f"--{flag}",action="store_true")
    for flag in ("buffer-check", "buffer-channels", "publish-ready", "sync-buffer-status",
                 "buffer-maintain", "publish-dry-run"):
        mode.add_argument(f"--{flag}",action="store_true")
    p.add_argument("-v","--verbose",action="store_true")
    return p

def load_all(*, read_only=False):
    s=Settings()
    if not read_only: s.ensure_directories()
    q=ContentQueue.load(s.queue_path); st=StateStore(s.state_path,create_parent=not read_only)
    pp=s.mpt_preset_path if s.mpt_preset_path.is_absolute() else (PROJECT_ROOT/s.mpt_preset_path).resolve()
    return s,q,st,load_preset(pp)

def show_status(q,st):
    t=Table(title="Kitok status")
    for c in ["ID","Publish","Status","Attempts","MPT %","Last error"]: t.add_column(c)
    for item in sorted(q.items,key=lambda x:x.publish_at):
        r=st.get(item.id)
        t.add_row(item.id,item.publish_at.strftime("%Y-%m-%d %H:%M"),r.get("status","pending"),
                  str(r.get("attempts",0)),str(r.get("mpt_progress","")),str(r.get("last_error") or ""))
    console.print(t)

def main(argv=None):
    a=parser().parse_args(argv)
    publishing_modes = ("buffer_check", "buffer_channels", "publish_ready",
                        "sync_buffer_status", "buffer_maintain", "publish_dry_run")
    if ((a.live and not a.publish_dry_run)
            or (a.refresh and not (a.buffer_usage or a.cloudinary_usage))):
        console.print("Usage error: --live requires --publish-dry-run; --refresh requires a usage command.")
        return 2
    if a.buffer_usage or a.cloudinary_usage or a.dashboard:
        if a.ids or a.publish_id or a.reset_publish_id or a.confirm or a.regenerate_all_ready or a.retry_failed:
            console.print("Usage error: dashboard/usage commands cannot be combined with content actions.")
            return 2
        if a.dashboard:
            import sys
            from streamlit.web import cli as streamlit_cli
            sys.argv = ["streamlit", "run", str(PROJECT_ROOT / "dashboard.py"),
                        "--server.address=127.0.0.1", "--browser.gatherUsageStats=false"]
            return streamlit_cli.main()
        return usage_main(a)
    if a.reset_publish_id or a.confirm:
        if (not a.reset_publish_id or len(a.reset_publish_id) != 1
                or a.ids or a.publish_id or a.regenerate_all_ready
                or a.retry_failed or a.dry_run or a.status or a.check_mpt or a.plan
                or any(getattr(a, flag) for flag in publishing_modes)):
            console.print("Usage error: --reset-publish-id may only be combined with --confirm.")
            return 2
        return reset_publishing_main(a)
    if a.regenerate_all_ready:
        if (a.ids or a.retry_failed or a.publish_id or a.status or a.check_mpt or a.plan
                or any(getattr(a, flag) for flag in publishing_modes)):
            console.print("Usage error: --regenerate-all-ready may only be combined with --dry-run.")
            return 2
        return regeneration_main(a)
    if a.publish_id and (a.ids or any(getattr(a, flag) for flag in publishing_modes
                                     if flag != "publish_dry_run")):
        console.print("Usage error: --publish-id may only be combined with --publish-dry-run.")
        return 2
    if a.publish_id or any(getattr(a, flag) for flag in publishing_modes):
        return publishing_main(a)
    try: s,q,st,preset=load_all()
    except Exception as e:
        console.print(f"[red]Startup error:[/red] {e}"); return 2
    configure_logging(s.logs_dir,a.verbose)

    if a.dry_run:
        v=VideoValidator(s.ffprobe_binary)
        console.print(f"[green]Queue OK[/green]: {len(q.items)} items")
        console.print(f"[green]Preset OK[/green]: {len(preset)} fields")
        console.print(f"MPT: {s.mpt_base_url}")
        console.print(f"READY_DIR: {s.ready_dir.expanduser()}")
        console.print("ffprobe: "+("OK" if v.ffprobe_available() else "NOT FOUND"))
        return 0 if v.ffprobe_available() else 1

    if a.status: show_status(q,st); return 0
    if a.plan:
        generate_publish_plan(q,st.all(),s.local_ready_dir)
        if s.ready_dir.expanduser().resolve()!=s.local_ready_dir.resolve():
            generate_publish_plan(q,st.all(),s.ready_dir.expanduser())
        console.print("[green]Plan regenerated[/green]"); return 0

    client=MPTClient(s.mpt_base_url,s.mpt_api_key,s.mpt_request_timeout_seconds,
                     s.http_retry_attempts,s.http_retry_base_seconds)
    try:
        if a.check_mpt:
            console.print("[green]MPT reachable[/green]")
            console.print(client.check()); return 0
        ids=set(a.ids) if a.ids else None
        if ids:
            missing=ids-set(q.by_id())
            if missing:
                console.print(f"[red]Unknown ids:[/red] {', '.join(sorted(missing))}"); return 2
        Pipeline(s,q,st,client,preset).process(ids=ids,retry_failed=a.retry_failed)
        show_status(q,st); return 0
    except MPTError as e:
        console.print(f"[red]MPT error:[/red] {e}"); return 3
    finally:
        client.close()


def regeneration_main(args):
    try:
        s, q, state, preset = load_all(read_only=args.dry_run)
    except Exception as error:
        console.print(f"[red]Startup error:[/red] {error}")
        return 2
    client = None
    try:
        if not args.dry_run:
            configure_logging(s.logs_dir, args.verbose)
            client = MPTClient(s.mpt_base_url, s.mpt_api_key, s.mpt_request_timeout_seconds,
                               s.http_retry_attempts, s.http_retry_base_seconds)
        run = ReadyRegenerator(s, q, state, client, preset, print_line=console.print)
        summary = run.run(dry_run=args.dry_run)
        label = "Dry-run" if args.dry_run else "Regeneration"
        console.print(f"{label} summary: regenerated={summary.regenerated} "
                      f"failed={summary.failed} skipped={summary.skipped}"
                      + (f" would_regenerate={summary.would_regenerate}" if args.dry_run else ""))
        return 1 if summary.failed else 0
    except (OSError, RuntimeError, ValueError) as error:
        console.print(f"[red]Regeneration error:[/red] {error}")
        return 3
    finally:
        if client is not None:
            client.close()


def reset_publishing_main(args):
    try:
        settings = Settings()
        queue = ContentQueue.load(settings.queue_path)
        content_id = args.reset_publish_id[0]
        if content_id not in queue.by_id():
            console.print(f"Unknown content ID: {content_id}", markup=False)
            return 2
        state = StateStore(settings.state_path, create_parent=False)
        if not args.confirm:
            console.print(f"Publishing state for {content_id} to clear:", markup=False)
            console.print_json(data=state.get(content_id).get("publishing") or {})
            console.print("No changes made. Add --confirm to reset this item's publishing state.")
            return 0
        if "publishing" not in state.get(content_id):
            console.print(f"Publishing state for {content_id} to clear:", markup=False)
            console.print_json(data={})
            console.print("No publishing state to clear.")
            return 0
        with state.publishing_lock():
            record = state.get(content_id)
            publishing = record.get("publishing") or {}
            console.print(f"Publishing state for {content_id} to clear:", markup=False)
            console.print_json(data=publishing)
            if "publishing" not in record:
                console.print("No publishing state to clear.")
                return 0
            state.clear_publishing(content_id)
        console.print(f"Publishing state cleared for {content_id}.", markup=False)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        console.print(f"Publishing reset error: {error}", markup=False)
        return 3


def publishing_main(args):
    from .buffer_client import BufferClient, BufferError, select_channels
    from .publisher import Publisher
    from .service_cache import buffer_cache

    client = None
    try:
        s = Settings()
        if (args.publish_ready or args.buffer_maintain or
                (args.publish_id and not args.publish_dry_run)) and not s.publish_enabled:
            raise BufferError("Publishing disabled: set PUBLISH_ENABLED=true")
        key = s.buffer_api_key.get_secret_value()
        cache = buffer_cache(s, persist=not args.publish_dry_run)
        if args.live and not key:
            raise BufferError("BUFFER_API_KEY is required for --live")
        if key and (not args.publish_dry_run or args.live):
            client = BufferClient(key, publish_enabled=s.publish_enabled and not args.publish_dry_run,
                                  timeout=s.buffer_request_timeout_seconds, cache=cache,
                                  discovery_ttl=s.buffer_discovery_ttl_seconds)
        if args.buffer_check or args.buffer_channels:
            if client is None:
                raise BufferError("BUFFER_API_KEY is not configured")
            organizations = client.organizations()
            console.print_json(data={"organizations": organizations})
            org, _ = select_channels(organizations, [], s.buffer_organization_id)
            channels = client.channels(org)
            console.print_json(data={"organization_id": org, "channels": channels})
            if args.buffer_channels:
                return 0
            _, selected = select_channels(organizations, channels, org, s.buffer_channel_ids)
            from .state import utc_now_iso
            cache.put("discovery", {"configuration": [s.buffer_organization_id, s.buffer_channel_ids],
                                   "organization_id": org, "channels": channels, "selected": selected,
                                   "refreshed_at": utc_now_iso()})
            console.print_json(data={"selected": {p: c["id"] for p, c in selected.items()},
                                     "publish_enabled": s.publish_enabled,
                                     "missing_services": sorted(set(s.buffer_channel_ids) - set(selected))})
            console.print("Buffer read-only check completed. No uploads or mutations.")
            return 0
        q = ContentQueue.load(s.queue_path)
        ids = {args.publish_id} if args.publish_id else (set(args.ids) if args.ids else None)
        if ids and ids - set(q.by_id()):
            raise ValueError("Unknown ids: " + ", ".join(sorted(ids - set(q.by_id()))))
        state = StateStore(s.state_path, create_parent=not args.publish_dry_run)
        publisher = Publisher(s, q, state, client, cache=cache)
        if args.publish_dry_run:
            plan = (publisher.plan_one(args.publish_id) if args.publish_id
                    else publisher.plan(ids))
            console.print("Publishing dry-run: no uploads, mutations, or state changes.")
            if plan.offline:
                console.print("OFFLINE DRY-RUN — remote Buffer occupancy is not refreshed")
            else:
                console.print("LIVE DRY-RUN — remote occupancy refreshed; no local or remote writes")
            _print_publish_summary(plan, state, args.publish_id)
            return 1 if plan.issues else 0
        if args.publish_id:
            result = publisher.publish_one(
                args.publish_id,
                before_execute=lambda plan: _print_publish_summary(plan, state, args.publish_id),
            )
            console.print_json(data=result)
            return 1 if result["attention"] else 0
        if args.sync_buffer_status:
            result = publisher.sync()
        else:
            result = publisher.publish(ids, maintain=args.buffer_maintain,
                                       before_execute=lambda plan: console.print(
                                           f"Estimated Buffer requests this run: {plan.estimated_requests} "
                                           f"+ {s.buffer_request_reserve} reserve"))
        console.print_json(data=result)
        if args.buffer_maintain:
            for label, key in (("BEFORE", "before"), ("CREATED", "created_by_platform"),
                               ("AFTER (estimated)", "after_estimated")):
                console.print(label)
                for platform, count in result.get(key, {}).items():
                    console.print(f"{platform.title():12} " + (f"+{count}" if key == "created_by_platform"
                                                            else f"{count} / {s.buffer_max_scheduled_per_channel}"))
            print_buffer_usage(client.usage)
        return 1 if result["attention"] else 0
    except (BufferError, ValueError, OSError, RuntimeError) as error:
        console.print("Publishing error: " + str(error), markup=False)
        return 3
    finally:
        if client is not None:
            client.close()


def _print_publish_summary(plan, state, content_id=None):
    rows = [{key: row.get(key) for key in ("id", "platform", "local_publish_at", "dueAt", "caption", "title", "video_path", "disclosure")}
            for row in plan.rows]
    payload = {"selected_id": content_id, "scheduled_counts": plan.counts,
               "occupancy_source": plan.occupancy_source, "occupancy_refreshed_at": plan.refreshed_at,
               "cloudinary": None, "would_schedule": rows,
               "needs_attention": plan.issues, "deferred": plan.deferred}
    if content_id:
        cloudinary = state.get(content_id).get("publishing", {}).get("cloudinary", {})
        payload["cloudinary"] = "reuse existing URL" if cloudinary.get("url") else "upload once"
    console.print("Pre-publish summary. No write has been performed yet.")
    console.print_json(data=payload)


def print_buffer_usage(usage: dict) -> None:
    """Display cached/header-derived usage without fetching anything."""
    from .buffer_usage import usage_rows
    console.print("Buffer API usage")
    rows = usage_rows(usage)
    for row in rows:
        console.print(f"{row['Window']}: {row['Remaining']} / {row['Quota']} remaining; reset {row['Reset']}")
    if not rows:
        console.print("No cached rate-limit headers. Use --buffer-usage --refresh.")
    console.print(f"Updated: {usage.get('refreshed_at', 'never')}")
    if usage.get("retry_at"):
        console.print(f"Cooldown until: {usage['retry_at']}")


def usage_main(args) -> int:
    """Read local usage by default; explicit refresh performs service reads only."""
    from .buffer_client import BufferClient
    from .cloudinary_usage import CloudinaryUsage
    from .service_cache import buffer_cache
    try:
        settings = Settings()
        if args.cloudinary_usage:
            service = CloudinaryUsage(settings)
            report = service.refresh() if args.refresh else service.cached()
            console.print("Cloudinary usage — " + ("refreshed" if args.refresh else "cached"))
            console.print_json(data=report or {"status": "unknown; use --refresh"})
        else:
            cache = buffer_cache(settings)
            report = cache.get("usage")
            if args.refresh:
                client = BufferClient(settings.buffer_api_key.get_secret_value(), cache=cache,
                                      timeout=settings.buffer_request_timeout_seconds)
                try:
                    report = client.refresh_usage()
                finally:
                    client.close()
            print_buffer_usage(report)
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        console.print(f"Usage error: {error}", markup=False)
        return 3
