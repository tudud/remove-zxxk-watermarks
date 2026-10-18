# 去除学科网水印

讲义净化 1.0.3，支持学科网讲义与浙考神墙 PDF 的离线水印清理，以及 Word / PPT 参考答案与解析结论一致性核对。

Windows 10 / 11 x64 便携程序。双击完整运行目录中的 `HandoutCleaner.exe`；收到 ZIP 时先完整解压。
Python、OCR 中文模型、LibreOffice、7-Zip 和中文字体均随包提供，运行时无需联网或安装 Office。

## 使用

1. 添加 ZIP/RAR/7Z、Word、PDF、PPT，或拖入文件 / 文件夹。
2. 选择保存位置，点击“开始处理”。
3. Word 输出习题 `.docx`、`（答案）.docx`、习题 `.pdf`；PDF 输入只输出去水印后的 `.pdf`，不转换 Word、不拆分习题 / 答案；课件仍是 `.pptx`。
4. 打开 `处理报告.html` 查看每次答案修改和待核对事项。

压缩包会递归解压，A3 默认跳过。文件名会删除教材版本、学年、原卷版、解析版、分层作业等标签，保留课时和重难点训练 / 专练。
题目前的试题来源默认整段删除，也可切换“只删年份，保留地区”。清除 Word 页眉页脚后重建居中页码。
PPT 会清理各页、母版和版式中的标识，包括透明底 Logo 图片；默认删除最后一页，可取消勾选“删除 PPT 最后一页”。仅有一页的课件会保留。
PDF 会匹配完整的“欢迎关注公众号：浙考神墙620”，包括 OCR 将前缀与名称分成相邻文本框的情况。
扫描 PDF 中的浅灰色背景水印会先分离淡色层，再旋转识别已知标识；只清理匹配区域中的淡色像素，不使用会抹掉黑色正文的大块白色遮挡。

答案纠错只核对同一题的显式参考选项与“故选A / 正确答案为A”等明确结论。解析结论唯一且与参考答案不符时修改参考答案，并记录依据。它不重新解题，也不判断解析推理本身是否正确。多个冲突结论保持原值并提示核对。
Word 与 PPT 使用相同的明确结论判定。PPT 支持题号 / 典例标记、答案标签、题干末尾括号中的选项，以及叠在题目空括号上的独立红色答案字母；保留原字体、颜色和位置。明确的邻页解析可关联到上一页的单道题。答案汇总必须能通过题号唯一关联；缺少明确结论、题号关联不明或图片内答案会提示人工核对，不根据 OCR 结果改写答案图片。

缺少参考答案的 Word 会生成明确标注“待补充”的答案模板，不会凭空编造答案。PDF 保留原页数和版式，不重新排版，也不生成答案模板；答案纠错应用于 Word 和 PPT，不应用于 PDF。复杂水印与正文完全重叠时可能残留或影响原文，建议检查报告和输出。清理定位基于实际文字 / OCR，未采用整条页边遮挡。

原始资料保留。分发时必须把整个目录压缩传递，包含 `_internal`、`vendor`、`source` 和 `licenses`，不能只发送 EXE。
日常只需保留最新完整运行目录，不依赖旧版；旧版目录、旧 ZIP 和开发构建缓存可在验证后清理。不要删除新版中的运行组件。

## 源码运行

本仓库只包含源码、测试、图标和说明，不包含私人讲义、测试结果或大型运行组件。源码 ZIP 不是可直接运行的便携程序。

使用 Python 3.12 或更新版本，在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pytest pyinstaller psutil
$env:PYTHONPATH = "$PWD/src"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run.py
```

Word / PPT 格式转换、RAR / 7Z 解压和中文字体依赖下节列出的 `vendor` 组件。缺少组件时，相应操作会报告缺失依赖。OCR 中文模型由 RapidOCR 依赖提供。

测试数据默认使用合成内容：`python tools/make_fixtures.py`。仅在显式指定 `--sample-archive` 或 `--sample-pdf` 时读取本地资料；样例及处理结果位于 Git 忽略的 `artifacts/`，不要提交实际讲义或私人资料。

## 构建

安装 `pyproject.toml` 中依赖及 PyInstaller；将 LibreOffice 的免安装文件放入 `vendor/LibreOffice`，7-Zip 放入 `vendor/7zip`，中文字体放入 `vendor/fonts`。

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m pytest -q
python tools/make_icon.py
python -m PyInstaller --clean --noconfirm HandoutCleaner.spec
python tools/package.py
```

命令行可运行 `HandoutCleaner.exe --cli --input "资料.zip" --output "结果目录"`。

磁盘空间不足时，可设置 `HANDOUT_EXE_ONLY=1`，将 PyInstaller 的 `--workpath` 指向 D 盘，然后用 `tools/package.py --build-dir ... --built-exe ... --runtime-from ... --vendor ... --app ... --release-dir ... --update-only` 复用版本完全一致的 1.0.2 运行组件。升级包只包含修改后的程序、源码和说明，不是独立完整版；升级方法见 `assets/UPDATE.txt`。未使用增量参数时仍可生成完整便携 ZIP。

## 许可

本项目采用 AGPL-3.0-or-later，与随包 PyMuPDF 的许可一致。可传递给其他电脑使用和修改；再分发时保留随包源码和第三方许可证。Qt、LibreOffice、7-Zip、RapidOCR、Noto 字体分别遵循自己的开源许可证，见发行包 `licenses` 与各组件目录。LibreOffice 源码入口：https://www.libreoffice.org/about-us/source-code/ 。
