from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import subprocess
import sys
from typing import Any, Literal

from .indexer import get_lmstudio_home
from .models import ServiceStatusInfo

PlatformType = Literal["macos", "linux", "windows"]

MACOS_LABEL = "ai.lmstudio.webui"
LINUX_UNIT_NAME = "lmstudio-webui.service"
WINDOWS_RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE_NAME = "LMStudioWebUI"
WINDOWS_REG_DISPLAY = rf"HKCU\{WINDOWS_RUN_SUBKEY}\{WINDOWS_VALUE_NAME}"
WINDOWS_STATE_FILENAME = "lms-webui-service.json"
PROJECT_DIR = Path(__file__).resolve().parents[2]


def detect_platform(override: str | None = None) -> PlatformType:
    if override:
        low = override.strip().lower()
        if low in ("macos", "darwin", "mac"):
            return "macos"
        if low in ("linux", "systemd"):
            return "linux"
        if low in ("windows", "win32", "win"):
            return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32" or os.name == "nt":
        return "windows"
    return "linux"


def _format_cmd(prog_args: list[str], platform: PlatformType) -> str:
    if platform == "windows":
        return subprocess.list2cmdline([str(x) for x in prog_args])
    return shlex.join([str(x) for x in prog_args])


def build_service_path_env(platform: PlatformType | None = None) -> str:
    plat = platform or detect_platform()
    sep = ";" if plat == "windows" else ":"
    raw_path = os.environ.get("PATH", "")
    parts = [p for p in raw_path.split(sep) if p]

    if plat == "windows":
        extra_dirs = [
            str(Path.home() / ".local" / "bin"),
            str(Path.home() / ".lmstudio" / "bin"),
        ]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            extra_dirs.append(str(Path(local_app_data) / "lm-studio" / "bin"))
    else:
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
    return sep.join(parts)


def resolve_program_arguments(
    port: int = 8420,
    host: str = "0.0.0.0",
    lmstudio_url: str = "http://localhost:1234",
    lmstudio_home: str | Path | None = None,
    platform_override: str | None = None,
) -> tuple[Path, list[str]]:
    """Resolve (working_directory, program_args) whether run from checkout or installed tool."""
    plat = detect_platform(platform_override)
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

    if plat == "windows":
        if (PROJECT_DIR / "pyproject.toml").is_file():
            for exe_name in ("pythonw.exe", "python.exe"):
                cand = PROJECT_DIR / ".venv" / "Scripts" / exe_name
                if cand.is_file():
                    return (
                        PROJECT_DIR,
                        [str(cand), "-m", "lmstudio_webui.cli", *serve_args],
                    )
            return (
                PROJECT_DIR,
                [
                    str(PROJECT_DIR / ".venv" / "Scripts" / "pythonw.exe"),
                    "-m",
                    "lmstudio_webui.cli",
                    *serve_args,
                ],
            )

        pyw = Path(sys.executable).with_name("pythonw.exe")
        if pyw.is_file():
            return Path.home(), [str(pyw), "-m", "lmstudio_webui.cli", *serve_args]
        return Path.home(), [sys.executable, "-m", "lmstudio_webui.cli", *serve_args]

    if (PROJECT_DIR / "pyproject.toml").is_file():
        venv_py = PROJECT_DIR / ".venv" / "bin" / "python"
        if venv_py.is_file():
            return (
                PROJECT_DIR,
                [str(venv_py), "-m", "lmstudio_webui.cli", *serve_args],
            )
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


def get_unit_path(
    platform: PlatformType,
    custom_dir: Path | None = None,
    lmstudio_home: str | Path | None = None,
) -> Path:
    if platform == "macos":
        base = custom_dir or (Path.home() / "Library" / "LaunchAgents")
        return base / f"{MACOS_LABEL}.plist"
    if platform == "windows":
        base = custom_dir or (get_lmstudio_home(lmstudio_home) / ".internal")
        return base / WINDOWS_STATE_FILENAME
    base = custom_dir or (Path.home() / ".config" / "systemd" / "user")
    return base / LINUX_UNIT_NAME


