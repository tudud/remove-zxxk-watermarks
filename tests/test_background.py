from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from handout_cleaner.background import clean_faint_background
from handout_cleaner.ocr import OCR


def test_faint_diagonal_mark_preserves_every_dark_pixel():
    image=Image.new('RGB',(1000,1400),'white')
    font=ImageFont.truetype('vendor/fonts/NotoSansCJKsc-Regular.otf',140)
    mark=Image.new('RGBA',(950,200))
    ImageDraw.Draw(mark).text((0,0),'浙考神墙620',font=font,fill=(232,232,232,255))
    mark=mark.rotate(45,expand=True)
    image.paste(mark,(50,200),mark)
    draw=ImageDraw.Draw(image)
    textfont=ImageFont.truetype('vendor/fonts/NotoSansCJKsc-Regular.otf',24)
    for y in range(150,1250,70):draw.text((70,y),'1. 答案A。质量620克，计算过程保留。',font=textfont,fill=(20,20,20))
    stream=BytesIO();image.save(stream,format='PNG')
    cleaned,count=clean_faint_background(stream.getvalue(),OCR())
    before=np.asarray(image);after=np.asarray(Image.open(BytesIO(cleaned)).convert('RGB'))
    assert count>0
    dark=before.min(axis=2)<180
    assert np.array_equal(before[dark],after[dark])
    pale=(before.min(axis=2)>210)&(before.max(axis=2)<245)
    assert np.mean(after[pale].min(axis=1)>250)>.85
