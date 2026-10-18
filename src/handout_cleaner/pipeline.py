import html
import json
import re
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from .models import Options, Record, Cancelled
from .rules import clean_name, edition
from .archives import discover
from .convert import convert_office
from .ocr import OCR
from .word import clean_docx, has_answers, answer_template
from .pdf import clean_pdf
from .slides import clean_pptx


class Processor:
    def __init__(self, options=None, callback=None, cancelled=None):
        self.options = options or Options()
        self.callback = callback or (lambda **kw: None)
        self.cancelled = cancelled or (lambda: False)
        self.ocr = OCR()
        self.records = []

    def check(self):
        if self.cancelled():
            raise Cancelled('已停止；已完成的输出仍保留')

    def emit(self, **data):
        self.callback(**data)

    def run(self, inputs: list[Path], output: Path):
        output = output.resolve()
        inputs = [p.resolve() for p in inputs]
        output.mkdir(parents=True, exist_ok=True)
        started = time.strftime('%Y-%m-%d %H:%M:%S')
        self.emit(message='正在扫描并解压资料…')
        with tempfile.TemporaryDirectory(prefix='hc-') as temp:
            work = Path(temp)
            files = discover(inputs, work, self.check, exclude=output)
            groups = {}
            for path, origin in files:
                if self.options.skip_a3 and re.search(r'(?i)A3', path.stem):
                    self.records.append(Record(str(path), status='跳过 A3'))
                    continue
                suffix = path.suffix.lower()
                kind = 'ppt' if suffix in ('.ppt','.pptx') else 'pdf' if suffix == '.pdf' else 'doc'
                name = clean_name(path.name, ppt=kind == 'ppt')
                if kind == 'pdf' and edition(path.stem) == 'answer':
                    name += '（答案）'
                # PDFs remain independent, even beside a same-title Word file.
                key = (origin, name, kind, str(path) if kind == 'pdf' else '')
                groups.setdefault(key, []).append(path)
            if not groups:
                raise ValueError('没有找到可处理的 Word、PDF 或 PowerPoint 文件')
            used = set()
            for index, ((origin, name, kind, _), sources) in enumerate(groups.items()):
                self.check()
                record = Record(' | '.join(str(p) for p in sources))
                self.records.append(record)
                self.emit(current=index, total=len(groups), name=name, message=f'正在处理：{name}')
                try:
                    stage = work / ('result'+str(index))
                    stage.mkdir()
                    if kind == 'ppt':
                        source = sources[0]
                        if source.suffix.lower() == '.ppt':
                            source = convert_office(source, work/('legacy'+str(index)), 'pptx')
                        clean_pptx(source, stage/(name+'.pptx'), self.options, record, self.ocr)
                    elif kind == 'pdf':
                        clean_pdf(sources[0], stage/(name+'.pdf'), self.options, record, self.ocr, lambda msg:self.emit(message=msg), self.check)
                    else:
                        self.process_handout(sources, name, stage, work/('job'+str(index)), record)
                    destination = output
                    if any((origin, p.name) in used or (destination/p.name).exists() for p in stage.iterdir()):
                        destination = output / clean_name(origin)
                        number = 2
                        while destination.exists():
                            destination = output / (clean_name(origin)+f'-{number}')
                            number += 1
                    destination.mkdir(parents=True, exist_ok=True)
                    for path in stage.iterdir():
                        dst = destination/path.name
                        shutil.move(str(path), dst)
                        used.add((origin, path.name))
                        record.outputs.append(str(dst))
                    record.status = '完成（需核对）' if record.warnings else '完成'
                except Cancelled:
                    raise
                except Exception as exc:
                    record.status = '失败'
                    record.warnings.append(str(exc))
                    self.emit(message=f'处理失败：{name} — {exc}')
                    with (output/'error-details.log').open('a', encoding='utf-8') as error_log:
                        error_log.write(traceback.format_exc()+'\n')
                self.write_reports(output, started)
                self.emit(current=index+1, total=len(groups), name=name, record=record.to_dict(), message=record.status+'：'+name)
        self.write_reports(output, started)
        return self.records

    def process_handout(self, sources, name, stage, work, record):
        work.mkdir(parents=True, exist_ok=True)
        normalized = []
        for index, source in enumerate(sources):
            self.check()
            role = edition(source.stem)
            if source.suffix.lower() == '.doc':
                source = convert_office(source, work/('converted'+str(index)), 'docx')
            normalized.append((source, role))
        answers = [p for p,r in normalized if r == 'answer']
        practices = [p for p,r in normalized if r == 'practice']
        standard = [p for p,r in normalized if r == 'standard']
        answer = answers[0] if answers else None
        practice = practices[0] if practices else (standard[0] if standard else None)
        if len(practices) > 1 or len(standard) > 1:
            record.warnings.append('发现多个同名习题源，优先原卷版；请在原压缩包中核对重复版本')
        answer_output = stage/(name+'（答案）.docx')
        practice_output = stage/(name+'.docx')
        practice_pdf = stage/(name+'.pdf')
        if practice and practice.suffix.lower() == '.docx' and not answer and has_answers(practice):
            answer, practice = practice, None
        if answer and answer.suffix.lower() == '.docx':
            clean_docx(answer, answer_output, self.options, record, self.ocr)
            if not practice:
                clean_docx(answer_output, practice_output, self.options, record, None, practice=True, remove_answers=True)
        if practice:
            if practice.suffix.lower() == '.docx':
                clean_docx(practice, practice_output, self.options, record, self.ocr, practice=True)
        if not practice_output.exists():
            raise ValueError('没有生成习题 Word，输入资料不完整')
        if not answer_output.exists():
            answer_template(answer_output, name)
            record.warnings.append('输入资料没有可识别答案；已生成标明“待补充”的答案模板')
        for extra_index, extra in enumerate(answers[1:], 2):
            if extra.suffix.lower() == '.docx':
                extra_output = stage/(name+f'（详解{extra_index}）（答案）.docx')
                clean_docx(extra, extra_output, self.options, record, self.ocr)
                record.warnings.append('存在多份答案，已额外保留详解副本')
        if not practice_pdf.exists():
            convert_office(practice_output, stage, 'pdf:writer_pdf_Export')

    def write_reports(self, output, started):
        from . import __version__
        report = {'version':__version__, 'started':started, 'options':vars(self.options), 'records':[r.to_dict() for r in self.records]}
        (output/'处理报告.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        rows=[]
        for r in self.records:
            corrections='<br>'.join(html.escape((f"第{x['slide']}页 " if x.get('slide') else '')+f"第{x['question']}题：{x['before']} → {x['after']}；依据：{x['evidence']}") for x in r.changes)
            corrections='<br>'.join(filter(None, [corrections, '<br>'.join(html.escape(a) for a in r.actions)]))
            warnings='<br>'.join(html.escape(w) for w in r.warnings)
            links='<br>'.join(f'<a href="{html.escape(Path(p).as_uri(),quote=True)}">{html.escape(Path(p).name)}</a>' for p in r.outputs)
            rows.append(f'<tr><td>{html.escape(Path(r.source.split(" | ")[0]).name)}</td><td>{html.escape(r.status)}</td><td>{links}</td><td>{r.watermark_count}</td><td>{r.source_count}</td><td>{corrections}</td><td>{warnings}</td></tr>')
        page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>讲义处理报告</title><style>body{font:16px "Microsoft YaHei",sans-serif;margin:32px;color:#202825}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d9dfdc;padding:10px;text-align:left;vertical-align:top}th{background:#edf3ef}a{color:#086958}h1{font-size:24px}</style><h1>讲义处理报告</h1><p>开始时间：'+html.escape(started)+'</p><table><thead><tr><th>输入</th><th>状态</th><th>输出文件</th><th>水印匹配</th><th>来源清理</th><th>答案修正</th><th>待核对事项</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></html>'
        (output/'处理报告.html').write_text(page, encoding='utf-8')
