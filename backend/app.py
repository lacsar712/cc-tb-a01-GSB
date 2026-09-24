import os
from functools import wraps

import psycopg2
from flask import Flask, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from rules import validate_scale, weigh

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
    aroma = float(request.form["aroma"])
    taste = float(request.form["taste"])
    liquor = float(request.form["liquor"])
    lot = request.form["lot"].strip()
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 未挂母叶比例尺的批次直接拒交
        cur.execute("SELECT 1 FROM blend_scales WHERE lot = %s", (lot,))
        if cur.fetchone() is None:
            return (f"批次 {lot} 缺母叶比例尺，先挂比例尺再交审评", 400)
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
    """比例尺页：可按批次查当前占比表（观察员只读）。"""
    selected = (request.args.get("lot") or "").strip()
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT lot FROM blend_scales ORDER BY lot")
        lots = [r["lot"] for r in cur.fetchall()]
        scale = None
        if selected:
            cur.execute(
                """SELECT s.lot, s.created_by, l.leaf, l.percent
                     FROM blend_scales s
                     JOIN blend_leaves l ON l.scale_id = s.id
                    WHERE s.lot = %s ORDER BY l.id""",
                (selected,),
            )
            rows = cur.fetchall()
            if rows:
                scale = {
                    "lot": rows[0]["lot"],
                    "created_by": rows[0]["created_by"],
                    "leaves": [(r["leaf"], float(r["percent"])) for r in rows],
                }
    error = request.args.get("error", "")
    return render_template(
        "scales.html",
        lots=lots,
        selected=selected,
        scale=scale,
        error=error,
        can_write=session.get("role") == "writer",
    )


def _read_leaves_from_form():
    names = request.form.getlist("leaf")
    percents = request.form.getlist("percent")
    return list(zip(names, percents))


@app.post("/scales/register")
@login_required
def register_scale():
    if session.get("role") != "writer":
        return ("仅审评员可登记母叶比例尺", 403)
    lot = request.form.get("lot", "").strip()
    if not lot:
        return redirect(url_for("scales", error="批次不能为空"))
    leaves, error = validate_scale(_read_leaves_from_form())
    if error:
        return redirect(url_for("scales", lot=lot, error=error))
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """INSERT INTO blend_scales (lot, created_by) VALUES (%s,%s)
               ON CONFLICT (lot) DO NOTHING RETURNING id""",
            (lot, session["user"]),
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return redirect(url_for("scales", lot=lot, error=f"批次 {lot} 已挂比例尺，请直接修改"))
        scale_id = row["id"]
        cur.executemany(
            "INSERT INTO blend_leaves (scale_id, leaf, percent) VALUES (%s,%s,%s)",
            [(scale_id, leaf, percent) for leaf, percent in leaves],
        )
        conn.commit()
    return redirect(url_for("scales", lot=lot))


@app.post("/scales/update")
@login_required
def update_scale():
    if session.get("role") != "writer":
        return ("仅审评员可修改母叶占比", 403)
    lot = request.form.get("lot", "").strip()
    leaves, error = validate_scale(_read_leaves_from_form())
    if error:
        return redirect(url_for("scales", lot=lot, error=error))
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM blend_scales WHERE lot = %s FOR UPDATE", (lot,))
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return redirect(url_for("scales", lot=lot, error=f"批次 {lot} 还没有比例尺"))
        scale_id = row["id"]
        cur.execute("DELETE FROM blend_leaves WHERE scale_id = %s", (scale_id,))
        cur.executemany(
            "INSERT INTO blend_leaves (scale_id, leaf, percent) VALUES (%s,%s,%s)",
            [(scale_id, leaf, percent) for leaf, percent in leaves],
        )
        conn.commit()
    return redirect(url_for("scales", lot=lot))


@app.post("/scales/delete")
@login_required
def delete_scale():
    if session.get("role") != "writer":
        return ("仅审评员可删除母叶比例尺", 403)
    lot = request.form.get("lot", "").strip()
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM blend_scales WHERE lot = %s", (lot,))
        conn.commit()
    return redirect(url_for("scales"))