# --- Windows HKCU\Software\Microsoft\Windows\CurrentVersion\Run + Detached pythonw.exe ---


def _winreg_set_run_value(value_name: str, command_str: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_SUBKEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, command_str)
    except Exception:
        subprocess.run(
            [
                "reg",
                "add",
                rf"HKCU\{WINDOWS_RUN_SUBKEY}",
                "/v",
                value_name,
                "/t",
                "REG_SZ",
                "/d",
                command_str,
                "/f",
            ],
            capture_output=True,
            check=True,
        )


def _winreg_get_run_value(value_name: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_SUBKEY,
            0,
            winreg.KEY_READ,
        ) as key:
            val, _ = winreg.QueryValueEx(key, value_name)
            return str(val) if val else None
    except Exception:
        return None


def _winreg_delete_run_value(value_name: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_SUBKEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        pass
    except Exception:
        subprocess.run(
            ["reg", "delete", rf"HKCU\{WINDOWS_RUN_SUBKEY}", "/v", value_name, "/f"],
            capture_output=True,
            check=False,
        )


def _is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            return res.returncode == 0 and str(pid) in res.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_windows_process(pid: int | None) -> None:
    if pid and pid > 0:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass


def _start_windows_detached_process(
    prog_args: list[str],
    work_dir: Path,
    env_vars: dict[str, str],
    log_dir: Path,
) -> int | None:
    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / "lms-webui.out.log"
    err_log = log_dir / "lms-webui.err.log"

    full_env = os.environ.copy()
    full_env.update(env_vars)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )

    with open(out_log, "ab") as out_f, open(err_log, "ab") as err_f:
        proc = subprocess.Popen(
            prog_args,
            cwd=str(work_dir),
            env=full_env,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            creationflags=creationflags,
            start_new_session=(sys.platform != "win32"),
        )
        return int(proc.pid)


def generate_windows_service_payload(
    port: int = 8420,
    host: str = "0.0.0.0",
    lmstudio_url: str = "http://localhost:1234",
    lmstudio_home: str | Path | None = None,
    api_token: str | None = None,
) -> tuple[Path, list[str], dict[str, Any]]:
    work_dir, prog_args = resolve_program_arguments(
        port=port,
        host=host,
        lmstudio_url=lmstudio_url,
        lmstudio_home=lmstudio_home,
        platform_override="windows",
    )
    resolved_home = get_lmstudio_home(lmstudio_home)
    exec_start = _format_cmd(prog_args, "windows")

    env_vars: dict[str, str] = {
        "PATH": build_service_path_env("windows"),
        "LMSTUDIO_URL": lmstudio_url,
        "LMSTUDIO_HOME": str(resolved_home),
        "LMS_WEBUI_PORT": str(port),
        "LMS_WEBUI_HOST": host,
    }
    if (PROJECT_DIR / "packages").is_dir():
        env_vars["PYTHONPATH"] = str(PROJECT_DIR / "packages")
    token = api_token or os.environ.get("LM_API_TOKEN")
    if token:
        env_vars["LM_API_TOKEN"] = token

    payload: dict[str, Any] = {
        "platform": "windows",
        "service_manager": "hkcu-run",
        "service_name": WINDOWS_VALUE_NAME,
        "registry_key": WINDOWS_REG_DISPLAY,
        "working_directory": str(work_dir),
        "program_arguments": prog_args,
        "exec_start": exec_start,
        "environment": env_vars,
        "port": port,
        "host": host,
        "lmstudio_url": lmstudio_url,
        "pid": None,
    }
    return work_dir, prog_args, payload


