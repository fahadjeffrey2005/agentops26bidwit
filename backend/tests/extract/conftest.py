import zlib
from pathlib import Path

import pytest
from pypdf import PdfWriter

FIX = Path(__file__).parent / "fixtures"


def _raw_pdf(objs: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.7\n")
    offs = []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture(scope="session")
def hostile(tmp_path_factory) -> dict[str, Path]:
    """Hostile files are generated at test time, never stored in the repo."""
    d = tmp_path_factory.mktemp("hostile")
    c = zlib.compressobj(9)
    chunk = b"0 " * (8 * 1024 * 1024)
    bomb = b"".join(c.compress(chunk) for _ in range(64)) + c.flush()          # 1 GiB when inflated
    (d / "bomb.pdf").write_bytes(_raw_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>",
        f"<< /Length {len(bomb)} /Filter /FlateDecode >>\nstream\n".encode() + bomb + b"\nendstream"]))
    (d / "loop.pdf").write_bytes(_raw_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [2 0 R 3 0 R] /Count 2 >>",
        b"<< /Type /Pages /Parent 2 0 R /Kids [2 0 R] /Count 1 >>"]))
    w = PdfWriter(); w.add_blank_page(595, 842); w.encrypt("secret"); w.write(str(d / "encrypted.pdf"))
    (d / "fake.pdf").write_bytes(b"MZ\x90\x00 not a pdf" * 50)
    src = (FIX / "hard_tender.pdf").read_bytes()
    (d / "truncated.pdf").write_bytes(src[: len(src) // 2])
    w = PdfWriter()
    for _ in range(600):
        w.add_blank_page(595, 842)
    w.write(str(d / "too_many_pages.pdf"))
    (d / "empty.pdf").write_bytes(b"")
    return {p.stem: p for p in d.iterdir()}
