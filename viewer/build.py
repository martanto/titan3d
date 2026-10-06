"""Inject a granflow JSON bundle into the three.js viewer template."""
import sys, pathlib
tpl, data, out = sys.argv[1:4]
html = pathlib.Path(tpl).read_text().replace("/*__DATA__*/null", pathlib.Path(data).read_text())
pathlib.Path(out).write_text(html)
print(out, f"{len(html)/1e6:.2f} MB")