# --- macOS & Linux Unit Generators ---


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
        platform_override="macos",
    )
    resolved_home = get_lmstudio_home(lmstudio_home)
    logs_folder = log_dir or (Path.home() / "Library" / "Logs" / "lmstudio-webui")

    env_vars: dict[str, str] = {
        "PATH": build_service_path_env("macos"),
        "LMSTUDIO_URL": lmstudio_url,
        "LMSTUDIO_HOME": str(resolved_home),
        "LMS_WEBUI_PORT": str(port),
        "LMS_WEBUI_HOST": host,
    }
    if (PROJECT_DIR / "packages").is_dir():
        env_vars["PYTHONPATH"] = str(PROJECT_DIR / "packages")
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
        platform_override="linux",
    )
    resolved_home = get_lmstudio_home(lmstudio_home)
    exec_start = shlex.join(prog_args)
    user_path = build_service_path_env("linux")

    env_lines = [
        f'Environment="PATH={user_path}"',
        f'Environment="LMSTUDIO_URL={lmstudio_url}"',
        f'Environment="LMSTUDIO_HOME={resolved_home}"',
        f'Environment="LMS_WEBUI_PORT={port}"',
        f'Environment="LMS_WEBUI_HOST={host}"',
    ]
    if (PROJECT_DIR / "packages").is_dir():
        env_lines.append(f'Environment="PYTHONPATH={PROJECT_DIR / "packages"}"')
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


# --- Unified Service Status, Install, Uninstall, & Control ---


def get_service_status(
    platform_override: str | None = None,
    unit_dir: Path | None = None,
    default_port: int = 8420,
    default_host: str = "0.0.0.0",
    default_lmstudio_url: str = "http://localhost:1234",
) -> ServiceStatusInfo:
    plat = detect_platform(platform_override)
    unit_path = get_unit_path(plat, custom_dir=unit_dir)
    work_dir, prog_args = resolve_program_arguments(
        port=default_port,
        host=default_host,
        lmstudio_url=default_lmstudio_url,
        platform_override=plat,
    )
    exec_start = _format_cmd(prog_args, plat)
    port = default_port
    host = default_host
    lmstudio_url = default_lmstudio_url

    if plat == "windows":
        reg_val = _winreg_get_run_value(WINDOWS_VALUE_NAME) if unit_dir is None else None
        installed = unit_path.is_file() or bool(reg_val)
        pid: int | None = None
        if unit_path.is_file():
            try:
                state = json.loads(unit_path.read_text(encoding="utf-8"))
                exec_start = str(state.get("exec_start") or reg_val or exec_start)
                work_dir = Path(state.get("working_directory") or work_dir)
                port = int(state.get("port") or port)
                host = str(state.get("host") or host)
                lmstudio_url = str(state.get("lmstudio_url") or lmstudio_url)
                if state.get("pid"):
                    pid = int(state["pid"])
            except Exception:
                pass
        elif reg_val:
            exec_start = reg_val

        running = _is_pid_running(pid) if installed else False
        return ServiceStatusInfo(
            platform="windows",
            service_manager="hkcu-run",
            service_name=WINDOWS_VALUE_NAME,
            unit_path=WINDOWS_REG_DISPLAY if unit_dir is None else str(unit_path),
            installed=installed,
            running=running,
            exec_start=exec_start,
            working_directory=str(work_dir),
            port=port,
            host=host,
            lmstudio_url=lmstudio_url,
        )

    installed = unit_path.is_file()
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


