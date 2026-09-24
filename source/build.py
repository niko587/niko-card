"""Rebuild ../index.html: run `python3 build_scene.py "$PWD/"` (needs `pip install bpy`) to re-export the GLBs, then `python3 build.py`."""
import base64, pathlib
here = pathlib.Path(__file__).parent
src = (here / "index.src.html").read_text()
for key, f in (("__SILK_GLB__", "silk.glb"), ("__CARD_GLB__", "card.glb")):
    src = src.replace(key, base64.b64encode((here / f).read_bytes()).decode())
src = src.replace("__CUTOUT__", base64.b64encode((here / "cutout.webp").read_bytes()).decode())
(here.parent / "index.html").write_text(src)
print("wrote", here.parent / "index.html")
