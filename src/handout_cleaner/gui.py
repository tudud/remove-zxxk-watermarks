import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QFont, QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QLineEdit, QCheckBox, QComboBox, QProgressBar, QPlainTextEdit, QMessageBox, QStyle,
    QAbstractItemView, QSplitter)
from .models import Options, Cancelled
from . import __version__


class Worker(QThread):
    update = Signal(dict)
    finished_result = Signal(object)
    error = Signal(str)

    def __init__(self, paths, output, options):
        super().__init__()
        self.paths, self.output, self.options = paths, output, options
        self.stop = threading.Event()

    def run(self):
        from .pipeline import Processor
        processor = Processor(self.options, lambda **kw:self.update.emit(kw), self.stop.is_set)
        try:
            self.finished_result.emit(processor.run(self.paths, self.output))
        except Cancelled as exc:
            processor.write_reports(self.output, datetime.now().isoformat(timespec='seconds'))
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        from .fonts import register_qt_fonts
        register_qt_fonts()
        self.setWindowTitle('讲义净化  ·  便携版 '+__version__)
        self.resize(1120, 830)
        self.setMinimumSize(860, 700)
        self.setAcceptDrops(True)
        self.paths = []
        self.worker = None
        self.rows = {}
        self.closing = False
        self.setStyleSheet('''
            QMainWindow,QWidget{background:#f8faf9;color:#202a25;font-family:"Noto Sans CJK SC","Microsoft YaHei";font-size:15px;}
            QPushButton{background:white;border:1px solid #c9d2cd;border-radius:4px;padding:8px 14px;min-height:24px;}
            QPushButton:hover{background:#edf3ef;border-color:#8aa295;}
            QPushButton:disabled{color:#9ba49e;background:#f0f3f1;}
            QPushButton#start{background:#16735b;color:white;border-color:#16735b;font-weight:600;}
            QPushButton#start:hover{background:#0b5a45;}
            QLineEdit,QComboBox{background:white;border:1px solid #c9d2cd;border-radius:4px;padding:7px;min-height:24px;}
            QTableWidget,QPlainTextEdit{background:white;border:1px solid #d6ded9;gridline-color:#e8ede9;selection-background-color:#e0f0e7;selection-color:#152c20;}
            QHeaderView::section{background:#eef2ef;border:0;border-bottom:1px solid #d6ded9;padding:8px;font-weight:600;}
            QProgressBar{border:1px solid #d1dbd4;background:white;border-radius:3px;text-align:center;min-height:22px;}
            QProgressBar::chunk{background:#65a58c;}
            QCheckBox{spacing:8px;}
            QLabel#title{font-size:24px;font-weight:600;}
            QLabel#badge{color:#66766c;font-size:14px;}
        ''')
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24,20,24,20)
        layout.setSpacing(13)
        heading = QHBoxLayout()
        title = QLabel('讲义净化');title.setObjectName('title')
        heading.addWidget(title)
        heading.addStretch()
        badge = QLabel('本地处理  ·  Windows x64');badge.setObjectName('badge')
        heading.addWidget(badge)
        layout.addLayout(heading)
        toolbar = QHBoxLayout()
        self.add = self.button('添加文件', QStyle.SP_FileIcon, self.add_files)
        self.folder = self.button('添加文件夹', QStyle.SP_DirIcon, self.add_folder)
        self.remove = self.button('移除选中', QStyle.SP_TrashIcon, self.remove_selected)
        toolbar.addWidget(self.add);toolbar.addWidget(self.folder);toolbar.addWidget(self.remove)
        toolbar.addStretch()
        self.count = QLabel('0 个输入')
        toolbar.addWidget(self.count)
        layout.addLayout(toolbar)
        self.input_table = QTableWidget(0,3)
        self.input_table.setHorizontalHeaderLabels(['输入文件', '格式', '大小'])
        self.input_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.input_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.input_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.input_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.input_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.input_table.verticalHeader().hide()
        self.input_table.setMinimumHeight(125)
        self.input_table.setMaximumHeight(185)
        layout.addWidget(self.input_table)
        settings = QHBoxLayout()
        settings.addWidget(QLabel('题目来源'))
        self.source_mode = QComboBox()
        self.source_mode.addItem('删除完整来源','all')
        self.source_mode.addItem('只删年份，保留地区','year')
        self.source_mode.addItem('保留来源','keep')
        settings.addWidget(self.source_mode)
        self.ocr = QCheckBox('扫描图像 OCR');self.ocr.setChecked(True)
        self.correction = QCheckBox('核对 Word / PPT 答案');self.correction.setChecked(True)
        self.correction.setToolTip('按同题明确解析结论核对，不重新解题；冲突或图片答案会提示人工核对。')
        self.skip = QCheckBox('跳过 A3');self.skip.setChecked(True)
        settings.addWidget(self.ocr);settings.addWidget(self.correction);settings.addWidget(self.skip)
        settings.addStretch()
        layout.addLayout(settings)
        row = QHBoxLayout()
        self.last_slide = QCheckBox('删除 PPT 最后一页');self.last_slide.setChecked(True)
        row.addWidget(self.last_slide)
        row.addStretch()
        layout.addLayout(row)
        destination = QHBoxLayout()
        destination.addWidget(QLabel('保存位置'))
        self.output = QLineEdit(str(Path.home()/'Desktop'/('讲义净化-'+datetime.now().strftime('%Y%m%d-%H%M'))))
        destination.addWidget(self.output,1)
        self.browse = self.button('选择',QStyle.SP_DirOpenIcon,self.choose_output)
        destination.addWidget(self.browse)
        self.open = self.button('打开结果',QStyle.SP_DirLinkIcon,self.open_output)
        destination.addWidget(self.open)
        layout.addLayout(destination)
        self.results = QTableWidget(0,3)
        self.results.setHorizontalHeaderLabels(['讲义 / 课件', '状态', '输出 / 待核对事项'])
        self.results.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.results.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.results.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
        self.results.verticalHeader().hide()
        self.results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results.setWordWrap(True)
        layout.addWidget(self.results,1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True);self.log.setMaximumHeight(115);self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log)
        self.progress = QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0)
        layout.addWidget(self.progress)
        bottom = QHBoxLayout()
        self.status = QLabel('就绪')
        self.status.setWordWrap(True)
        bottom.addWidget(self.status,1)
        self.cancel = self.button('停止',QStyle.SP_MediaStop,self.stop)
        self.cancel.setEnabled(False)
        self.start = self.button('开始处理',QStyle.SP_MediaPlay,self.begin);self.start.setObjectName('start')
        bottom.addWidget(self.cancel);bottom.addWidget(self.start)
        layout.addLayout(bottom)
        self.setCentralWidget(central)

    def button(self, text, icon, action):
        button=QPushButton(self.style().standardIcon(icon),text)
        button.clicked.connect(action)
        return button

    def add_paths(self, paths):
        if self.worker and self.worker.isRunning():
            return
        for value in paths:
            path=Path(value)
            if path not in self.paths and path.exists():
                self.paths.append(path)
                row=self.input_table.rowCount();self.input_table.insertRow(row)
                data=[path.name, '文件夹' if path.is_dir() else path.suffix.upper().lstrip('.'), '—' if path.is_dir() else f'{path.stat().st_size/1024**2:.1f} MB']
                for col,text in enumerate(data):
                    item=QTableWidgetItem(text);item.setToolTip(str(path));self.input_table.setItem(row,col,item)
        self.count.setText(f'{len(self.paths)} 个输入')

    def add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'选择讲义或压缩包','','讲义资料 (*.zip *.rar *.7z *.doc *.docx *.pdf *.ppt *.pptx)')
        self.add_paths(files)

    def add_folder(self):
        path=QFileDialog.getExistingDirectory(self,'选择资料文件夹')
        if path:self.add_paths([path])

    def remove_selected(self):
        for row in sorted({x.row() for x in self.input_table.selectedIndexes()},reverse=True):
            self.paths.pop(row);self.input_table.removeRow(row)
        self.count.setText(f'{len(self.paths)} 个输入')

    def choose_output(self):
        path=QFileDialog.getExistingDirectory(self,'选择保存位置')
        if path:self.output.setText(path)

    def open_output(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.output.text()))

    def busy(self,value):
        for widget in [self.add,self.folder,self.remove,self.start,self.source_mode,self.ocr,self.correction,self.skip,self.output,self.browse,self.last_slide]:
            widget.setEnabled(not value)
        self.cancel.setEnabled(value)

    def begin(self):
        if not self.paths:
            QMessageBox.information(self,'未选择资料','请添加资料文件或文件夹。');return
        if not self.output.text().strip():return
        self.results.setRowCount(0);self.rows={};self.log.clear();self.busy(True)
        self.progress.setRange(0,0)
        options=Options(source_mode=self.source_mode.currentData(),ocr=self.ocr.isChecked(),correct_answers=self.correction.isChecked(),skip_a3=self.skip.isChecked(),remove_last_slide=self.last_slide.isChecked())
        self.worker=Worker(list(self.paths),Path(self.output.text()),options)
        self.worker.update.connect(self.on_update)
        self.worker.finished_result.connect(self.on_finish)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(lambda:self.busy(False))
        self.worker.start()

    def on_update(self,data):
        message=data.get('message','')
        if message:self.status.setText(message);self.log.appendPlainText(message)
        if 'total' in data:
            self.progress.setRange(0,data['total']);self.progress.setValue(data.get('current',0))
        name=data.get('name')
        if name:
            if name not in self.rows:
                self.rows[name]=self.results.rowCount();self.results.insertRow(self.rows[name])
            row=self.rows[name]
            record=data.get('record',{})
            detail='；'.join(record.get('warnings',[])) or '、'.join(Path(p).name for p in record.get('outputs',[]))
            for col,text in enumerate([name,record.get('status','处理中'),detail]):
                item=QTableWidgetItem(text);item.setToolTip(text);self.results.setItem(row,col,item)
            self.results.resizeRowToContents(row)
            self.results.scrollToBottom()

    def on_finish(self,records):
        failed=sum(r.status=='失败' for r in records)
        files=sum(len(r.outputs) for r in records)
        changes=sum(len(r.changes) for r in records)
        self.status.setText(f'处理结束 · {files} 个输出 · 答案修正 {changes} 处 · 失败 {failed} 项')
        self.log.appendPlainText(self.status.text())

    def on_error(self,message):
        self.status.setText(message);self.log.appendPlainText(message)
        self.progress.setRange(0,100);self.progress.setValue(0)

    def stop(self):
        if self.worker:self.worker.stop.set();self.status.setText('正在停止，等待当前步骤完成…');self.cancel.setEnabled(False)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()

    def dropEvent(self,event):
        self.add_paths([u.toLocalFile() for u in event.mimeData().urls()])

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.stop();event.ignore()
        else:event.accept()


def run_gui():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Noto Sans CJK SC',11))
    window=Window();window.show()
    return app.exec()
