"""個人記帳 Web 應用"""
import sqlite3
import os
import json
import re
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


@app.route("/vco")
def vco():
    resp = send_from_directory(".", "lc_vco.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/analyze", methods=["POST"])
def analyze():
    api_key = os.environ.get("GROQ_API_KEY", "")
    prompt = request.json.get("prompt", "").strip()

    if not api_key:
        return jsonify({"error": "伺服器未設定 API Key"}), 500
    if not prompt:
        return jsonify({"error": "缺少 prompt"}), 400

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": 3000,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        data = resp.json()
        if resp.status_code != 200:
            return jsonify({"error": f"Groq {resp.status_code}: {data.get('error', {}).get('message', resp.text[:200])}"}), 500
        content = data["choices"][0]["message"]["content"]
        return jsonify({"result": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/vco-schematic", methods=["POST"])
def vco_schematic():
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return jsonify({"error": "伺服器未設定 GROQ_API_KEY"}), 500

    data = request.json or {}
    img_data = data.get("image", "")
    if not img_data:
        return jsonify({"error": "缺少圖片"}), 400

    # 確保是完整 data URL 格式
    if not img_data.startswith("data:"):
        img_data = "data:image/png;base64," + img_data

    prompt = (
        "分析這張 LC-VCO ADS 電路架構圖，萃取所有元件參數。\n"
        "ADS 中被紅色虛線框住的元件是 deactivated（停用），active 填 false。\n"
        "注意：d1、d2 等小寫字母加數字的名稱是 ADS 節點名稱，不是元件，不要放入任何陣列。\n"
        "元件名稱格式：電容以 C 開頭、電阻以 R 開頭、電感以 L 開頭、電晶體以 M 開頭。\n"
        "ADS 電晶體顯示 lr=Y um 或 wr=X um 時，X/Y 是 parameter sweep 變數名稱，不是數值。\n"
        "PMOS 與 NMOS 的實際 lr 均為 0.35μm（TSMC 0.18um RF，此電路設計值）。wr 請從 nr 行旁邊讀取實際數字。\n"
        "只回傳 JSON，不要任何說明文字：\n"
        '{"topology":"complementary|nmos-only|pmos-only|other",'
        '"vdd":null,"vc_default":null,"vb_default":null,'
        '"transistors":[{"name":"","type":"NMOS|PMOS","wr":0,"lr":0,"nr":0,"w_total":0,"role":""}],'
        '"inductor":{"name":"","w":0,"rad":0,"nr":0,"lay":0},'
        '"varactors":[{"name":"C??","g":0,"b":0,"active":true}],'
        '"fixed_caps":[{"name":"C??","value_pF":0,"active":true}],'
        '"resistors":[{"name":"R??","value_kohm":0,"active":true}],'
        '"notes":""}'
    )

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "max_tokens": 1500,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": img_data}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            },
            timeout=60
        )
        rdata = resp.json()
        if resp.status_code != 200:
            return jsonify({"error": f"Groq {resp.status_code}: {rdata.get('error',{}).get('message', str(rdata)[:200])}"}), 500

        text = rdata["choices"][0]["message"]["content"].strip()
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return jsonify({"error": "無法解析回應", "raw": text[:400]}), 500

        circuit = json.loads(m.group())

        # 後處理：修正 AI 常見誤讀
        for t in circuit.get("transistors", []):
            # lr=Y 之類的 ADS sweep 變數會被誤讀成大數字，強制修正為 0.35
            if not isinstance(t.get("lr"), (int, float)) or t.get("lr", 0) > 1:
                t["lr"] = 0.35
            # w_total 重新計算，避免 AI 算錯
            wr = t.get("wr") or 0
            nr = t.get("nr") or 0
            if wr and nr:
                t["w_total"] = round(wr * nr, 3)
        # 過濾掉節點名稱（d1、d2 等不以字母 A-Z 開頭後跟數字的元件名）
        for key in ("varactors", "fixed_caps", "resistors"):
            circuit[key] = [x for x in circuit.get(key, []) if re.match(r'^[A-Za-z]\d', x.get("name", ""))]

        return jsonify({"circuit": circuit})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/vco-vision", methods=["POST"])
def vco_vision():
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return jsonify({"error": "伺服器未設定 GROQ_API_KEY"}), 500

    data = request.json or {}
    images = data.get("images", [])
    if not images:
        return jsonify({"error": "缺少圖片資料"}), 400

    content = []
    for img in images:
        raw = img.get("data", "")
        if not raw.startswith("data:"):
            raw = "data:image/png;base64," + raw
        content.append({"type": "image_url", "image_url": {"url": raw}})

    content.append({
        "type": "text",
        "text": (
            "你是類比電路分析助手，專門從 ADS SPICE 模擬截圖萃取 LC-VCO 參數。\n"
            "分析圖片（可能包含：Vc vs fout 調諧曲線、KVCO 曲線、相位雜訊圖、時域波形），萃取：\n"
            "fmin(GHz), fmax(GHz), f0(GHz), vc_min(V), kvco_min(MHz/V), vc_max(V), kvco_max(MHz/V),\n"
            "pn_offset(MHz), pn_val(dBc/Hz 負數), pn_vc(V), vpp(V), vdd(V)。\n"
            "僅回傳 JSON，無法確認的填 null：\n"
            '{"fmin":null,"fmax":null,"f0":null,"vc_min":null,"kvco_min":null,'
            '"vc_max":null,"kvco_max":null,"pn_offset":null,"pn_val":null,"pn_vc":null,'
            '"vpp":null,"vdd":null}'
        )
    })

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": content}]
            },
            timeout=60
        )
        rdata = resp.json()
        if resp.status_code != 200:
            return jsonify({"error": f"Groq {resp.status_code}: {rdata.get('error',{}).get('message', str(rdata)[:200])}"}), 500

        text = rdata["choices"][0]["message"]["content"].strip()
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            return jsonify({"params": json.loads(m.group())})
        return jsonify({"error": "無法解析 AI 回應", "raw": text[:400]}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
