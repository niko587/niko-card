"""Build the single-file page from source/: embed the Blender GLBs (silk hero, floating card, the three-card
deck), the portrait cutout and the vCard into index.src.html, write index.html and Niko-Stathis.vcf into the
output folder (the repo root by default), and copy the link-preview image and icons next to them.

    python3 source/build.py            # writes ../index.html and ../Niko-Stathis.vcf
    python3 source/build.py out/       # writes into another folder
"""
import base64, json, pathlib, shutil, sys
here = pathlib.Path(__file__).parent
root = here.parent
out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root
out.mkdir(parents=True, exist_ok=True)


def fold(line):
    """vCard 3.0 line folding: 75 octets, continuation lines start with one space."""
    parts = [line[:75]]; line = line[75:]
    while line:
        parts.append(" " + line[:74]); line = line[74:]
    return "\r\n".join(parts)


photo = base64.b64encode((here / "contact.jpg").read_bytes()).decode()
vcard = "\r\n".join(fold(l) for l in [
    "BEGIN:VCARD", "VERSION:3.0", "N:Stathis;Niko;;;", "FN:Niko Stathis", "TITLE:Health Insurance Advisor",
    "TEL;TYPE=CELL,VOICE:+1-224-306-4565", "EMAIL;TYPE=INTERNET:niko@nshealthsolutions.org",
    "URL:https://calendly.com/nikostathis", "NOTE:Nationally licensed health insurance advisor.",
    "PHOTO;ENCODING=b;TYPE=JPEG:" + photo, "END:VCARD"]) + "\r\n"
(out / "Niko-Stathis.vcf").write_bytes(vcard.encode())

src = (here / "index.src.html").read_text(encoding="utf-8")
for key, f in (("__SILK_GLB__", "silk.glb"), ("__CARD_GLB__", "card.glb"), ("__DECK_GLB__", "deck.glb")):
    src = src.replace(key, base64.b64encode((here / f).read_bytes()).decode())
src = src.replace("__CUTOUT__", base64.b64encode((here / "cutout.webp").read_bytes()).decode())
src = src.replace("__VCARD_JSON__", json.dumps(vcard))
(out / "index.html").write_text(src, encoding="utf-8")
if out.resolve() != root.resolve():
    for f in ("card.png", "card.webp", "og.jpg", "apple-touch-icon.png", "icon-192.png"):
        shutil.copy(root / f, out / f)
print((out / "index.html").stat().st_size, (out / "Niko-Stathis.vcf").stat().st_size)
