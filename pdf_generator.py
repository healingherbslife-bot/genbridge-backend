"""
GenBridge Invoice PDF Generator
Generates PDF invoices using only Python stdlib (struct, zlib).
A minimal but complete PDF writer - no external libraries required.
"""
import struct, zlib, io, math
from datetime import datetime

# ── Minimal PDF builder ────────────────────────────────────────────────────────
class PDF:
    def __init__(self):
        self.objects = []   # list of (offset, content_bytes)
        self.buf = io.BytesIO()
        self._write(b"%PDF-1.4\n")
        self.pages = []
        self.fonts = {}
        self._add_fonts()

    def _write(self, data: bytes):
        self.buf.write(data)

    def _add_obj(self, content: str) -> int:
        oid = len(self.objects) + 1
        offset = self.buf.tell()
        self._write(f"{oid} 0 obj\n{content}\nendobj\n".encode())
        self.objects.append(offset)
        return oid

    def _add_fonts(self):
        # Helvetica (standard PDF font - no embedding needed)
        self.font_regular = self._add_obj(
            "<</Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            "/Encoding /WinAnsiEncoding>>")
        self.font_bold = self._add_obj(
            "<</Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            "/Encoding /WinAnsiEncoding>>")

    def add_page(self, content_stream: bytes, width=595, height=842) -> int:
        """Add a page and return its object ID."""
        # Compress stream
        compressed = zlib.compress(content_stream)
        stream_obj = self._add_obj(
            f"<</Filter /FlateDecode /Length {len(compressed)}>>\nstream\n"
            + compressed.decode("latin-1") + "\nendstream")

        page_id = self._add_obj(
            f"<</Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {width} {height}] "
            f"/Contents {stream_obj} 0 R "
            f"/Resources <</Font <</F1 {self.font_regular} 0 R "
            f"/F2 {self.font_bold} 0 R>>>>>>")
        self.pages.append(page_id)
        return page_id

    def save(self) -> bytes:
        pages_refs = " ".join(f"{p} 0 R" for p in self.pages)
        pages_id = self._add_obj(
            f"<</Type /Pages /Kids [{pages_refs}] /Count {len(self.pages)}>>")

        # Patch page parent reference
        catalog_id = self._add_obj(
            f"<</Type /Catalog /Pages {pages_id} 0 R>>")

        # Cross-reference table
        xref_offset = self.buf.tell()
        n = len(self.objects) + 1
        self._write(f"xref\n0 {n}\n0000000000 65535 f \n".encode())
        for off in self.objects:
            self._write(f"{off:010d} 00000 n \n".encode())

        self._write(
            f"trailer\n<</Size {n} /Root {catalog_id} 0 R>>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode())
        return self.buf.getvalue()


def _esc(text: str) -> str:
    """Escape text for PDF string literals."""
    return str(text).replace("\\","\\\\").replace("(","\\(").replace(")","\\)")


def _stream(*ops) -> bytes:
    return "\n".join(ops).encode("latin-1")


# ── Colour helpers ─────────────────────────────────────────────────────────────
def _rg(hex_color: str):
    h = hex_color.lstrip("#")
    r,g,b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    return f"{r:.3f} {g:.3f} {b:.3f} rg"

def _RG(hex_color: str):
    h = hex_color.lstrip("#")
    r,g,b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    return f"{r:.3f} {g:.3f} {b:.3f} RG"


# ── Invoice PDF ────────────────────────────────────────────────────────────────
def generate_invoice_pdf(invoice: dict, booking: dict, workshop: dict, programme: dict) -> bytes:
    """
    Build a professional A4 invoice PDF.
    All arguments are plain dicts from the database.
    Returns raw PDF bytes.
    """
    W, H = 595, 842          # A4 in points
    NAVY  = "1B3A6B"
    TEAL  = "0D7377"
    GOLD  = "C8962E"
    LIGHT = "F0F4FA"
    MID   = "4A5568"

    def fmt_lkr(cents):
        return f"LKR {cents:,}"

    lines = []

    # ── Background header band ─────────────────────────────────────────────
    lines += [
        f"{_rg(NAVY)}",
        f"0 {H-120} {W} 120 re f",            # Navy header rect
        f"{_rg(GOLD)}",
        f"0 {H-124} {W} 4 re f",              # Gold underline strip
    ]

    # ── Logo text ──────────────────────────────────────────────────────────
    lines += [
        "BT",
        f"/F2 28 Tf",
        f"1 1 1 rg",                           # white
        f"40 {H-65} Td",
        f"(GenBridge) Tj",
        "ET",
        "BT",
        f"/F1 11 Tf",
        f"0.75 0.85 0.9 rg",
        f"40 {H-85} Td",
        f"(Corporate Training Solutions) Tj",
        "ET",
    ]

    # ── INVOICE label (top right) ──────────────────────────────────────────
    lines += [
        "BT",
        f"/F2 22 Tf",
        f"{_rg(GOLD)}",
        f"400 {H-55} Td",
        f"(INVOICE) Tj",
        "ET",
        "BT",
        f"/F1 10 Tf",
        f"1 1 1 rg",
        f"400 {H-75} Td",
        f"({_esc(invoice.get('invoice_number','INV-0000'))}) Tj",
        "ET",
    ]

    # ── Info section ───────────────────────────────────────────────────────
    y = H - 170
    def label_value(label, value, x=40, yy=None):
        nonlocal y
        yy = yy if yy else y
        return [
            "BT", f"/F2 9 Tf", f"{_rg(MID)}",
            f"{x} {yy} Td", f"({_esc(label)}) Tj", "ET",
            "BT", f"/F1 10 Tf", f"{_rg(NAVY)}",
            f"{x} {yy-13} Td", f"({_esc(value)}) Tj", "ET",
        ]

    lines += label_value("BILL TO",        booking.get("client_name","-"))
    lines += label_value("",               booking.get("client_company",""), yy=y-13)
    lines += label_value("",               booking.get("client_email",""), yy=y-26)
    y -= 15

    lines += label_value("INVOICE DATE",   invoice.get("issued_date","-")[:10], x=350, yy=H-170)
    lines += label_value("DUE DATE",       invoice.get("due_date","-")[:10] if invoice.get("due_date") else "On receipt", x=350, yy=H-197)

    paid_status = invoice.get("status","unpaid").upper()
    status_color = "1B6B3A" if paid_status == "PAID" else ("C0531A" if paid_status == "OVERDUE" else NAVY)
    lines += [
        "BT", f"/F2 11 Tf", f"{_rg(status_color)}",
        f"350 {H-225} Td", f"(Status: {_esc(paid_status)}) Tj", "ET",
    ]

    # ── Table header ──────────────────────────────────────────────────────
    table_y = H - 300
    lines += [
        f"{_rg(NAVY)}",
        f"40 {table_y} {W-80} 28 re f",
        "BT", "/F2 9 Tf", "1 1 1 rg",
        f"50 {table_y+10} Td", "(DESCRIPTION) Tj", "ET",
        "BT", "/F2 9 Tf", "1 1 1 rg",
        f"300 {table_y+10} Td", "(PAX) Tj", "ET",
        "BT", "/F2 9 Tf", "1 1 1 rg",
        f"360 {table_y+10} Td", "(UNIT PRICE) Tj", "ET",
        "BT", "/F2 9 Tf", "1 1 1 rg",
        f"470 {table_y+10} Td", "(AMOUNT) Tj", "ET",
    ]

    # ── Table row ─────────────────────────────────────────────────────────
    row_y = table_y - 35
    pax      = booking.get("pax_count", 1)
    unit_lkr = (invoice.get("subtotal",0) // max(pax,1))
    total    = invoice.get("total_amount", 0)

    prog_name = programme.get("name","Training Programme") if programme else "Training Programme"
    ws_date   = workshop.get("start_datetime","")[:10] if workshop else ""
    desc      = f"{_esc(prog_name)} - {_esc(ws_date)}"

    lines += [
        f"{_rg(LIGHT)}",
        f"40 {row_y-8} {W-80} 30 re f",
        "BT", f"/F1 9 Tf", f"{_rg(NAVY)}",
        f"50 {row_y+4} Td", f"({desc}) Tj", "ET",
        "BT", f"/F1 9 Tf", f"{_rg(NAVY)}",
        f"310 {row_y+4} Td", f"({pax}) Tj", "ET",
        "BT", f"/F1 9 Tf", f"{_rg(NAVY)}",
        f"360 {row_y+4} Td", f"(LKR {unit_lkr:,}) Tj", "ET",
        "BT", f"/F1 9 Tf", f"{_rg(NAVY)}",
        f"460 {row_y+4} Td", f"(LKR {invoice.get('subtotal',0):,}) Tj", "ET",
    ]

    # ── Totals box ────────────────────────────────────────────────────────
    tot_y = row_y - 80
    tax   = invoice.get("tax_amount", 0)
    lines += [
        # Subtotal
        "BT", f"/F1 10 Tf", f"{_rg(MID)}",
        f"360 {tot_y+40} Td", f"(Subtotal) Tj", "ET",
        "BT", f"/F1 10 Tf", f"{_rg(NAVY)}",
        f"460 {tot_y+40} Td", f"(LKR {invoice.get('subtotal',0):,}) Tj", "ET",
        # Tax
        "BT", f"/F1 10 Tf", f"{_rg(MID)}",
        f"360 {tot_y+22} Td", f"(VAT (0%)) Tj", "ET",
        "BT", f"/F1 10 Tf", f"{_rg(NAVY)}",
        f"460 {tot_y+22} Td", f"(LKR {tax:,}) Tj", "ET",
        # Divider
        f"0.8 0.8 0.8 RG", f"360 {tot_y+16} m {W-40} {tot_y+16} l S",
        # Total
        f"{_rg(NAVY)}", f"360 {tot_y-4} {W-40-360} 28 re f",
        "BT", "/F2 10 Tf", "1 1 1 rg",
        f"370 {tot_y+6} Td", f"(TOTAL DUE) Tj", "ET",
        "BT", "/F2 11 Tf", f"{_rg(GOLD)}",
        f"460 {tot_y+6} Td", f"(LKR {total:,}) Tj", "ET",
    ]

    # ── Payment instructions ───────────────────────────────────────────────
    pay_y = tot_y - 80
    lines += [
        f"{_rg(TEAL)}", f"40 {pay_y+30} 4 50 re f",  # Left accent bar
        "BT", "/F2 10 Tf", f"{_rg(NAVY)}",
        f"52 {pay_y+60} Td", f"(PAYMENT DETAILS) Tj", "ET",
        "BT", "/F1 9 Tf", f"{_rg(MID)}",
        f"52 {pay_y+44} Td", f"(Bank: Commercial Bank of Ceylon) Tj", "ET",
        "BT", "/F1 9 Tf", f"{_rg(MID)}",
        f"52 {pay_y+30} Td", f"(Account: GenBridge Corporate Training Solutions (Pvt) Ltd) Tj", "ET",
        "BT", "/F1 9 Tf", f"{_rg(MID)}",
        f"52 {pay_y+16} Td", f"(Account No: 1234-5678-9012  |  Branch: Colombo 3) Tj", "ET",
        "BT", "/F1 9 Tf", f"{_rg(MID)}",
        f"52 {pay_y+2} Td", f"(Please use invoice number as payment reference.) Tj", "ET",
    ]

    # ── Footer ────────────────────────────────────────────────────────────
    lines += [
        f"{_rg(NAVY)}", f"0 0 {W} 40 re f",
        "BT", "/F1 8 Tf", "1 1 1 rg",
        f"40 18 Td", f"(GenBridge Corporate Training Solutions (Pvt) Ltd  |  Colombo 3, Sri Lanka  |  info@genbridge.lk  |  +94 11 234 5678) Tj",
        "ET",
        "BT", "/F1 8 Tf", f"{_rg(GOLD)}",
        f"40 8 Td", f"(www.genbridge.lk  |  Business Reg. No. PV 12345678) Tj",
        "ET",
    ]

    stream = _stream(*lines)
    pdf = PDF()
    pdf.add_page(stream)
    return pdf.save()
