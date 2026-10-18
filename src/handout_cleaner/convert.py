import shutil
import subprocess
import tempfile
from pathlib import Path
from .models import vendor_root
from .native import run_native


def office_binary() -> Path:
    path = vendor_root() / 'LibreOffice' / 'program' / 'soffice.exe'
    if not path.exists():
        raise RuntimeError('便携包缺少 LibreOffice/program/soffice.exe，请完整解压整个程序文件夹')
    return path


def convert_office(source: Path, output: Path, fmt: str) -> Path:
    from .fonts import register_fonts
    register_fonts()
    source = source.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hc-office-') as temp:
        profile = (Path(temp) / 'profile').as_uri()
        target = Path(temp) / 'out'
        target.mkdir()
        command = [str(office_binary()), '-env:UserInstallation='+profile, '--headless', '--nologo', '--nodefault', '--nofirststartwizard', '--convert-to', fmt, '--outdir', str(target), str(source)]
        run = run_native(command, timeout=150)
        ext = fmt.split(':')[0]
        files = list(target.glob('*.'+ext))
        if run.returncode or not files:
            raise RuntimeError('文档转换失败：'+(run.stdout+run.stderr).decode('utf-8', errors='replace')[-1200:])
        destination = output / (source.stem+'.'+ext)
        shutil.copy2(files[0], destination)
        return destination
