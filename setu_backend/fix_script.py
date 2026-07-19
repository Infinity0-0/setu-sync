
import re

with open('e:\setu\auth.html', 'r', encoding="utf-8") as f:
    content = f.read()

style_start = content.find("<style>")
style_end = content.find("</style>", style_start) + len("</style>")
old_style = content[style_start:style_end]

print("Old style len:", len(old_style))
