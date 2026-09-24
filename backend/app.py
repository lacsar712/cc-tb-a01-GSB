import os
from functools import wraps

import psycopg2
from flask import Flask, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from rules import check_scale, weigh

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "tea-cupping-dev-secret")

ACCOUNTS = {
    "taster": {"password": "tea123456", "role": "writer"},
    "observer": {"password": "look123456", "role": "reader"},
}


def db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def login_required(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrap


@app.get("/health")
def health():
    return {"status": "ok", "service": "tea-blend-cupping"}


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        name = request.form.get("username", "").strip()
        account = ACCOUNTS.get(name)
        if not account or account["password"] != request.form.get("password", ""):
            error = "用户名或密码错误"
        else:
            session["user"] = name
            session["role"] = account["role"]
            return redirect(url_for("home"))
    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def home():
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM cuppings ORDER BY id DESC")
        rows = cur.fetchall()
    return render_template("home.html", rows=rows, can_write=session.get("role") == "writer")


@app.post("/cuppings")
@login_required
def create():
    if session.get("role") != "writer":
        return ("仅审评员可提交拼配审评", 403)
    lot = request.form["lot"].strip()
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT 1 FROM ratio_scales WHERE lot = %s", (lot,))
        if cur.fetchone() is None:
            return (f"批次「{lot}」缺比例尺，请先在比例尺页登记母叶占比", 409)
        aroma = float(request.form["aroma"])
        taste = float(request.form["taste"])
        liquor = float(request.form["liquor"])
        verdict, note, score = weigh(aroma, taste, liquor)
        cur.execute(
            """INSERT INTO cuppings (lot, aroma, taste, liquor, score, verdict, note, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (lot, aroma, taste, liquor, score, verdict, note, session["user"]),
        )
        row = cur.fetchone()
        conn.commit()
    if request.headers.get("HX-Request"):
        return render_template("_row.html", row=row)
    return redirect(url_for("home"))


@app.get("/scales")
@login_required
def scales():
    lot = request.args.get("lot", "").strip()
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT s.id AS scale_id, s.lot, i.leaf, i.percent
               FROM ratio_scales s
               LEFT JOIN ratio_items i ON i.scale_id = s.id
               ORDER BY s.lot, i.id"""
        )
        grouped = {}
        for r in cur.fetchall():
            scale = grouped.setdefault(
                r["lot"], {"id": r["scale_id"], "lot": r["lot"], "items": []}
            )
            if r["leaf"] is not None:
                scale["items"].append({"leaf": r["leaf"], "percent": r["percent"]})
    current = grouped.get(lot) if lot else None
    return render_template(
        "scales.html",
        lot=lot,
        current=current,
        scales=list(grouped.values()),
        can_write=session.get("role") == "writer",
    )


@app.post("/scales")
@login_required
def save_scale():
    if session.get("role") != "writer":
        return ("仅审评员可登记比例尺", 403)
    lot = request.form.get("lot", "").strip()
    if not lot:
        return ("批次不能为空", 400)
    pairs = list(zip(request.form.getlist("leaf"), request.form.getlist("percent")))
    items, error = check_scale(pairs)
    if error:
        return (error, 400)
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM ratio_scales WHERE lot = %s", (lot,))
        existing = cur.fetchone()
        if existing:
            scale_id = existing[0]
            cur.execute("DELETE FROM ratio_items WHERE scale_id = %s", (scale_id,))
        else:
            cur.execute(
                "INSERT INTO ratio_scales (lot, created_by) VALUES (%s, %s) RETURNING id",
                (lot, session["user"]),
            )
            scale_id = cur.fetchone()[0]
        for leaf, percent in items:
            cur.execute(
                "INSERT INTO ratio_items (scale_id, leaf, percent) VALUES (%s, %s, %s)",
                (scale_id, leaf, percent),
            )
        conn.commit()
    return redirect(url_for("scales", lot=lot))


@app.post("/scales/<int:scale_id>/delete")
@login_required
def delete_scale(scale_id):
    if session.get("role") != "writer":
        return ("仅审评员可删除比例尺", 403)
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ratio_scales WHERE id = %s", (scale_id,))
        conn.commit()
    return redirect(url_for("scales"))
