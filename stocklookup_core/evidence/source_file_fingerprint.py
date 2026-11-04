"""Metadata identity of one regular file. This is not a content hash.

Root modules cannot import ``tools.vault_snapshot`` (architecture policy: root may not
depend on tools). This helper is the feedback receipt anchor. It reads NTFS ChangeTime
with ``GetFileInformationByHandleEx`` (FileBasicInfo). Python's Windows ``st_ctime`` is
the creation time and is not used. POSIX uses ``st_ctime_ns``.

A symlink, junction, or other reparse point returns no fingerprint. The caller then
hashes the bytes instead of trusting metadata.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

_INVALID_ATTRIBUTES = 0xFFFFFFFF
_REPARSE_POINT = 0x400


def path_has_reparse_point(path: Path) -> bool:
    """True when ``path`` itself is a symlink, junction, or reparse point."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
    except OSError:
        return True
    if os.name != "nt":
        return False
    import ctypes
    attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attributes == _INVALID_ATTRIBUTES:
        return False
    return bool(attributes & _REPARSE_POINT)


def source_file_fingerprint(path: Path) -> dict | None:
    """Volume, file id, size, mtime_ns and ChangeTime. ``None`` means do not trust metadata."""
    path = Path(path)
    try:
        if path_has_reparse_point(path):
            return None
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            return None
        change = info.st_ctime_ns if os.name != "nt" else _nt_change_time(path)
        if change is None:
            return None
    except OSError:
        return None
    return {
        "volume": info.st_dev,
        "file_id": info.st_ino,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "change": int(change),
    }


def _nt_change_time(path: Path) -> int | None:
    """NTFS ChangeTime as the FileBasicInfo integer. Does not follow a reparse point."""
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int64) for name in ("creation", "access", "write", "change")] + [
            ("attrs", wintypes.DWORD)
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # FILE_FLAG_OPEN_REPARSE_POINT: metadata of this path, not of a link target.
    handle = kernel.CreateFileW(str(path), 0x80000000, 0x00000001, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        return None
    try:
        basic = Basic()
        if not kernel.GetFileInformationByHandleEx(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic)):
            return None
        return int(basic.change)
    finally:
        kernel.CloseHandle(handle)
