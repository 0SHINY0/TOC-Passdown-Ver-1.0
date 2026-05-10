from flask import Flask, render_template, request, redirect, send_file
from datetime import datetime
import sqlite3
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

app = Flask(__name__)
DB_NAME = "passdown.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            updated_at TEXT,
            submitted_by TEXT,
            terminal TEXT,
            category TEXT,
            priority TEXT,
            status TEXT,
            title TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()

@app.route("/")
def index():
    conn = get_db()
    entries = conn.execute("""
        SELECT * FROM entries
        ORDER BY terminal, created_at DESC
    """).fetchall()
    conn.close()
    return render_template("index.html", entries=entries)

@app.route("/add", methods=["POST"])
def add():
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute("""
        INSERT INTO entries
        (created_at, updated_at, submitted_by, terminal, category, priority, status, title, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now,
        now,
        request.form.get("submitted_by"),
        request.form.get("terminal"),
        request.form.get("category"),
        request.form.get("priority"),
        request.form.get("status"),
        request.form.get("title"),
        request.form.get("notes")
    ))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/edit/<int:id>", methods=["POST"])
def edit(id):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute("""
        UPDATE entries
        SET submitted_by=?, terminal=?, category=?, priority=?, status=?, title=?, notes=?, updated_at=?
        WHERE id=?
    """, (
        request.form.get("submitted_by"),
        request.form.get("terminal"),
        request.form.get("category"),
        request.form.get("priority"),
        request.form.get("status"),
        request.form.get("title"),
        request.form.get("notes"),
        now,
        id
    ))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    conn = get_db()
    conn.execute("DELETE FROM entries WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

# ✅ PDF BACK (FIXED)
@app.route("/generate-pdf")
def generate_pdf():
    conn = get_db()
    entries = conn.execute("""
        SELECT * FROM entries 
        ORDER BY terminal, created_at DESC
    """).fetchall()

    file_path = "passdown_report.pdf"
    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    def draw_header():
        # 🔷 HEADER BAR
        c.setFillColorRGB(0.0, 0.45, 0.65)
        c.rect(0, 760, width, 40, fill=1, stroke=0)

        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 775, "TOC PASSDOWN REPORT")

        c.setFont("Helvetica", 9)
        c.drawRightString(width - 50, 775, datetime.now().strftime("%Y-%m-%d %H:%M"))

    def draw_footer(page_num):
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawCentredString(width / 2, 20, f"Page {page_num}")

    def priority_color(priority):
        return {
            "FYI": (0.17, 0.72, 0.45),
            "Low": (0.5, 0.5, 0.5),
            "Medium": (0.2, 0.6, 1),
            "High": (1, 0.6, 0),
            "Urgent": (0.85, 0, 0)
        }.get(priority, (0.5, 0.5, 0.5))

    # GROUP BY TERMINAL
    terminals = {}
    for e in entries:
        terminals.setdefault(e["terminal"], []).append(e)

    y = 740
    page_num = 1
    draw_header()

    for terminal, items in terminals.items():

        if y < 120:
            draw_footer(page_num)
            c.showPage()
            page_num += 1
            draw_header()
            y = 740

        # 🔷 TERMINAL HEADER
        c.setFillColorRGB(0.85, 0.92, 0.96)
        c.roundRect(50, y - 20, 500, 20, 6, fill=1, stroke=0)

        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y - 15, terminal)

        y -= 30

        for e in items:

            if y < 120:
                draw_footer(page_num)
                c.showPage()
                page_num += 1
                draw_header()
                y = 740

            # CARD BACKGROUND
            c.setFillColorRGB(0.96, 0.96, 0.96)
            c.roundRect(50, y - 70, 500, 70, 8, fill=1, stroke=0)

            # LEFT PRIORITY BAR
            r, g, b = priority_color(e["priority"])
            c.setFillColorRGB(r, g, b)
            c.rect(50, y - 70, 6, 70, fill=1, stroke=0)

            # TEXT RESET
            c.setFillColorRGB(0, 0, 0)

            # TITLE
            c.setFont("Helvetica-Bold", 11)
            c.drawString(65, y - 18, e["title"] or "Untitled")

            # CATEGORY
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(65, y - 32, e["category"] or "")

            # NOTES (WRAP MANUALLY)
            notes = (e["notes"] or "")
            lines = []
            while len(notes) > 80:
                lines.append(notes[:80])
                notes = notes[80:]
            lines.append(notes)

            c.setFont("Helvetica", 9)
            text_y = y - 45
            for line in lines[:2]:  # limit to 2 lines
                c.drawString(65, text_y, line)
                text_y -= 10

            # RIGHT SIDE BADGE
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(540, y - 18, f"{e['priority']} | {e['status']}")

            # FOOTER (BOTTOM CENTER)
            c.setFont("Helvetica-Oblique", 8)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            
            submitted_by = e["submitted_by"] if "submitted_by" in e.keys() and e["submitted_by"] else "N/A"
            updated_at = e["updated_at"] if "updated_at" in e.keys() and e["updated_at"] else ""
            c.drawCentredString(
                width / 2,
                y - 60,
                f"Submitted by: {submitted_by} | Last Modified: {updated_at}"
            )

            y -= 85

    draw_footer(page_num)
    c.save()

    # ✅ REMOVE RESOLVED
    conn.execute("DELETE FROM entries WHERE status='Resolved'")
    conn.commit()
    conn.close()

    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)