"""A small PDF writer (standard library only) for the made-up documents: letters and financial statements.

Pages hold headings, wrapped paragraphs and monospaced tables in the standard PDF fonts (Helvetica and
Courier, WinAnsi encoding), so nothing is embedded and the output is byte-identical on every run. Every
page carries a footer saying the document is a made-up example.
"""
import zlib

A4_W, A4_H = 595.28, 841.89


class PDF:
    def __init__(self, title: str, footer: str = "Made-up example for Example Holding. Not a real document."):
        self.title, self.footer = title, footer
        self.pages = []
        self.m = 56
        self.new_page()

    # ------------------------------------------------------------ layout
    def new_page(self):
        self.cur = []
        self.pages.append(self.cur)
        self.y = A4_H - self.m

    def need(self, h):
        if self.y - h < self.m + 24:
            self.new_page()

    @staticmethod
    def _esc(s: str) -> str:
        s = s.encode("cp1252", "replace").decode("latin-1")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def text(self, x, y, s, font="F1", size=10):
        self.cur.append(f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({self._esc(s)}) Tj ET")

    def heading(self, s, size=13):
        self.need(size + 16)
        self.y -= size + 8
        self.text(self.m, self.y, s, "F2", size)
        self.y -= 4

    def para(self, s, size=10, bold=False, indent=0, gap=4):
        width = (A4_W - 2 * self.m - indent) / (0.53 * size)
        words, line, lines = s.split(), "", []
        for w in words:
            if len(line) + len(w) + 1 > width and line:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            lines.append(line)
        for ln in lines:
            self.need(size + 3)
            self.y -= size + 3
            self.text(self.m + indent, self.y, ln, "F2" if bold else "F1", size)
        self.y -= gap

    def bullets(self, items, size=10):
        for it in items:
            self.need(size + 3)
            self.text(self.m + 6, self.y - size - 3, "-", "F1", size)
            self.para(it, size=size, indent=18, gap=1)
        self.y -= 3

    def table(self, rows, widths, size=8.5, header=True, aligns=None):
        """rows: lists of strings; widths in characters (Courier)."""
        aligns = aligns or ["l"] + ["r"] * (len(widths) - 1)
        for i, row in enumerate(rows):
            cells = []
            for c, w, a in zip(row, widths, aligns):
                c = str(c)[:w]
                cells.append(c.ljust(w) if a == "l" else c.rjust(w))
            self.need(size + 3)
            self.y -= size + 3
            bold = header and i == 0 or (row and str(row[0]).startswith("Total"))
            self.text(self.m, self.y, " ".join(cells), "F4" if bold else "F3", size)
        self.y -= 6

    def space(self, h=8):
        self.y -= h

    # ------------------------------------------------------------ output
    def save(self, path):
        objs = []

        def add(b):
            objs.append(b)
            return len(objs)

        fonts = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Courier", "F4": "Courier-Bold"}
        font_ids = {k: add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{v} /Encoding /WinAnsiEncoding >>".encode())
                    for k, v in fonts.items()}
        pages_id = len(objs) + 1
        objs.append(None)  # placeholder for the pages tree
        page_ids = []
        n = len(self.pages)
        for i, ops in enumerate(self.pages):
            foot = [f"BT /F1 7.5 Tf {self.m:.2f} 30 Td ({self._esc(self.footer)}) Tj ET",
                    f"BT /F1 7.5 Tf {A4_W - self.m - 60:.2f} 30 Td ({self._esc(f'Page {i + 1} of {n}')}) Tj ET"]
            stream = zlib.compress("\n".join(ops + foot).encode("latin-1"), 9)
            cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
            res = " ".join(f"/{k} {v} 0 R" for k, v in font_ids.items())
            page_ids.append(add((f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {A4_W} {A4_H}] "
                                 f"/Resources << /Font << {res} >> >> /Contents {cid} 0 R >>").encode()))
        objs[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>").encode()
        info = add(f"<< /Title ({self._esc(self.title)}) /Producer (Example Holding generator) "
                   f"/CreationDate (D:20261120000000+03'00') >>".encode("latin-1"))
        cat = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, o in enumerate(objs):
            offs.append(len(out))
            out += f"{i + 1} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for o in offs:
            out += f"{o:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root {cat} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        with open(path, "wb") as f:
            f.write(out)


def sar(v, dec=0):
    """Format halalas as SAR with thousands separators; negatives in brackets."""
    x = v / 100.0
    s = f"{abs(x):,.{dec}f}"
    return f"({s})" if x < 0 else s
