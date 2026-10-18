from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, copy_metadata

ROOT=Path(SPECPATH)
ocr_data,ocr_bins,ocr_hidden=collect_all('rapidocr_onnxruntime')
datas=ocr_data+copy_metadata('rapidocr-onnxruntime')
datas+=collect_data_files('onnxruntime')
datas+=collect_data_files('pdf2docx')
bins=ocr_bins+collect_dynamic_libs('onnxruntime')
a=Analysis([str(ROOT/'run.py')],pathex=[str(ROOT/'src')],
    binaries=bins,datas=datas,
    hiddenimports=ocr_hidden+['onnxruntime.capi.onnxruntime_pybind11_state','PySide6.QtCore','PySide6.QtGui','PySide6.QtWidgets','cv2','pdf2docx'],
    excludes=['matplotlib','pandas','scipy','torch','tensorflow','IPython','jupyter','tkinter','pytest','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick','PySide6.QtPdf'],
    noarchive=False)
# Qt 6.12 calls the unversioned Windows 10 ICU API. The development Python
# runtime also ships a version-suffixed ICU DLL with the same filename.
a.binaries=[entry for entry in a.binaries if entry[0].lower() not in ('icuuc.dll','icudt78.dll')]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='HandoutCleaner',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,icon=str(ROOT/'assets'/'app.ico'))
if os.environ.get('HANDOUT_EXE_ONLY') != '1':
    coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='HandoutCleaner')
