from flask import Flask, render_template, request, redirect, send_file
from datetime import datetime
import pytz
import psycopg2
import psycopg2.extras
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
import os

app = Flask(__name__)

# ✅ CONNECT TO POSTGRES
def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

# ✅ INIT DB
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id SERIAL PRIMARY KEY,
            created_at TEXT,
            updated_at TEXT,
            submitted_by TEXT,
            terminal TEXT,
            category TEXT,
            priority TEXT,
            status TEXT,
            title TEXT,
            notes TEXT,
            archived INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# 🔥 WORD WRAP (UNCHANGED)
def wrap_text(text, max_width, font, size):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = current + (" " if current else "") + word
        if stringWidth(test, font, size) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines

# ✅ INDEX
@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT * FROM entries
        WHERE archived = 0
        ORDER BY terminal, created_at DESC
    """)
    entries = cur.fetchall()

    cur.close()
    conn.close()
    return render_template("index.html", entries=entries)

# ✅ ADD
@app.route("/add", methods=["POST"])
def add():
    conn = get_db()
    cur = conn.cursor()

    tz = pytz.timezone("America/Los_Angeles")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    cur.execute("""
        INSERT INTO entries
        (created_at, updated_at, submitted_by, terminal, category, priority, status, title, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        now, now,
        request.form.get("submitted_by"),
        request.form.get("terminal"),
        request.form.get("category"),
        request.form.get("priority"),
        request.form.get("status"),
        request.form.get("title"),
        request.form.get("notes")
    ))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")

# ✅ EDIT
@app.route("/edit/<int:id>", methods=["POST"])
def edit(id):
    conn = get_db()
    cur = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    cur.execute("""
        UPDATE entries
        SET submitted_by=%s, terminal=%s, category=%s, priority=%s,
            status=%s, title=%s, notes=%s, updated_at=%s
        WHERE id=%s
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
    cur.close()
    conn.close()
    return redirect("/")

# ✅ DELETE
@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM entries WHERE id=%s", (id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/")

# ✅ ARCHIVES
@app.route("/archives")
def archives():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    search = request.args.get("search", "")
    terminal = request.args.get("terminal", "")
    priority = request.args.get("priority", "")
    date_filter = request.args.get("date", "")

    query = "SELECT * FROM entries WHERE archived=1"
    params = []

    if search:
        query += " AND (title ILIKE %s OR notes ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]

    if terminal:
        query += " AND terminal=%s"
        params.append(terminal)

    if priority:
        query += " AND priority=%s"
        params.append(priority)

    if date_filter:
        if date_filter == "7":
            query += " AND created_at >= NOW() - INTERVAL '7 days'"
        elif date_filter == "30":
            query += " AND created_at >= NOW() - INTERVAL '30 days'"
        elif date_filter == "90":
            query += " AND created_at >= NOW() - INTERVAL '90 days'"

    query += " ORDER BY created_at DESC"

    cur.execute(query, params)
    entries = cur.fetchall()

    cur.close()
    conn.close()
    return render_template("archives.html", entries=entries)

# ✅ RESTORE
@app.route("/restore/<int:id>", methods=["POST"])
def restore(id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE entries
        SET archived=0, status='Ongoing'
        WHERE id=%s
    """, (id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/archives")

# 🔥 PDF (YOUR VERSION — FIXED FOOTER OVERLAP)
@app.route("/generate-pdf")
def generate_pdf():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT * FROM entries
        ORDER BY terminal, created_at DESC
    """)
    entries = cur.fetchall()

    cur.close()

    file_path = "passdown_report.pdf"
    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    def draw_header():
        c.setFillColorRGB(0.0, 0.45, 0.65)
        c.rect(0, 760, width, 40, fill=1)

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

    terminals = {}
    for e in entries:
        terminals.setdefault(e["terminal"], []).append(e)

    y = 740
    page_num = 1
    draw_header()

    for terminal, items in terminals.items():

        if y < 140:
            draw_footer(page_num)
            c.showPage()
            page_num += 1
            draw_header()
            y = 740

        c.setFillColorRGB(0.85, 0.92, 0.96)
        c.roundRect(50, y - 20, 500, 20, 6, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y - 15, terminal)

        y -= 30

        for e in items:
            lines = wrap_text(e["notes"] or "", 400, "Helvetica", 9)

            line_height = 10
            card_height = 65 + (len(lines) * line_height)

            if y - card_height < 140:
                draw_footer(page_num)
                c.showPage()
                page_num += 1
                draw_header()
                y = 740

            c.setFillColorRGB(0.96, 0.96, 0.96)
            c.roundRect(50, y - card_height, 500, card_height, 8, fill=1)

            r, g, b = priority_color(e["priority"])
            c.setFillColorRGB(r, g, b)
            c.rect(50, y - card_height, 6, card_height, fill=1)

            c.setFillColorRGB(0, 0, 0)

            c.setFont("Helvetica-Bold", 11)
            c.drawString(65, y - 18, e["title"] or "Untitled")

            c.setFont("Helvetica-Oblique", 9)
            c.drawString(65, y - 32, e["category"] or "")

            c.setFont("Helvetica", 9)
            text_y = y - 45
            for line in lines:
                c.drawString(65, text_y, line)
                text_y -= line_height

            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(540, y - 18, f"{e['priority']} | {e['status']}")

            c.setFont("Helvetica-Oblique", 8)
            c.setFillColorRGB(0.3, 0.3, 0.3)

            c.drawCentredString(
                width / 2,
                y - card_height + 12,
                f"Submitted by: {e['submitted_by'] or 'N/A'} | Last Modified: {e['updated_at'] or ''}"
            )

            y -= (card_height + 15)

    draw_footer(page_num)
    c.save()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE entries SET archived=1 WHERE status='Resolved'")
    conn.commit()
    cur.close()
    conn.close()

    return send_file(file_path, as_attachment=True)

# INIT
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
