import ctypes
import os
import atexit
from .models import vendor_root

_loaded = []


def unregister_fonts():
    if os.name == 'nt':
        for path in _loaded:
            ctypes.windll.gdi32.RemoveFontResourceExW(path, 0, 0)
        _loaded.clear()


atexit.register(unregister_fonts)


def register_fonts():
    # Session-only font resources also make Chinese fonts visible to LibreOffice.
    if os.name != 'nt':
        return
    for path in (vendor_root()/'fonts').glob('*.otf'):
        if str(path) not in _loaded:
            if ctypes.windll.gdi32.AddFontResourceExW(str(path), 0, 0):
                _loaded.append(str(path))


def register_qt_fonts():
    from PySide6.QtGui import QFontDatabase
    register_fonts()
    for path in (vendor_root()/'fonts').glob('*.otf'):
        QFontDatabase.addApplicationFont(str(path))
