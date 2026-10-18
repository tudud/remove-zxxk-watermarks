import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from .models import vendor_root
from .native import run_native

SUPPORTED = {'.docx', '.doc', '.pdf', '.pptx', '.ppt'}
ARCHIVES = {'.zip', '.rar', '.7z'}
MAX_BYTES = 3 * 1024**3


def unpack_zip(path: Path, target: Path, budget: list[int]):
    with zipfile.ZipFile(path) as z:
        for member in z.infolist():
            name = member.filename
            if not member.flag_bits & 0x800:
                try:
                    name = name.encode('cp437').decode('gb18030')
                except (UnicodeError, LookupError):
                    pass
            parts = PurePosixPath(name.replace('\\', '/')).parts
            if not parts or '..' in parts or ':' in name or name.startswith(('/', '\\')):
                raise ValueError(f'压缩包路径不合法：{name}')
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('不支持压缩包中的符号链接')
            dest = target.joinpath(*parts)
            if member.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            budget[0] += member.file_size
            if budget[0] > MAX_BYTES:
                raise ValueError('解压后超过 3 GB 限制，请分批处理')
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as inp, dest.open('wb') as out:
                shutil.copyfileobj(inp, out)


def discover(inputs: list[Path], work: Path, check_cancel=lambda: None, exclude=None):
    queue = [(p, 0, p.stem) for p in inputs]
    result = []
    budget = [0]
    seen = set()
    while queue:
        check_cancel()
        path, depth, origin = queue.pop(0)
        if exclude and path.resolve().is_relative_to(exclude.resolve()):
            continue
        if path.is_dir():
            queue.extend((p, depth, origin) for p in sorted(path.iterdir()))
            continue
        if path.name.startswith('~$'):
            continue
        if path.suffix.lower() in ARCHIVES:
            if depth >= 8:
                raise ValueError('压缩包嵌套超过 8 层')
            target = work / ('a' + str(len(seen)))
            target.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            if path.suffix.lower() == '.zip':
                unpack_zip(path, target, budget)
            else:
                seven = vendor_root() / '7zip' / '7z.exe'
                if not seven.exists():
                    raise RuntimeError('缺少便携解压组件 7-Zip')
                run=run_native([str(seven), 'x', str(path), '-o'+str(target), '-y', '-bd'], timeout=180)
                if run.returncode:
                    raise RuntimeError('压缩包解压失败：'+run.stderr.decode('utf-8',errors='replace')[-400:])
                for p in target.rglob('*'):
                    if p.is_symlink() or not p.resolve().is_relative_to(target.resolve()):
                        raise ValueError('压缩包包含外部链接')
                    if p.is_file():
                        budget[0] += p.stat().st_size
                if budget[0] > MAX_BYTES:
                    raise ValueError('解压后超过 3 GB 限制')
            queue.extend((p, depth+1, origin) for p in sorted(target.rglob('*')) if p.is_file())
        elif path.suffix.lower() in SUPPORTED:
            result.append((path, origin))
    return result
