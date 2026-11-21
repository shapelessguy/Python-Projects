"""An application's icon for the page, drawn the way Windows shows it.

Qt objects: only on the GUI thread (UI.app_icon_png gets there).
"""
import ctypes
import json
import os
import subprocess
from ctypes import wintypes
from functools import lru_cache
from comtypes import GUID, IUnknown, COMMETHOD, HRESULT
from PyQt5.QtCore import QBuffer, QIODevice
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QStyle
from PyQt5.QtWinExtras import QtWin


def icon_from_exe(exe_path):
    """The icon inside an .exe, or None."""
    if not exe_path or not os.path.exists(exe_path):
        return None
    large, small = wintypes.HICON(), wintypes.HICON()
    num_icons = ctypes.windll.shell32.ExtractIconExW(exe_path, 0, ctypes.byref(large), ctypes.byref(small), 1)
    try:
        hicon = large.value or small.value
        if num_icons == 0 or not hicon:
            return None
        return QIcon(QtWin.fromHICON(hicon))
    finally:
        for h in (large.value, small.value):
            if h:
                ctypes.windll.user32.DestroyIcon(wintypes.HICON(h))


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _IShellItemImageFactory(IUnknown):
    _iid_ = GUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
    _methods_ = [COMMETHOD([], HRESULT, "GetImage",
                           (["in"], _SIZE, "size"), (["in"], ctypes.c_int, "flags"),
                           (["out"], ctypes.POINTER(wintypes.HBITMAP), "phbm"))]


_SIIGBF_ICONONLY = 0x4


@lru_cache(maxsize=1)
def _start_menu_ids():
    """Start menu entry name -> AppID, as Get-StartApps lists them (once per run)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return {x["Name"]: x["AppID"] for x in json.loads(out)}
    except Exception as e:
        print(f"Start menu apps not listed: {e.__class__.__name__} - {e}")
        return {}


def icon_from_start_menu(name):
    """The icon of a Start menu entry (what `app:<name>` paths launch), or None.
    It follows the app's updates, unlike a versioned exe path."""
    app_id = _start_menu_ids().get(name)
    if not app_id:
        return None
    factory = ctypes.POINTER(_IShellItemImageFactory)()
    hr = ctypes.windll.shell32.SHCreateItemFromParsingName(
        "shell:AppsFolder\\" + app_id, None, ctypes.byref(_IShellItemImageFactory._iid_), ctypes.byref(factory))
    if hr != 0 or not factory:
        return None
    try:
        hbitmap = factory.GetImage(_SIZE(32, 32), _SIIGBF_ICONONLY)
    except Exception:
        return None
    try:
        return QIcon(QtWin.fromHBITMAP(hbitmap, QtWin.HBitmapPremultipliedAlpha))
    finally:
        ctypes.windll.gdi32.DeleteObject(wintypes.HGDIOBJ(hbitmap))


def application_icon(application, mapped_exe):
    """The exe last seen running (exe_map.json), else the configured path,
    else the Start menu entry, else a generic icon."""
    path = application.path
    if os.path.basename(path).lower() == "chrome_proxy.exe":  # no icon of its own
        path = os.path.join(os.path.dirname(path), "chrome.exe")
    icon = icon_from_exe(mapped_exe) or icon_from_exe(path)
    if icon is None and path.startswith("app:"):
        icon = icon_from_start_menu(path[len("app:"):])
    return icon or QApplication.style().standardIcon(QStyle.SP_FileIcon)


def icon_png(application, mapped_exe, size=32) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    application_icon(application, mapped_exe).pixmap(size, size).save(buffer, "PNG")
    return bytes(buffer.data())
