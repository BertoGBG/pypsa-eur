"""md -> html (python-markdown) -> pdf (headless Chrome). Usage: md2pdf.py in.md out.pdf"""

import pathlib
import re
import subprocess
import sys
import tempfile

import markdown

src = pathlib.Path(sys.argv[1]).resolve()
out = pathlib.Path(sys.argv[2]).resolve()
text = src.read_text(encoding="utf-8")

# expand <details> for print: summary becomes a bold paragraph
text = re.sub(r"<details>\s*<summary>(.*?)</summary>", r"**\1**", text, flags=re.S)
text = text.replace("</details>", "")

body = markdown.markdown(text, extensions=["tables", "toc", "fenced_code", "sane_lists"])
body = re.sub(r"<p><em>((?:Figure|Table) \d+)", r'<p class="caption"><em>\1', body)
body = re.sub(r"<p><strong>(Table 12[a-p]\.)", r'<p class="caption sub"><strong>\1', body)

css = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; font-size: 10pt;
       line-height: 1.45; color: #1a1a1a; background: #fff; }
h1 { font-size: 18pt; } h2 { font-size: 14pt; border-bottom: 1px solid #ccc; padding-bottom: 2px; margin-top: 1.6em; }
h3 { font-size: 12pt; } h4 { font-size: 10.5pt; }
h1, h2, h3, h4 { break-after: avoid; page-break-after: avoid; }
table { border-collapse: collapse; margin: 0.4em 0 1em; font-size: 8.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 2px 6px; vertical-align: top; }
th { background: #f2f2f2; }
img { max-width: 100%; display: block; margin: 0.6em auto 0.2em; page-break-inside: avoid; }
code { font-size: 8.5pt; background: #f5f5f5; padding: 0 2px; }
p.caption { font-size: 8.5pt; color: #444; margin: 0.2em 0 0.4em; page-break-after: avoid; }
p.caption.sub { font-size: 9pt; color: #1a1a1a; margin-top: 1em; }
a { color: #1f5fa8; text-decoration: none; }
"""
html = f"""<!doctype html><html><head><meta charset="utf-8">
<base href="{src.parent.as_uri()}/"><style>{css}</style></head><body>{body}</body></html>"""

with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
    f.write(html)
    tmp = f.name

chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
subprocess.run(
    [chrome, "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
     "--no-pdf-header-footer", f"--print-to-pdf={out}", pathlib.Path(tmp).as_uri()],
    check=True, capture_output=True,
)
print("wrote", out)
