"""Assemble a complete portable directory without machine-specific runtime paths."""
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import zipfile
import types

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'dist'/'HandoutCleaner'


def verify_code(build_dir=None):
    from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader
    reader=ZlibArchiveReader(str((build_dir or ROOT/'build/HandoutCleaner')/'PYZ-00.pyz'))
    def signature(code):
        return (code.co_code,code.co_names,code.co_varnames,tuple(signature(x) if isinstance(x,types.CodeType) else x for x in code.co_consts))
    for path in (ROOT/'src/handout_cleaner').glob('*.py'):
        module='handout_cleaner' if path.stem=='__init__' else 'handout_cleaner.'+path.stem
        expected=compile(path.read_text(encoding='utf-8'),str(path),'exec')
        actual=reader.extract(module)
        if signature(actual)!=signature(expected):
            raise RuntimeError('冻结代码与源码不一致，请使用 PyInstaller --clean 重新构建：'+module)


def link_tree(source: Path, destination: Path):
    destination.mkdir(parents=True,exist_ok=True)
    for path in source.rglob('*'):
        relative=path.relative_to(source)
        target=destination/relative
        if path.is_dir():
            target.mkdir(parents=True,exist_ok=True)
        elif path.suffix.lower() != '.msi':
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                continue
            try:os.link(path,target)
            except OSError:shutil.copy2(path,target)


def main():
    global APP
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory-only',action='store_true')
    parser.add_argument('--app',type=Path,default=APP)
    parser.add_argument('--vendor',type=Path,default=ROOT/'vendor')
    parser.add_argument('--build-dir',type=Path,default=ROOT/'build/HandoutCleaner')
    parser.add_argument('--release-dir',type=Path,default=ROOT/'release')
    parser.add_argument('--runtime-from',type=Path)
    parser.add_argument('--built-exe',type=Path)
    parser.add_argument('--update-only',action='store_true')
    args=parser.parse_args()
    if args.update_only:
        if not args.runtime_from or '1.0.2' not in (args.runtime_from/'source/src/handout_cleaner/__init__.py').read_text(encoding='utf-8'):
            raise SystemExit('增量包必须复用已验证的 1.0.2 组件')
    # Allow a new release to coexist with an open, older portable directory.
    APP = args.app.resolve()
    verify_code(args.build_dir)
    if args.runtime_from:
        versions=json.loads((args.runtime_from/'component-versions.json').read_text(encoding='utf-8'))
        for name,version in versions.items():
            if metadata.version(name)!=version:
                raise RuntimeError('运行组件版本不同，不能复用：'+name)
        APP.mkdir(parents=True,exist_ok=True)
        if not args.built_exe:
            raise SystemExit('--runtime-from requires --built-exe')
        link_tree(args.runtime_from/'_internal',APP/'_internal')
        shutil.copy2(args.built_exe,APP/'HandoutCleaner.exe')
    if not (APP/'HandoutCleaner.exe').exists():
        raise SystemExit('Run PyInstaller first')
    for name in ('LibreOffice','7zip','fonts'):
        link_tree(args.vendor/name,APP/'vendor'/name)
    source=APP/'source'
    source.mkdir(exist_ok=True)
    for name in ('src','tests','tools','assets'):
        shutil.copytree(ROOT/name,source/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('pyproject.toml','HandoutCleaner.spec','run.py','README.md','LICENSE.txt'):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,source/name)
    shutil.copy2(ROOT/'README.md',APP/'使用说明.txt')
    shutil.copy2(ROOT/'LICENSE.txt',APP/'LICENSE.txt')
    licenses=APP/'licenses';licenses.mkdir(exist_ok=True)
    packages=['PyMuPDF','python-docx','python-pptx','rapidocr-onnxruntime','onnxruntime','PySide6-Essentials','shiboken6','numpy','opencv-python-headless','lxml','Pillow','Shapely','pyclipper','pdf2docx','fonttools','PyYAML','typing_extensions','XlsxWriter','fire','termcolor','tqdm','protobuf','packaging']
    versions={}
    for name in packages:
        dist=metadata.distribution(name)
        versions[name]=dist.version
        target=licenses/name;target.mkdir(exist_ok=True)
        (target/'METADATA.txt').write_text(dist.read_text('METADATA') or name+' '+dist.version,encoding='utf-8')
        for item in dist.files or []:
            if any(token in item.name.lower() for token in ('license','copying','notice','copyright')) and '.dist-info' in str(item):
                path=Path(dist.locate_file(item))
                if path.is_file():shutil.copy2(path,target/item.name)
    (APP/'component-versions.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
    (source/'requirements-lock.txt').write_text('\n'.join(f'{k}=={v}' for k,v in versions.items())+'\nPyInstaller=='+metadata.version('pyinstaller')+'\n',encoding='utf-8')
    reference=source/'references';reference.mkdir(exist_ok=True)
    skill=Path.home()/'.codex/skills/remove-watermarks/SKILL.md'
    if skill.exists():shutil.copy2(skill,reference/'remove-watermarks.SKILL.md')
    print(f'PORTABLE_DIRECTORY={APP}',flush=True)
    if args.directory_only:
        return
    from handout_cleaner import __version__
    filename=f'HandoutCleaner-Update-1.0.2-to-{__version__}.zip' if args.update_only else f'HandoutCleaner-Windows-x64-{__version__}.zip'
    target=args.release_dir/filename
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for path in APP.rglob('*'):
            relative=path.relative_to(APP)
            if args.update_only and relative.parts[0] in ('_internal','vendor'):
                continue
            if path.is_file():z.write(path,'HandoutCleaner/'+relative.as_posix())
        if args.update_only:
            z.write(ROOT/'assets/UPDATE.txt','升级说明.txt')
    with target.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    target.with_suffix('.sha256').write_text(digest+'  '+target.name+'\n',encoding='ascii')
    print(f'RELEASE={target}\nSIZE_MB={target.stat().st_size/1024**2:.1f}\nSHA256={digest}')


if __name__=='__main__':main()
