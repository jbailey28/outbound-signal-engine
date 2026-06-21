#!/usr/bin/env python3
"""Generate a synthetic Salesforce-like Printable-View PDF for demos/tests.

This produces a table with the same columns a real Salesforce Printable View
exports, using entirely fictional accounts. Run once to (re)create the bundled
sample:

    python tests/make_sample_pdf.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

OUT = Path(__file__).resolve().parent.parent / "data" / "sample" / "sample_accounts.pdf"

HEADER = ["Account Name", "Website", "Competitors", "Industry", "Sub-Industry"]

# Fictional accounts. Note the deliberate messiness we want the parser to survive:
#   - mixed-case / www / paths / query strings in URLs
#   - a near-duplicate (different URL formatting, same domain)
#   - a row with no website (forces name-key fallback)
ROWS = [
    ["Acme Retail, Inc.", "https://www.acmeretail.com/affiliates", "PartnerStack", "Retail", "Apparel"],
    ["Globex Corporation", "globex.co.uk", "impact.com", "Technology", "SaaS"],
    ["Initech LLC", "HTTP://Initech.com/partners?utm=x", "Awin", "Technology", "Fintech"],
    ["Umbrella Health", "shop.umbrellahealth.com", "CJ Affiliate", "Healthcare", "Wellness"],
    ["Acme Retail", "acmeretail.com", "PartnerStack", "Retail", "Apparel"],  # dup of row 1
    ["Wayne Enterprises", "", "Rakuten", "Industrials", "Manufacturing"],     # no website
    ["Soylent Foods", "www.soylentfoods.com.au", "", "Consumer Goods", "Food & Beverage"],
]


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT), pagesize=landscape(letter),
                            title="Accounts - Printable View")
    data = [HEADER] + ROWS
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0070d2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6f9")]),
    ]))
    title = Paragraph("Accounts", styles["Title"])
    doc.build([title, table])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
