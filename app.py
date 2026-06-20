"""個人記帳 Web 應用"""
import sqlite3
import os
import json
import requests
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, send_from_directory

app = Flask(__name__)
DB_PATH = "ledger.db"

CATEGORIES = ["餐飲", "交通", "購物", "娛樂", "醫療", "住房", "薪資", "投資", "其他"]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            date     TEXT    NOT NULL,
            type     TEXT    NOT NULL CHECK(type IN ('收入','支出')),
            amount   REAL    NOT NULL CHECK(amount > 0),
            category TEXT    NOT NULL DEFAULT '其他',
            note     TEXT    DEFAULT ''
        )
    """)
    conn.commit()
    return conn


@app.route("/")
def index():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    type_filter = request.args.get("type", "")

    with get_conn() as conn:
        # 交易列表
        query = "SELECT * FROM transactions WHERE date LIKE ?"
        params = [f"{month}%"]
        if type_filter:
            query += " AND type = ?"
            params.append(type_filter)
        query += " ORDER BY date DESC, id DESC"
        rows = conn.execute(query, params).fetchall()

        # 本月統計
        stats = conn.execute("""
            SELECT type, SUM(amount) as total
            FROM transactions WHERE date LIKE ?
            GROUP BY type
        """, (f"{month}%",)).fetchall()

        # 分類統計（圓餅圖用）
        cat_stats = conn.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions WHERE date LIKE ? AND type='支出'
            GROUP BY category ORDER BY total DESC
        """, (f"{month}%",)).fetchall()

    income  = next((r["total"] for r in stats if r["type"] == "收入"), 0)
    expense = next((r["total"] for r in stats if r["type"] == "支出"), 0)
    balance = income - expense

    return render_template("index.html",
        rows=rows, month=month, type_filter=type_filter,
        income=income, expense=expense, balance=balance,
        cat_stats=cat_stats, categories=CATEGORIES,
        today=date.today().isoformat()
    )


@app.route("/add", methods=["POST"])
def add():
    amount   = float(request.form["amount"])
    type_    = request.form["type"]
    category = request.form["category"]
    note     = request.form.get("note", "")
    day      = request.form.get("date") or date.today().isoformat()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO transactions (date, type, amount, category, note) VALUES (?,?,?,?,?)",
            (day, type_, amount, category, note)
        )
    month = day[:7]
    return redirect(url_for("index", month=month))


@app.route("/delete/<int:id_>", methods=["POST"])
def delete(id_):
    month = request.form.get("month", date.today().strftime("%Y-%m"))
    with get_conn() as conn:
        conn.execute("DELETE FROM transactions WHERE id=?", (id_,))
    return redirect(url_for("index", month=month))


@app.route("/career")
def career():
    return send_from_directory(".", "career_analyzer.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    api_key = os.environ.get("GROQ_API_KEY", "")
    prompt = request.json.get("prompt", "").strip()

    if not api_key:
        return jsonify({"error": "伺服器未設定 API Key"}), 500
    if not prompt:
        return jsonify({"error": "缺少 prompt"}), 400

    def stream():
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 2000,
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            },
            stream=True,
            timeout=120,
        )
        for line in resp.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    yield decoded + "\n"

    return Response(stream(), content_type="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
