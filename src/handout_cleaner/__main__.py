import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='讲义净化 Windows 便携版')
    parser.add_argument('--cli', action='store_true')
    parser.add_argument('--input', nargs='+')
    parser.add_argument('--output')
    parser.add_argument('--no-ocr', action='store_true')
    parser.add_argument('--keep-last-slide', action='store_true')
    parser.add_argument('--source-mode', choices=['all','year','keep'], default='all')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        from .models import vendor_root
        from .convert import office_binary
        from .ocr import OCR
        from PIL import Image
        engine = OCR()
        engine.read(Image.new('RGB', (200,100), 'white'))
        check={'office':office_binary().exists(), 'ocr':True, '7zip':(vendor_root()/'7zip'/'7z.exe').exists()}
        if args.output:
            Path(args.output).write_text(json.dumps(check), encoding='utf-8')
        return 0 if all(check.values()) else 1
    if args.cli:
        if not args.input or not args.output:
            parser.error('--cli 需要 --input 与 --output')
        from .pipeline import Processor
        from .models import Options
        records = Processor(Options(source_mode=args.source_mode,ocr=not args.no_ocr,remove_last_slide=not args.keep_last_slide), lambda **d: print(d.get('message',''),flush=True)).run([Path(p) for p in args.input],Path(args.output))
        return 1 if any(r.status=='失败' for r in records) else 0
    from .gui import run_gui
    return run_gui()


if __name__ == '__main__':
    raise SystemExit(main())
