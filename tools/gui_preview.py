import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from handout_cleaner.gui import Window

app=QApplication(sys.argv)
app.setStyle('Fusion')
window=Window()
root=Path(__file__).resolve().parents[1]
window.add_paths([root/'artifacts/fixtures/学科网测试包.zip',root/'artifacts/fixtures/浙考神墙扫描测试.pdf'])
window.on_update({'name':'第2节 物质的导电性','total':2,'current':1,'message':'完成：第2节 物质的导电性','record':{'status':'完成','outputs':['第2节 物质的导电性.docx','第2节 物质的导电性（答案）.docx','第2节 物质的导电性.pdf'],'warnings':[]}})
window.show()
def capture():
    window.grab().save(str(root/'artifacts/gui-preview.png'))
    app.quit()
QTimer.singleShot(1500,capture)
app.exec()
