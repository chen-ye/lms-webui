from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
import httpx
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from .indexer import HostModelIndex, get_lmstudio_home
from .service import (
    control_service,
    get_service_status,
    install_service,
    uninstall_service,
)

app = typer.Typer(
    name="lms-webui",
    help="Control-plane WebUI and stateless host proxy for LM Studio's /api/v1 model management REST API.",
)
service_app = typer.Typer(
    name="service",
    help="Register and manage lms-webui as a persistent background service (macOS launchd, Linux systemd, or Windows HKCU Run + pythonw.exe).",
)
app.add_typer(service_app, name="service")

console = Console()


@app.command("serve")
def serve_cmd(
    port: int = typer.Option(8420, "--port", "-p", help="Port to bind the WebUI server"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host interface to bind"),
    lmstudio_url: str = typer.Option(
        os.environ.get("LMSTUDIO_URL", "http://localhost:1234"),
        "--lmstudio-url",
        "-u",
        help="Upstream LM Studio API Server URL",
    ),
    lmstudio_home: Optional[str] = typer.Option(
        None,
        "--lmstudio-home",
        help="Path to ~/.lmstudio directory on this host",
    ),
    api_token: Optional[str] = typer.Option(
        None,
        "--api-token",
        help="Optional LM Studio API token (defaults to $LM_API_TOKEN)",
    ),
) -> None:
    """Start the LM Studio Model Manager WebUI and REST proxy server."""
    os.environ["LMS_WEBUI_PORT"] = str(port)
    os.environ["LMS_WEBUI_HOST"] = host
    os.environ["LMSTUDIO_URL"] = lmstudio_url.rstrip("/")
    if lmstudio_home:
        os.environ["LMSTUDIO_HOME"] = str(Path(lmstudio_home).expanduser().resolve())
    if api_token:
        os.environ["LM_API_TOKEN"] = api_token

    console.print(
        f"[bold green]Starting LM Studio Model Manager WebUI on http://{host}:{port}[/bold green]"
    )
    console.print(f"  • Upstream LM Studio : [cyan]{os.environ['LMSTUDIO_URL']}[/cyan]")
    console.print(f"  • Host LM Studio Dir : [dim]{get_lmstudio_home()}[/dim]")
    uvicorn.run("lmstudio_webui.server:app", host=host, port=port, reload=False)


@app.command("models")
def list_models_cmd(
    lmstudio_url: str = typer.Option(
        os.environ.get("LMSTUDIO_URL", "http://localhost:1234"),
        "--lmstudio-url",
        "-u",
        help="Upstream LM Studio API Server URL",
    ),
    lmstudio_home: Optional[str] = typer.Option(
        None,
        "--lmstudio-home",
        help="Path to ~/.lmstudio directory on this host",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON format"),
) -> None:
    """List models from LM Studio's REST API enriched with resolved local filesystem paths."""
    headers: dict[str, str] = {}
    tok = os.environ.get("LM_API_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    resp = httpx.get(f"{lmstudio_url.rstrip('/')}/api/v1/models", headers=headers, timeout=10.0)
    resp.raise_for_status()
    raw_models = resp.json().get("models") or []
    indexer = HostModelIndex(lmstudio_home)
    enriched = indexer.enrich_models(raw_models)

    if json_output:
        console.print(json.dumps([m.model_dump() for m in enriched], indent=2))
        return

    table = Table(title="LM Studio Models (Enriched Host Index)", header_style="bold cyan")
    table.add_column("Key", style="bold white")
    table.add_column("Type", style="magenta")
    table.add_column("Format", style="yellow")
    table.add_column("Quant", style="green")
    table.add_column("Origin", style="bold")
    table.add_column("Loaded", style="cyan")
    table.add_column("Resolved Disk Target(s)", style="dim")

    for m in enriched:
        q_name = (m.quantization or {}).get("name") or "-"
        origin_label = (
            f"remote ({m.device_name})"
            if m.origin == "remote" and m.device_name
            else m.origin
        )
        targets = ", ".join(m.disk_paths.delete_targets) or (m.disk_paths.concrete_dir or "-")
        table.add_row(
            m.selected_variant or m.key,
            m.type,
            m.format or "-",
            str(q_name),
            origin_label,
            str(len(m.loaded_instances)) if m.loaded_instances else "-",
            targets,
        )
    console.print(table)


@service_app.command("install")
def service_install_cmd(
    port: int = typer.Option(8420, "--port", "-p", help="Port for the WebUI service"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host for the WebUI service"),
    lmstudio_url: str = typer.Option(
        os.environ.get("LMSTUDIO_URL", "http://localhost:1234"),
        "--lmstudio-url",
        "-u",
        help="Upstream LM Studio API Server URL",
    ),
    lmstudio_home: Optional[str] = typer.Option(
        None,
        "--lmstudio-home",
        help="Path to ~/.lmstudio directory",
    ),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        help="Override target platform ('macos', 'linux', or 'windows')",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the generated service configuration and commands without installing",
    ),
) -> None:
    """Install and start lms-webui as a background user service on macOS (launchd), Linux (systemd), or Windows (HKCU Run + pythonw.exe)."""
    res = install_service(
        port=port,
        host=host,
        lmstudio_url=lmstudio_url.rstrip("/"),
        lmstudio_home=lmstudio_home,
        platform_override=platform,
        dry_run=dry_run,
    )
    if dry_run:
        console.print(f"[bold cyan]Dry-run ({res['platform']} / {res['service_manager']}):[/bold cyan]")
        console.print(f"  • Unit Path : [green]{res['unit_path']}[/green]")
        console.print(f"  • ExecStart : [yellow]{res['exec_start']}[/yellow]")
        console.print("\n[bold]Generated Unit Content:[/bold]")
        console.print(res["content"])
        return

    console.print(
        f"[bold green]Installed and started {res['service_name']} ({res['service_manager']})![/bold green]"
    )
    console.print(f"  • Unit Path : [cyan]{res['unit_path']}[/cyan]")
    console.print(f"  • WebUI URL : [green]http://localhost:{port}[/green]")


@service_app.command("uninstall")
def service_uninstall_cmd(
    platform: Optional[str] = typer.Option(None, "--platform", help="Override platform ('macos', 'linux', or 'windows')"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show uninstall commands without executing"),
) -> None:
    """Stop and remove the lms-webui background service."""
    res = uninstall_service(platform_override=platform, dry_run=dry_run)
    console.print(
        f"[bold green]Uninstalled {res['service_name']} ({res['unit_path']}).[/bold green]"
    )


@service_app.command("status")
def service_status_cmd(
    platform: Optional[str] = typer.Option(None, "--platform", help="Override platform ('macos', 'linux', or 'windows')"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON format"),
) -> None:
    """Show the installation and running status of the lms-webui background service."""
    st = get_service_status(platform_override=platform)
    if json_output:
        console.print(json.dumps(st.model_dump(), indent=2))
        return

    state_str = (
        "[bold green]running[/bold green]"
        if st.running
        else ("[yellow]installed (stopped)[/yellow]" if st.installed else "[dim]not installed[/dim]")
    )
    console.print(f"[bold cyan]LMS WebUI Service Status ({st.platform} / {st.service_manager})[/bold cyan]")
    console.print(f"  • Service Name : [white]{st.service_name}[/white]")
    console.print(f"  • State        : {state_str}")
    console.print(f"  • Target / Key : [dim]{st.unit_path}[/dim]")
    console.print(f"  • ExecStart    : [dim]{st.exec_start}[/dim]")
    console.print(f"  • Port / Host  : [cyan]{st.host}:{st.port}[/cyan] -> [yellow]{st.lmstudio_url}[/yellow]")


@service_app.command("start")
def service_start_cmd(
    platform: Optional[str] = typer.Option(None, "--platform", help="Override platform ('macos', 'linux', or 'windows')"),
) -> None:
    """Start the installed lms-webui service."""
    res = control_service("start", platform_override=platform)
    console.print(f"[bold green]Started service ({res['command']}).[/bold green]")


@service_app.command("stop")
def service_stop_cmd(
    platform: Optional[str] = typer.Option(None, "--platform", help="Override platform ('macos', 'linux', or 'windows')"),
) -> None:
    """Stop the running lms-webui service."""
    res = control_service("stop", platform_override=platform)
    console.print(f"[bold yellow]Stopped service ({res['command']}).[/bold yellow]")


@service_app.command("restart")
def service_restart_cmd(
    platform: Optional[str] = typer.Option(None, "--platform", help="Override platform ('macos', 'linux', or 'windows')"),
) -> None:
    """Restart the lms-webui service."""
    res = control_service("restart", platform_override=platform)
    console.print(f"[bold green]Restarted service ({res['command']}).[/bold green]")


if __name__ == "__main__":
    app()
