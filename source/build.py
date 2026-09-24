"""Build the single-file page: embed the Blender GLBs, the portrait cutout and the vCard, then copy the
static files (card image, link-preview image, icons and the .vcf) next to it."""
import base64, json, pathlib, shutil, sys
here = pathlib.Path(__file__).parent
scratch = here.parent
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)


def fold(line):
    """vCard 3.0 line folding: 75 octets, continuation lines start with one space."""
    parts = [line[:75]]; line = line[75:]
    while line:
        parts.append(" " + line[:74]); line = line[74:]
    return "\r\n".join(parts)


photo = base64.b64encode((scratch / "contact.jpg").read_bytes()).decode()
vcard = "\r\n".join(fold(l) for l in [
    "BEGIN:VCARD", "VERSION:3.0", "N:Stathis;Niko;;;", "FN:Niko Stathis", "TITLE:Health Insurance Advisor",
    "TEL;TYPE=CELL,VOICE:+1-224-306-4565", "EMAIL;TYPE=INTERNET:niko@nshealthsolutions.org",
    "URL:https://calendly.com/nikostathis", "NOTE:Nationally licensed health insurance advisor.",
    "PHOTO;ENCODING=b;TYPE=JPEG:" + photo, "END:VCARD"]) + "\r\n"
(out / "Niko-Stathis.vcf").write_bytes(vcard.encode())

src = (here / "index.src.html").read_text()
for key, f in (("__SILK_GLB__", "silk.glb"), ("__CARD_GLB__", "card.glb")):
    src = src.replace(key, base64.b64encode((scratch / "blender" / f).read_bytes()).decode())
src = src.replace("__CUTOUT__", base64.b64encode((scratch / "cutout.webp").read_bytes()).decode())
src = src.replace("__VCARD_JSON__", json.dumps(vcard))
(out / "index.html").write_text(src)
shutil.copy("/root/.claude/uploads/05693cae-b467-5e04-881f-6177f129669e/0bfd6982-Untitled-6.png", out / "card.png")
for f in ("og.jpg", "apple-touch-icon.png", "icon-192.png"):
    shutil.copy(scratch / f, out / f)
print((out / "index.html").stat().st_size, (out / "Niko-Stathis.vcf").stat().st_size)
