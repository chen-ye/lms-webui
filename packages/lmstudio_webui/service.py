from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
from typing import Any, Literal

from .indexer import get_lmstudio_home
from .models import ServiceStatusInfo

PlatformType = Literal["macos", "linux"]

MACOS_LABEL = "ai.lmstudio.webui"
LINUX_UNIT_NAME = "lmstudio-webui.service"
PROJECT_DIR = Path(__file__).resolve().parents[2]


def detect_platform(override: str | None = None) -> PlatformType:
    if override and override.lower() in ("macos", "darwin", "mac"):
        return "macos"
    if override and override.lower() in ("linux", "systemd"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def build_service_path_env() -> str:
    raw_path = os.environ.get("PATH", "")
    parts = [p for p in raw_path.split(":") if p]
    extra_dirs = [
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".lmstudio" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/home/linuxbrew/.linuxbrew/bin",
        "/usr/bin",
        "/bin",
    ]
    for d in reversed(extra_dirs):
        if d not in parts:
            parts.insert(0, d)
    return ":".join(parts)


def resolve_program_arguments(
    port: int = 8420,
    host: str = "0.0.0.0",
    lmstudio_url: str = "http://localhost:1234",
    lmstudio_home: str | Path | None = None,
) -> tuple[Path, list[str]]:
    """Resolve (working_directory, program_args) whether run from checkout or installed tool."""
    serve_args = [
        "serve",
        "--host",
        host,
        "--port",
        str(port),
        "--lmstudio-url",
        lmstudio_url,
    ]
    if lmstudio_home:
        serve_args.extend(["--lmstudio-home", str(Path(lmstudio_home).expanduser().resolve())])

    if (PROJECT_DIR / "pyproject.toml").is_file():
        uv_bin = shutil.which("uv")
        if not uv_bin:
            for cand in (
                Path.home() / ".local" / "bin" / "uv",
                Path("/opt/homebrew/bin/uv"),
                Path("/usr/local/bin/uv"),
            ):
                if cand.is_file():
                    uv_bin = str(cand)
                    break
        uv_cmd = uv_bin or "uv"
        return (
            PROJECT_DIR,
            [uv_cmd, "run", "--project", str(PROJECT_DIR), "lms-webui", *serve_args],
        )

    cli_bin = Path(sys.executable).parent / "lms-webui"
    if cli_bin.is_file():
        return Path.home(), [str(cli_bin), *serve_args]

    found = shutil.which("lms-webui")
    if found:
        return Path.home(), [found, *serve_args]

    return Path.home(), [sys.executable, "-m", "lmstudio_webui.cli", *serve_args]


def get_unit_path(platform: PlatformType, custom_dir: Path | None = None) -> Path:
    if platform == "macos":
        base = custom_dir or (Path.home() / "Library" / "LaunchAgents")
        return base / f"{MACOS_LABEL}.plist"
    base = custom_dir or (Path.home() / ".config" / "systemd" / "user")
    return base / LINUX_UNIT_NAME


def generate_macos_plist_bytes(
    port: int = 8420,
    host: str = "0.0.0.0",
    lmstudio_url: str = "http://localhost:1234",
    lmstudio_home: str | Path | None = None,
    api_token: str | None = None,
    log_dir: Path | None = None,
) -> tuple[Path, list[str], bytes]:
    work_dir, prog_args = resolve_program_arguments(
        port=port,
        host=host,
        lmstudio_url=lmstudio_url,
        lmstudio_home=lmstudio_home,
    )
    resolved_home = get_lmstudio_home(lmstudio_home)
    logs_folder = log_dir or (Path.home() / "Library" / "Logs" / "lmstudio-webui")

    env_vars: dict[str, str] = {
        "PATH": build_service_path_env(),
        "LMSTUDIO_URL": lmstudio_url,
        "LMSTUDIO_HOME": str(resolved_home),
        "LMS_WEBUI_PORT": str(port),
        "LMS_WEBUI_HOST": host,
    }
    token = api_token or os.environ.get("LM_API_TOKEN")
    if token:
        env_vars["LM_API_TOKEN"] = token

    plist_dict: dict[str, Any] = {
        "Label": MACOS_LABEL,
        "ProgramArguments": prog_args,
        "WorkingDirectory": str(work_dir),
        "EnvironmentVariables": env_vars,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(logs_folder / "lms-webui.out.log"),
        "StandardErrorPath": str(logs_folder / "lms-webui.err.log"),
    }
    return work_dir, prog_args, plistlib.dumps(plist_dict, sort_keys=False)


def generate_linux_systemd_unit(
    port: int = 8420,
    host: str = "0.0.0.0",
    lmstudio_url: str = "http://localhost:1234",
    lmstudio_home: str | Path | None = None,
    api_token: str | None = None,
) -> tuple[Path, list[str], str]:
    work_dir, prog_args = resolve_program_arguments(
        port=port,
        host=host,
        lmstudio_url=lmstudio_url,
        lmstudio_home=lmstudio_home,
    )
    resolved_home = get_lmstudio_home(lmstudio_home)
    exec_start = shlex.join(prog_args)
    user_path = build_service_path_env()

    env_lines = [
        f'Environment="PATH={user_path}"',
        f'Environment="LMSTUDIO_URL={lmstudio_url}"',
        f'Environment="LMSTUDIO_HOME={resolved_home}"',
        f'Environment="LMS_WEBUI_PORT={port}"',
        f'Environment="LMS_WEBUI_HOST={host}"',
    ]
    token = api_token or os.environ.get("LM_API_TOKEN")
    if token:
        env_lines.append(f'Environment="LM_API_TOKEN={token}"')

    env_block = "\n".join(env_lines)
    unit_text = f"""[Unit]
Description=LM Studio Model Management WebUI & REST Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory={work_dir}
ExecStart={exec_start}
Restart=always
RestartSec=3
{env_block}

[Install]
WantedBy=default.target
"""
    return work_dir, prog_args, unit_text


def get_service_status(
    platform_override: str | None = None,
    unit_dir: Path | None = None,
    default_port: int = 8420,
    default_host: str = "0.0.0.0",
    default_lmstudio_url: str = "http://localhost:1234",
) -> ServiceStatusInfo:
    plat = detect_platform(platform_override)
    unit_path = get_unit_path(plat, custom_dir=unit_dir)
    installed = unit_path.is_file()
    work_dir, prog_args = resolve_program_arguments(
        port=default_port,
        host=default_host,
        lmstudio_url=default_lmstudio_url,
    )
    exec_start = shlex.join(prog_args)
    port = default_port
    host = default_host
    lmstudio_url = default_lmstudio_url

    if installed:
        try:
            if plat == "macos":
                pl = plistlib.loads(unit_path.read_bytes())
                p_args = pl.get("ProgramArguments") or prog_args
                exec_start = shlex.join([str(x) for x in p_args])
                work_dir = Path(pl.get("WorkingDirectory") or work_dir)
                env_v = pl.get("EnvironmentVariables") or {}
                if env_v.get("LMS_WEBUI_PORT"):
                    port = int(env_v["LMS_WEBUI_PORT"])
                if env_v.get("LMS_WEBUI_HOST"):
                    host = str(env_v["LMS_WEBUI_HOST"])
                if env_v.get("LMSTUDIO_URL"):
                    lmstudio_url = str(env_v["LMSTUDIO_URL"])
            else:
                text = unit_path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    if line.startswith("ExecStart="):
                        exec_start = line.split("=", 1)[1].strip()
                    elif line.startswith("WorkingDirectory="):
                        work_dir = Path(line.split("=", 1)[1].strip())
                    elif 'Environment="LMS_WEBUI_PORT=' in line:
                        port = int(line.split("=", 2)[2].rstrip('"'))
                    elif 'Environment="LMS_WEBUI_HOST=' in line:
                        host = line.split("=", 2)[2].rstrip('"')
                    elif 'Environment="LMSTUDIO_URL=' in line:
                        lmstudio_url = line.split("=", 2)[2].rstrip('"')
        except Exception:
            pass

    running = False
    if installed and unit_dir is None:
        try:
            if plat == "macos" and sys.platform == "darwin":
                uid = os.getuid()
                res = subprocess.run(
                    ["launchctl", "print", f"gui/{uid}/{MACOS_LABEL}"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    check=False,
                )
                running = res.returncode == 0 and (
                    "state = running" in res.stdout or "pid =" in res.stdout
                )
            elif plat == "linux" and sys.platform.startswith("linux"):
                res = subprocess.run(
                    ["systemctl", "--user", "is-active", LINUX_UNIT_NAME],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    check=False,
                )
                running = res.returncode == 0 and res.stdout.strip() == "active"
        except Exception:
            running = False

    return ServiceStatusInfo(
        platform=plat,
        service_manager="launchd" if plat == "macos" else "systemd",
        service_name=MACOS_LABEL if plat == "macos" else LINUX_UNIT_NAME,
        unit_path=str(unit_path),
        installed=installed,
        running=running,
        exec_start=exec_start,
        working_directory=str(work_dir),
        port=port,
        host=host,
        lmstudio_url=lmstudio_url,
    )


def install_service(
    port: int = 8420,
    host: str = "0.0.0.0",
    lmstudio_url: str = "http://localhost:1234",
    lmstudio_home: str | Path | None = None,
    api_token: str | None = None,
    platform_override: str | None = None,
    unit_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    plat = detect_platform(platform_override)
    unit_path = get_unit_path(plat, custom_dir=unit_dir)

    if plat == "macos":
        log_dir = (unit_dir / "logs") if unit_dir else (Path.home() / "Library" / "Logs" / "lmstudio-webui")
        work_dir, prog_args, content_bytes = generate_macos_plist_bytes(
            port=port,
            host=host,
            lmstudio_url=lmstudio_url,
            lmstudio_home=lmstudio_home,
            api_token=api_token,
            log_dir=log_dir,
        )
        uid = os.getuid() if hasattr(os, "getuid") else 501
        commands = [
            ["launchctl", "bootout", f"gui/{uid}/{MACOS_LABEL}"],
            ["launchctl", "bootstrap", f"gui/{uid}", str(unit_path)],
            ["launchctl", "kickstart", "-k", f"gui/{uid}/{MACOS_LABEL}"],
        ]
        if not dry_run:
            unit_path.parent.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            unit_path.write_bytes(content_bytes)
            if unit_dir is None and sys.platform == "darwin":
                subprocess.run(commands[0], capture_output=True, check=False)
                subprocess.run(commands[1], capture_output=True, check=True)
                subprocess.run(commands[2], capture_output=True, check=False)
        return {
            "platform": "macos",
            "service_manager": "launchd",
            "service_name": MACOS_LABEL,
            "unit_path": str(unit_path),
            "working_directory": str(work_dir),
            "exec_start": shlex.join(prog_args),
            "content": content_bytes.decode("utf-8"),
            "commands": [shlex.join(c) for c in commands],
            "dry_run": dry_run,
        }

    work_dir, prog_args, unit_text = generate_linux_systemd_unit(
        port=port,
        host=host,
        lmstudio_url=lmstudio_url,
        lmstudio_home=lmstudio_home,
        api_token=api_token,
    )
    commands = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", LINUX_UNIT_NAME],
        ["systemctl", "--user", "restart", LINUX_UNIT_NAME],
    ]
    if not dry_run:
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(unit_text, encoding="utf-8")
        if unit_dir is None and sys.platform.startswith("linux"):
            for cmd in commands:
                subprocess.run(cmd, capture_output=True, check=True)
    return {
        "platform": "linux",
        "service_manager": "systemd",
        "service_name": LINUX_UNIT_NAME,
        "unit_path": str(unit_path),
        "working_directory": str(work_dir),
        "exec_start": shlex.join(prog_args),
        "content": unit_text,
        "commands": [shlex.join(c) for c in commands],
        "dry_run": dry_run,
    }


def uninstall_service(
    platform_override: str | None = None,
    unit_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    plat = detect_platform(platform_override)
    unit_path = get_unit_path(plat, custom_dir=unit_dir)

    if plat == "macos":
        uid = os.getuid() if hasattr(os, "getuid") else 501
        commands = [
            ["launchctl", "bootout", f"gui/{uid}/{MACOS_LABEL}"],
        ]
        if not dry_run:
            if unit_dir is None and sys.platform == "darwin":
                subprocess.run(commands[0], capture_output=True, check=False)
            if unit_path.exists():
                unit_path.unlink()
        return {
            "platform": "macos",
            "service_name": MACOS_LABEL,
            "unit_path": str(unit_path),
            "removed": not dry_run,
            "commands": [shlex.join(c) for c in commands],
        }

    commands = [
        ["systemctl", "--user", "disable", "--now", LINUX_UNIT_NAME],
        ["systemctl", "--user", "daemon-reload"],
    ]
    if not dry_run:
        if unit_dir is None and sys.platform.startswith("linux"):
            subprocess.run(commands[0], capture_output=True, check=False)
        if unit_path.exists():
            unit_path.unlink()
        if unit_dir is None and sys.platform.startswith("linux"):
            subprocess.run(commands[1], capture_output=True, check=False)
    return {
        "platform": "linux",
        "service_name": LINUX_UNIT_NAME,
        "unit_path": str(unit_path),
        "removed": not dry_run,
        "commands": [shlex.join(c) for c in commands],
    }


def control_service(
    action: Literal["start", "stop", "restart"],
    platform_override: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    plat = detect_platform(platform_override)
    if plat == "macos":
        uid = os.getuid() if hasattr(os, "getuid") else 501
        unit_path = get_unit_path("macos")
        if action == "start":
            cmd = ["launchctl", "kickstart", f"gui/{uid}/{MACOS_LABEL}"]
        elif action == "stop":
            cmd = ["launchctl", "kill", "SIGTERM", f"gui/{uid}/{MACOS_LABEL}"]
        else:
            cmd = ["launchctl", "kickstart", "-k", f"gui/{uid}/{MACOS_LABEL}"]

        if not dry_run and sys.platform == "darwin":
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0 and action in ("start", "restart") and unit_path.is_file():
                subprocess.run(
                    ["launchctl", "bootstrap", f"gui/{uid}", str(unit_path)],
                    capture_output=True,
                    check=False,
                )
                subprocess.run(cmd, capture_output=True, check=False)
        return {"platform": "macos", "action": action, "command": shlex.join(cmd)}

    cmd = ["systemctl", "--user", action, LINUX_UNIT_NAME]
    if not dry_run and sys.platform.startswith("linux"):
        subprocess.run(cmd, capture_output=True, check=True)
    return {"platform": "linux", "action": action, "command": shlex.join(cmd)}
