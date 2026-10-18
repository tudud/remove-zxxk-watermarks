"""Launch native helpers without inheriting PyInstaller's DLL overrides."""
import ctypes
import os
import subprocess
import sys
import threading
from pathlib import Path

_lock=threading.Lock()


def run_native(command, timeout=150):
    env=os.environ.copy()
    frozen_root=getattr(sys,'_MEIPASS',None)
    if frozen_root:
        env['PATH']=os.pathsep.join(part for part in env.get('PATH','').split(os.pathsep) if not part.lower().startswith(str(frozen_root).lower()))
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):
        env.pop(key,None)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with _lock:
        if os.name=='nt' and frozen_root:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            process=subprocess.Popen(list(map(str,command)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,env=env,creationflags=flags)
        finally:
            if os.name=='nt' and frozen_root:
                ctypes.windll.kernel32.SetDllDirectoryW(str(frozen_root))
    try:
        stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            taskkill=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
            subprocess.run([str(taskkill),'/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=flags,timeout=15)
        else:
            process.kill()
        process.communicate()
        raise RuntimeError(f'本地转换组件超时（{timeout}秒），已停止本次转换')
    return subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
