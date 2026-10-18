from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[1]
(root/'assets').mkdir(exist_ok=True)
image=Image.new('RGBA',(256,256),(19,107,82,255))
d=ImageDraw.Draw(image)
d.rounded_rectangle((56,28,200,226),radius=8,fill='white')
d.line((82,79,172,79),fill='#a1c8b6',width=9)
d.line((82,111,172,111),fill='#a1c8b6',width=9)
d.line((82,143,140,143),fill='#a1c8b6',width=9)
d.line((88,181,113,202,173,155),fill='#136b52',width=13)
image.save(root/'assets'/'app.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