def _kill_orphaned_service_processes() -> None:
    """Ensure no orphaned lms-webui / uv wrapper processes remain bound to the port."""
    if sys.platform == "win32":
        return
    for pattern in (r"[l]ms-webui serve", r"[l]mstudio_webui\.cli serve"):
        try:
            subprocess.run(["pkill", "-TERM", "-f", pattern], capture_output=True, check=False)
        except Exception:
            pass


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
    unit_path = get_unit_path(plat, custom_dir=unit_dir, lmstudio_home=lmstudio_home)

    if plat == "windows":
        work_dir, prog_args, payload = generate_windows_service_payload(
            port=port,
            host=host,
            lmstudio_url=lmstudio_url,
            lmstudio_home=lmstudio_home,
            api_token=api_token,
        )
        exec_start = payload["exec_start"]
        reg_cmd = [
            "reg",
            "add",
            rf"HKCU\{WINDOWS_RUN_SUBKEY}",
            "/v",
            WINDOWS_VALUE_NAME,
            "/t",
            "REG_SZ",
            "/d",
            exec_start,
            "/f",
        ]
        if not dry_run:
            # Stop any previously tracked PID before starting a fresh background instance
            if unit_path.is_file():
                try:
                    prev = json.loads(unit_path.read_text(encoding="utf-8"))
                    _stop_windows_process(prev.get("pid"))
                except Exception:
                    pass

            if unit_dir is None and sys.platform == "win32":
                _winreg_set_run_value(WINDOWS_VALUE_NAME, exec_start)
                log_dir = get_lmstudio_home(lmstudio_home) / "server-logs"
                pid = _start_windows_detached_process(
                    prog_args=prog_args,
                    work_dir=work_dir,
                    env_vars=payload["environment"],
                    log_dir=log_dir,
                )
                payload["pid"] = pid

            unit_path.parent.mkdir(parents=True, exist_ok=True)
            unit_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return {
            "platform": "windows",
            "service_manager": "hkcu-run",
            "service_name": WINDOWS_VALUE_NAME,
            "unit_path": WINDOWS_REG_DISPLAY if unit_dir is None else str(unit_path),
            "state_file": str(unit_path),
            "working_directory": str(work_dir),
            "exec_start": exec_start,
            "content": json.dumps(payload, indent=2),
            "commands": [subprocess.list2cmdline(reg_cmd), exec_start],
            "dry_run": dry_run,
        }

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
                _kill_orphaned_service_processes()
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

    if plat == "windows":
        reg_del_cmd = [
            "reg",
            "delete",
            rf"HKCU\{WINDOWS_RUN_SUBKEY}",
            "/v",
            WINDOWS_VALUE_NAME,
            "/f",
        ]
        if not dry_run:
            if unit_path.is_file():
                try:
                    state = json.loads(unit_path.read_text(encoding="utf-8"))
                    _stop_windows_process(state.get("pid"))
                except Exception:
                    pass
                unit_path.unlink()
            if unit_dir is None and sys.platform == "win32":
                _winreg_delete_run_value(WINDOWS_VALUE_NAME)
        return {
            "platform": "windows",
            "service_name": WINDOWS_VALUE_NAME,
            "unit_path": WINDOWS_REG_DISPLAY if unit_dir is None else str(unit_path),
            "removed": not dry_run,
            "commands": [subprocess.list2cmdline(reg_del_cmd)],
        }

    if plat == "macos":
        uid = os.getuid() if hasattr(os, "getuid") else 501
        commands = [
            ["launchctl", "bootout", f"gui/{uid}/{MACOS_LABEL}"],
        ]
        if not dry_run:
            if unit_dir is None and sys.platform == "darwin":
                subprocess.run(commands[0], capture_output=True, check=False)
                _kill_orphaned_service_processes()
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
    unit_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    plat = detect_platform(platform_override)

    if plat == "windows":
        unit_path = get_unit_path("windows", custom_dir=unit_dir)
        state: dict[str, Any] = {}
        if unit_path.is_file():
            try:
                state = json.loads(unit_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}

        work_dir = Path(state.get("working_directory") or PROJECT_DIR)
        prog_args = state.get("program_arguments")
        if not isinstance(prog_args, list) or not prog_args:
            work_dir, prog_args = resolve_program_arguments(platform_override="windows")
        env_vars = state.get("environment") if isinstance(state.get("environment"), dict) else {}
        cmd_str = _format_cmd(prog_args, "windows")

        if not dry_run:
            if action in ("stop", "restart"):
                _stop_windows_process(state.get("pid"))
                state["pid"] = None
            if action in ("start", "restart") and (sys.platform == "win32" or unit_dir is not None):
                if sys.platform == "win32":
                    log_dir = get_lmstudio_home() / "server-logs"
                    new_pid = _start_windows_detached_process(
                        prog_args=[str(x) for x in prog_args],
                        work_dir=work_dir,
                        env_vars=env_vars,
                        log_dir=log_dir,
                    )
                    state["pid"] = new_pid
            if unit_path.is_file() or state:
                unit_path.parent.mkdir(parents=True, exist_ok=True)
                unit_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        return {
            "platform": "windows",
            "action": action,
            "command": f"taskkill /PID {state.get('pid') or '<pid>'} /T /F" if action == "stop" else cmd_str,
        }

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
            if action in ("stop", "restart"):
                _kill_orphaned_service_processes()
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
