"""Owner Daily presentation host and sequential relaunch supervisor (stdlib only).

Replaces the resident Windows PowerShell host: the one-click route is now
``run_owner_daily.cmd`` -> this host -> ``run_owner_daily.py``. It keeps the
exact log/result/progress paths, Vietnamese presentation, exit codes and the
one-relaunch protocol of the former ``run_owner_daily.ps1`` body, while
holding no .NET runtime resident during host admission or the Daily itself.

Keep this module free of repository imports: anything imported here stays
resident for the whole Daily.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
RELAUNCH_EXIT = 75
CODE_HEAD_ENV = "STOCK_LOOKUP_OWNER_DAILY_CODE_HEAD"
RELAUNCH_PATH_ENV = "STOCK_LOOKUP_OWNER_DAILY_RELAUNCH_PATH"
REQUEST_KEYS = ("STOCK_LOOKUP_OWNER_DAILY_RUN_ID", "STOCK_LOOKUP_OWNER_DAILY_RUN_STARTED_AT",
                "STOCK_LOOKUP_OWNER_DAILY_RUN_STARTED_MONOTONIC", "STOCK_LOOKUP_OWNER_DAILY_PROGRESS_PATH")
LABELS = ("Kiểm tra kho mã & môi trường", "Chạy Daily chuẩn", "Xác minh hoàn tất Daily",
          "Công bố trạng thái Producer", "Công bố Dashboard", "Tạo gói bàn giao AI", "Xác minh từ xa",
          "Trung tâm Hành động Cá nhân", "Mở màn hình dành cho chủ sở hữu")
UNKNOWN = "chưa đủ dữ liệu"


class HostRefusal(Exception):
    """Refused before any log, result or journal exists."""


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _sha256(data: bytes) -> str:
    try:
        from _sha2 import sha256  # built in; avoids keeping OpenSSL resident
    except ImportError:
        from hashlib import sha256
    return sha256(data).hexdigest()


def bind_active_writer(environ: dict, home: str) -> None:
    """Same pre-log refusal as the former PowerShell host; the Owner re-validates fully."""
    binding_path = os.path.join(home, ".stocklookup", "active_workspace.json")
    if not os.path.exists(binding_path):
        return
    with open(binding_path, encoding="utf-8-sig") as handle:
        binding = json.load(handle)
    if binding.get("schema") != "stocklookup_active_workspace/v1":
        raise HostRefusal("Active workspace binding schema invalid")
    profile = str(binding.get("profile_path") or "")
    with open(profile, "rb") as handle:
        raw = handle.read()
    if not os.path.isabs(profile) or _sha256(raw) != binding.get("profile_sha256"):
        raise HostRefusal("Active workspace profile identity invalid")
    roles = json.loads(raw.decode("utf-8-sig"))["roles"]
    if not _same_path(ROOT, roles["producer"]):
        raise HostRefusal("Checkout is not the active production writer")
    configured = environ.get("STOCK_LOOKUP_WORKSPACE_PROFILE")
    if configured and not _same_path(configured, profile):
        raise HostRefusal("Stale workspace profile environment")
    python = str(binding.get("python_path") or "")
    if not os.path.isabs(python) or not os.path.isfile(python):
        raise HostRefusal("Active Python unavailable")
    configured_python = environ.get("STOCK_LOOKUP_PYTHON")
    if configured_python and not _same_path(configured_python, python):
        raise HostRefusal("Stale Python environment")
    if not _same_path(sys.executable, python):
        raise HostRefusal("Launcher interpreter is not the active production Python")
    environ["STOCK_LOOKUP_WORKSPACE_PROFILE"] = profile
    environ["STOCK_LOOKUP_PYTHON"] = python


def resolve_paths(python: str, environ: dict) -> tuple[str, str]:
    workspace = os.path.dirname(ROOT)
    runtime = environ.get("STOCK_LOOKUP_RUNTIME_ROOT") or os.path.join(workspace, "dashboard-runtime")
    logs = os.path.join(workspace, "run-logs")
    if environ.get("STOCK_LOOKUP_WORKSPACE_PROFILE"):
        # Qualify through the same Python path owner BEFORE creating any operational log;
        # the short-lived child exits before this host starts the Owner.
        code = ("import json; from runtime_paths import workspace_profile; "
                "print(json.dumps({k:str(v) for k,v in workspace_profile()['paths'].items()}))")
        completed = subprocess.run([python, "-B", "-c", code], env={**environ, "PYTHONPATH": ROOT},
                                   stdout=subprocess.PIPE, encoding="utf-8")
        if completed.returncode != 0:
            raise HostRefusal("Workspace volume qualification failed")
        roles = json.loads(completed.stdout)
        runtime, logs = roles["runtime"], roles["logs"]
        if not _same_path(ROOT, roles["producer"]):
            raise HostRefusal("Launcher must execute from the configured canonical Producer")
    return runtime, logs


def format_duration(seconds) -> str:
    if seconds is None:
        return UNKNOWN
    n = max(0, round(float(seconds)))
    return f"{n // 3600:02d}:{n % 3600 // 60:02d}:{n % 60:02d}"


def _text(value) -> str:
    return "" if value is None else str(value)


def _percent(value) -> str:
    # .NET '{0:0}' rounds half away from zero; percentages are never negative.
    return "" if value is None else str(int(float(value) + 0.5))


def format_presentation(event: dict, checkpoint: dict | None, phase_started, width: int = 0) -> dict:
    """Pure row/detail render plan shared by the interactive and redirected views."""
    checkpoint = checkpoint or {}
    phase = int(event["phase_index"])
    state = event.get("phase_state")
    if not state:
        state = ("LỖI" if event.get("status") == "FAILED"
                 else "XONG" if event.get("owner_phase") and event.get("status") == "END" else "ĐANG CHẠY")
    total = checkpoint.get("checkpoint_total")
    progress = (f"{_text(checkpoint.get('checkpoint_completed'))}/{total} "
                f"({_percent(checkpoint.get('checkpoint_percent'))}%)") if total else ""
    task = event.get("task_label") or checkpoint.get("checkpoint_label")
    parts = [f"[{phase}/9] {_text(event.get('phase_label'))}", state]
    if progress:
        parts.append("Tiến độ " + progress)
    if task and state != "XONG":
        parts.append("Đang làm: " + task)
    row = " | ".join(parts)
    if width > 0 and len(row) > width:
        # On small consoles the measured work count stays visible before the label.
        row = f"[{phase}/9] {progress} | {state} | {_text(task)}".rstrip(" |")
        if len(row) > width:
            row = row[:max(1, width - 1)] + "…"
    elapsed = event.get("phase_elapsed_seconds")
    if phase_started is not None and event.get("elapsed_seconds") is not None:
        elapsed = max(0.0, float(event["elapsed_seconds"]) - float(phase_started))
    details = []
    if elapsed is not None:
        details.append(("Thời gian: " if state == "XONG" else "Đã chạy: ") + format_duration(elapsed))
    eta = event.get("owner_eta_seconds")
    details.append("ETA: " + ("~" + format_duration(eta) if eta is not None else UNKNOWN))
    for key in ("request_detail", "work_detail"):
        if event.get(key):
            details.append(event[key])
    if event.get("disk_warning"):
        details.append("CẢNH BÁO: dung lượng đĩa thấp")
    return {"Row": row, "Details": details}


def _phase_index(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*[+-]?\d+\s*", value):
        value = int(value)
    return value if isinstance(value, int) and 1 <= value <= 9 else None


def validate_request(request) -> dict[str, str]:
    if (not isinstance(request, dict) or set(request) != {"head", "environment"}
            or not isinstance(request["head"], str) or not re.fullmatch(r"[0-9a-f]{40}", request["head"])
            or not isinstance(request["environment"], dict)
            or not set(request["environment"]) <= set(REQUEST_KEYS)
            or not set(REQUEST_KEYS[:3]) <= set(request["environment"])
            or any(not isinstance(v, str) for v in request["environment"].values())):
        raise ValueError("INVALID_RELAUNCH_REQUEST")
    return {**request["environment"], CODE_HEAD_ENV: request["head"]}


class Console:
    """Cursor-addressed rows on a real console; plain lines otherwise."""

    def __init__(self, interactive: bool):
        self.interactive = interactive
        self.row_top = 0
        self.ready = False
        self._kernel = self._handle = None
        if interactive:
            try:
                import ctypes
                self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                self._handle = self._kernel.GetStdHandle(-11)
            except (ImportError, OSError, AttributeError):
                self.interactive = False

    def width(self) -> int:
        return max(20, os.get_terminal_size(sys.stdout.fileno()).columns - 1)

    def cursor_top(self) -> int:
        import ctypes
        info = (ctypes.c_short * 11)()  # CONSOLE_SCREEN_BUFFER_INFO
        if not self._kernel.GetConsoleScreenBufferInfo(self._handle, info):
            raise OSError(ctypes.get_last_error())
        return info[3]

    def _move(self, top: int) -> None:
        if not self._kernel.SetConsoleCursorPosition(self._handle, (top & 0xFFFF) << 16):
            raise OSError("SetConsoleCursorPosition")

    def line(self, text: str) -> None:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def set_row(self, index: int, text: str) -> None:
        if self.interactive and self.ready:
            try:
                width = self.width()
                sys.stdout.flush()
                self._move(self.row_top + index)
                sys.stdout.write(text[:width].ljust(width))
                sys.stdout.flush()
                self._move(self.row_top + 14)
                return
            except (OSError, ValueError):
                self.interactive = False
        self.line(text)


class OwnerView:
    def __init__(self, console: Console, log, diagnostic: bool):
        self.console, self.log, self.diagnostic = console, log, diagnostic
        self.current_phase = 1
        self.checkpoints: dict[int, dict] = {}
        self.starts: dict[int, object] = {}
        self.requests: dict[int, str] = {}

    def handle(self, text: str) -> None:
        self.log(text)
        if text.startswith("OWNER_DAILY_PRESENTATION="):
            self._presentation(json.loads(text[len("OWNER_DAILY_PRESENTATION="):]))
        elif text.startswith("OWNER_DAILY_PROGRESS="):
            try:
                event = json.loads(text[len("OWNER_DAILY_PROGRESS="):])
            except ValueError:
                return
            self._progress(event)
        elif self.diagnostic:
            self.console.line(text)

    def _presentation(self, presentation: dict) -> None:
        console = self.console
        if console.interactive:
            try:
                console.row_top = console.cursor_top()
            except OSError:
                console.interactive = False
        estimates = presentation.get("phase_estimates") or {}
        for phase in range(1, 10):
            estimate = estimates.get(str(phase))
            eta = UNKNOWN if estimate is None else "~" + format_duration(estimate)
            console.line(f"[{phase}/9] {LABELS[phase - 1]} | CHỜ | ETA: {eta}")
        if console.interactive:
            for _ in range(5):
                console.line("")
        console.ready = True

    def _progress(self, event) -> None:
        if not isinstance(event, dict) or (phase := _phase_index(event.get("phase_index"))) is None:
            return
        self.current_phase = phase
        if event.get("owner_phase") and event.get("status") == "BEGIN":
            self.starts[phase] = event.get("elapsed_seconds")
        if event.get("checkpoint_total"):
            self.checkpoints[phase] = event
        event.setdefault("phase_label", None)
        event["phase_label"] = event["phase_label"] or LABELS[phase - 1]
        event["phase_index"] = phase
        if event.get("request_detail"):
            self.requests[phase] = event["request_detail"]
        elif self.requests.get(phase):
            event["request_detail"] = self.requests[phase]
        console = self.console
        width = 0
        if console.interactive:
            try:
                width = console.width()
            except (OSError, ValueError):
                pass
        rendered = format_presentation(event, self.checkpoints.get(phase), self.starts.get(phase), width)
        if console.interactive and console.ready:
            console.set_row(phase - 1, rendered["Row"])
            for index in range(5):
                details = rendered["Details"]
                console.set_row(9 + index, "      " + details[index] if index < len(details) else "")
        else:
            console.line(" | ".join([rendered["Row"], *rendered["Details"]]))


def run_owner(python: str, arguments: list[str], environ: dict, view: OwnerView,
              relaunch_path: str, popen=subprocess.Popen) -> tuple[int, bool]:
    """Sequential handoff: the successor starts only after the previous Owner has exited.

    The request may carry only run metadata; executable and argv stay fixed.
    """
    environ = {**environ, RELAUNCH_PATH_ENV: relaunch_path}
    exit_code = None
    for attempt in range(2):
        try:
            process = popen([python, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ)
        except OSError:
            return 1, True
        with process:
            for raw in process.stdout:
                try:
                    view.handle(raw.decode("utf-8", "replace").rstrip("\r\n"))
                except Exception:  # presentation must never orphan a running Owner
                    pass
        exit_code = process.wait()
        if exit_code != RELAUNCH_EXIT:
            return exit_code, False
        try:
            if attempt:
                raise ValueError("SECOND_RELAUNCH_REQUEST")
            if os.path.getsize(relaunch_path) > 16384:
                raise ValueError("INVALID_RELAUNCH_REQUEST")
            with open(relaunch_path, encoding="utf-8-sig") as handle:
                environ.update(validate_request(json.load(handle)))
            os.remove(relaunch_path)
        except (OSError, ValueError):
            return 1, True
    return 1, True


def parse_args(argv: list[str]) -> dict:
    options = {"replay": None, "entry": None, "logs": None, "no_pause": False, "diagnostic": False}
    values = {"--replay-completed-session": "replay", "--entry-script": "entry", "--log-directory": "logs"}
    flags = {"--no-pause": "no_pause", "--diagnostic": "diagnostic"}
    items = iter(argv)
    for item in items:
        if item in values:
            options[values[item]] = next(items, None)
            if options[values[item]] is None:
                raise HostRefusal("Missing value for " + item)
        elif item in flags:
            options[flags[item]] = True
        else:
            raise HostRefusal("Unknown launcher argument: " + item)
    return options


def main(argv: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if argv is None else argv)
    environ = dict(os.environ)
    bind_active_writer(environ, environ.get("USERPROFILE") or os.path.expanduser("~"))
    python = environ.get("STOCK_LOOKUP_PYTHON") or sys.executable
    if not os.path.isfile(python):
        raise HostRefusal("Configured Python unavailable")
    environ.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", STOCK_LOOKUP_OWNER_STRUCTURED_CONSOLE="1")
    runtime, logs = resolve_paths(python, environ)
    logs = options["logs"] or logs
    entry = options["entry"] or os.path.join(TOOLS, "run_owner_daily.py")
    os.makedirs(logs, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = os.path.join(logs, f"stock_lookup_daily_{stamp}.log")
    result = os.path.join(logs, f"stock_lookup_daily_{stamp}.result.json")
    progress = os.path.join(logs, f"stock_lookup_daily_{stamp}.progress.jsonl")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    console = Console(sys.stdout.isatty() and not options["diagnostic"])
    with open(log, "w", encoding="utf-8", newline="\r\n", buffering=1) as log_file:
        def log_line(text: str) -> None:
            log_file.write(text + "\n")

        def owner_line(text: str) -> None:
            console.line(text)
            log_line(text)

        owner_line("=" * 60)
        owner_line(" STOCK LOOKUP DAILY")
        owner_line(" Ngày: " + time.strftime("%Y-%m-%d"))
        owner_line("=" * 60)
        arguments = ["-u", entry, "--runtime-root", runtime, "--result-path", result, "--progress-path", progress]
        if options["replay"]:
            arguments += ["--replay-completed-session", options["replay"]]
        view = OwnerView(console, log_line, options["diagnostic"])
        temporary = environ.get("TMP") or environ.get("TEMP") or os.path.dirname(log)
        relaunch_path = os.path.join(temporary, "owner-daily-" + os.urandom(16).hex() + ".json")
        try:
            exit_code, relaunch_failure = run_owner(python, arguments, environ, view, relaunch_path)
            if relaunch_failure:
                failure = {"status": "FAILED", "failed_step": "Repository preflight",
                           "reason": "PRODUCER_CODE_RELAUNCH_FAILED",
                           "hint": "Nothing analytical ran; start the existing Daily launcher again.",
                           "resume_completed_session": False}
                with open(result, "w", encoding="utf-8") as handle:
                    json.dump(failure, handle, ensure_ascii=False, indent=4)
        finally:
            for path in (relaunch_path, os.path.splitext(relaunch_path)[0] + ".tmp"):
                try:
                    os.remove(path)
                except OSError:
                    pass
        if console.interactive and console.ready:
            try:
                console._move(console.row_top + 14)
            except OSError:
                pass
        summary = None
        if os.path.exists(result):
            with open(result, encoding="utf-8-sig") as handle:
                summary = json.load(handle)
        get = lambda *keys: _dig(summary, *keys)
        owner_line("=" * 60)
        if summary and summary.get("status") == "PASS" and exit_code == 0:
            owner_line(" HOÀN TẤT DAILY")
            owner_line(" Phiên: " + _text(summary.get("session")))
            owner_line(" Tổng thời gian: " + format_duration(get("telemetry", "elapsed_seconds")))
            owner_line("-" * 60)
            for label in ("Daily", "Dashboard", "Bàn giao AI", "Xác minh từ xa", "Trung tâm Hành động"):
                owner_line(" " + label + ": XONG")
            owner_line(" Trạng thái: PASS")
            if get("action_center", "view_open", "status") == "READY_VIEW_OPEN_FAILED":
                owner_line(" CẢNH BÁO: chưa mở được màn hình, xem log chi tiết.")
        else:
            current = view.current_phase
            owner_line(" DAILY CHƯA HOÀN TẤT")
            if get("action_center", "status") == "PARTIAL":
                current = 8
            elif get("dashboard", "status") == "FAILED":
                current = 5
            owner_line(f" Bước lỗi: [{current}/9] {LABELS[current - 1]}")
            explanation = ("Không thể xác minh gói bàn giao AI của phiên đã hoàn tất." if current == 6
                           else "Bước xử lý chưa vượt qua kiểm tra bắt buộc. Xem log chi tiết.")
            owner_line(" Lý do: " + explanation)
            reason = (get("reason") or get("action_center", "reason") or get("dashboard", "reason")
                      or ("OWNER_DAILY_" + _text(summary.get("status")) if summary else "NO_RESULT_FILE_WRITTEN"))
            owner_line(" Mã lỗi: " + _text(reason))
            if get("failed_step") == "Host preflight" and get("hint"):
                owner_line(" Host preflight: " + _text(get("hint")))
            owner_line(" Có thể tiếp tục từ phiên đã hoàn tất: " + ("CÓ" if get("resume_completed_session") else "KHÔNG"))
            owner_line(" Log chi tiết: " + log)
            owner_line(" Trạng thái: " + (_text(summary.get("status")) if summary else "INTERRUPTED"))
        owner_line("=" * 60)
        if options["diagnostic"]:
            owner_line(" Log chi tiết: " + log)
    final = exit_code if exit_code else 0
    if not final and (not summary or summary.get("status") != "PASS"):
        final = 1
    if not options["no_pause"]:
        try:
            input("Nhấn Enter để đóng: ")
        except EOFError:
            pass
    return final


def _dig(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HostRefusal as refusal:
        print(refusal, file=sys.stderr, flush=True)
        raise SystemExit(1)
