import io, os, sqlite3, sys, time
from datetime import datetime
from flask import Flask, request, jsonify, send_file, g
from mtparse import parse

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, "frozen", False):  # chạy dạng .app: dữ liệu để ngoài bundle, không mất khi cập nhật app
    DATA = os.path.expanduser("~/Library/Application Support/TradingJournal"); os.makedirs(DATA, exist_ok=True)
else:
    DATA = BASE
app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")
DB = os.path.join(DATA, "journal.db")
DEFAULTS = {"balance": 1000, "risk_pct": 0.5, "dl_pct": 2, "max_trades": 3}
SCHEMA = """CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, key TEXT UNIQUE, ts TEXT, ticket TEXT, symbol TEXT,
 account_id INTEGER NOT NULL DEFAULT 1, side TEXT, volume REAL, profit REAL, risk REAL, ok INTEGER DEFAULT 1, emo_before TEXT DEFAULT '', emo_after TEXT DEFAULT '',
 vio TEXT DEFAULT '', note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, broker TEXT DEFAULT '', currency TEXT DEFAULT 'USD',
 balance REAL DEFAULT 1000, risk_pct REAL DEFAULT 0.5, dl_pct REAL DEFAULT 2, max_trades REAL DEFAULT 3, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v REAL);"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def account_id(value=None):
    try: aid = int(value or 1)
    except (TypeError, ValueError): aid = 1
    if not db().execute("SELECT 1 FROM accounts WHERE id=?", (aid,)).fetchone(): aid = 1
    return aid

def settings(aid=1):
    r = db().execute("SELECT balance,risk_pct,dl_pct,max_trades FROM accounts WHERE id=?", (account_id(aid),)).fetchone()
    return dict(r) if r else dict(DEFAULTS)

@app.get("/")
@app.get("/index.html")
def home(): return app.send_static_file("index.html")

@app.get("/health")
def health(): return jsonify(ok=True)

@app.get("/api/accounts")
def api_accounts():
    return jsonify([dict(r) for r in db().execute("SELECT * FROM accounts ORDER BY id")])

@app.post("/api/accounts")
def api_account_create():
    data = request.get_json() or {}; name = str(data.get("name", "")).strip()
    if not name: return jsonify(error="Tên account không được để trống."), 400
    c = db(); cur = c.execute("INSERT INTO accounts(name,risk_pct) VALUES(?,0.5)", (name,)); c.commit()
    return jsonify(dict(c.execute("SELECT * FROM accounts WHERE id=?", (cur.lastrowid,)).fetchone())), 201

@app.route("/api/settings", methods=["GET", "PUT"])
def api_settings():
    aid = account_id(request.args.get("account_id"))
    if request.method == "PUT":
        for k, v in request.get_json().items():
            if k in DEFAULTS: db().execute(f"UPDATE accounts SET {k}=? WHERE id=?", (float(v), aid))
        db().commit()
    return jsonify(settings(aid))

@app.post("/api/import")
def api_import():
    aid = account_id(request.form.get("account_id"))
    f = request.files.get("file")
    if not f: return jsonify(error="Chưa chọn file."), 400
    try: res = parse(f.read())
    except Exception as e: return jsonify(error=f"Không đọc được file: {e}"), 400
    s = settings(aid)
    try: user_base = float(str(request.form.get("initial_balance", "")).replace(",", ""))
    except (TypeError, ValueError): user_base = 0
    try: user_risk_pct = float(str(request.form.get("risk_pct", "")).replace(",", "."))
    except (TypeError, ValueError): user_risk_pct = 0
    base = user_base if user_base > 0 else (res.get("initial_balance") or s["balance"])
    risk_pct = user_risk_pct if user_risk_pct > 0 else s["risk_pct"]
    risk = base * risk_pct / 100
    res["initial_balance"] = base
    res["risk"] = risk
    res["risk_pct"] = risk_pct
    if request.form.get("commit") != "1":
        res["count"] = len(res["trades"]); res["trades"] = res["trades"][:300]; return jsonify(res)
    db().execute("UPDATE accounts SET balance=? WHERE id=?", (base, aid))
    added = dup = 0
    for t in res["trades"]:
        try:
            db().execute("INSERT INTO trades(key,account_id,ts,ticket,symbol,side,volume,profit,risk) VALUES(?,?,?,?,?,?,?,?,?)",
                         (f"{aid}:{t['key']}", aid, t["ts"], t["ticket"], t["symbol"], t["side"], t["volume"], t["profit"], risk)); added += 1
        except sqlite3.IntegrityError: dup += 1
    db().commit(); return jsonify(added=added, dup=dup, initial_balance=base, risk=risk)

@app.get("/api/trades")
def api_trades():
    aid = account_id(request.args.get("account_id"))
    return jsonify([dict(r) for r in db().execute("SELECT * FROM trades WHERE account_id=? ORDER BY ts, id", (aid,))])

@app.post("/api/trades")
def api_trade_create():
    aid = account_id(request.args.get("account_id"))
    data = request.get_json() or {}
    symbol = str(data.get("symbol", "")).strip()
    if not symbol: return jsonify(error="Symbol không được để trống."), 400
    try:
        volume = float(data.get("volume", 0)); profit = float(data.get("profit", 0))
        risk = float(data.get("risk") or settings(aid)["balance"] * settings(aid)["risk_pct"] / 100)
    except (TypeError, ValueError): return jsonify(error="Lot, lãi/lỗ và rủi ro phải là số."), 400
    ts = str(data.get("ts") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).replace("T", " ")[:19]
    side = "Sell" if str(data.get("side", "Buy")).lower() == "sell" else "Buy"
    key = f"manual:{aid}:{time.time_ns()}"
    c = db(); cur = c.execute("INSERT INTO trades(key,account_id,ts,ticket,symbol,side,volume,profit,risk) VALUES(?,?,?,?,?,?,?,?,?)",
                              (key, aid, ts, "manual", symbol, side, volume, profit, risk)); c.commit()
    return jsonify(ok=True, id=cur.lastrowid)

@app.route("/api/trades/<int:i>", methods=["PATCH", "DELETE"])
def api_trade(i):
    if request.method == "DELETE": db().execute("DELETE FROM trades WHERE id=?", (i,))
    else:
        for k, v in request.get_json().items():
            if k in ("ok", "emo_before", "emo_after", "vio", "note", "risk"):
                db().execute(f"UPDATE trades SET {k}=? WHERE id=?", (v, i))
    db().commit(); return jsonify(ok=True)

@app.delete("/api/trades")
def api_clear():
    aid = account_id(request.args.get("account_id"))
    db().execute("DELETE FROM trades WHERE account_id=?", (aid,)); db().commit(); return jsonify(ok=True)

@app.get("/api/export.xlsx")
def export():
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font
    wb = Workbook(); ws = wb.active; ws.title = "Nhật ký"
    ws.append(["Thời gian", "Ticket", "Symbol", "Hướng", "Lot", "Lãi/lỗ $", "Rủi ro $", "R", "Đúng setup", "Cảm xúc trước", "Cảm xúc sau", "Vi phạm", "Ghi chú"])
    for c in ws[1]: c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="F5C65A")
    aid = account_id(request.args.get("account_id"))
    for r in db().execute("SELECT * FROM trades WHERE account_id=? ORDER BY ts, id", (aid,)):
        ws.append([r["ts"], r["ticket"], r["symbol"], r["side"], r["volume"], r["profit"], r["risk"],
                   round(r["profit"] / r["risk"], 2) if r["risk"] else None, "Có" if r["ok"] else "Không",
                   r["emo_before"], r["emo_after"], r["vio"], r["note"]])
        fill = PatternFill("solid", fgColor="E5F3EA" if r["profit"] > 0 else "FBE9E7")
        for c in ws[ws.max_row]: c.fill = fill
    for col, w in zip("ABCDEFGHIJKLM", (20, 12, 10, 8, 8, 10, 10, 7, 11, 14, 14, 24, 30)): ws.column_dimensions[col].width = w
    b = io.BytesIO(); wb.save(b); b.seek(0)
    return send_file(b, as_attachment=True, download_name="nhat-ky-giao-dich.xlsx")

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(trades)")}
        if "account_id" not in cols: c.execute("ALTER TABLE trades ADD COLUMN account_id INTEGER NOT NULL DEFAULT 1")
        if not c.execute("SELECT 1 FROM accounts WHERE id=1").fetchone():
            legacy = {r["k"]: r["v"] for r in c.execute("SELECT k,v FROM settings")}
            c.execute("INSERT INTO accounts(id,name,balance,risk_pct,dl_pct,max_trades) VALUES(1,?,?,?,?,?)",
                      ("Main Account", legacy.get("balance", 1000), legacy.get("risk_pct", 0.5), legacy.get("dl_pct", 2), legacy.get("max_trades", 3)))
        # Chuyển giá trị mặc định cũ của Main Account từ 1% sang 0.5%.
        c.execute("UPDATE accounts SET risk_pct=0.5 WHERE id=1 AND risk_pct=1")
        c.execute("UPDATE trades SET account_id=1 WHERE account_id IS NULL")

init_db()
def main(port=5001):
    import socket, threading, time, webbrowser, urllib.request

    def responds(p):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/health", timeout=0.4) as r:
                return r.status == 200
        except Exception:
            return False

    # Chỉ dùng lại port nếu đúng là Trading Journal đang chạy; tránh mở nhầm
    # một server cũ/ứng dụng khác đang chiếm port 5001.
    if responds(port):
        webbrowser.open(f"http://127.0.0.1:{port}"); return
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0: break
        port += 1
    url = f"http://127.0.0.1:{port}"
    up = lambda: responds(port)
    try:
        import webview  # cửa sổ riêng của macOS (pywebview); thiếu thì dùng trình duyệt
    except ImportError:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=port); return
    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False), daemon=True).start()
    for _ in range(50):
        if up(): break
        time.sleep(0.1)
    try: webview.settings["ALLOW_DOWNLOADS"] = True  # cho phép nút Xuất Excel
    except Exception: pass
    webview.create_window("Trading Journal", url, width=1280, height=860, min_size=(900, 600))
    webview.start()  # đóng cửa sổ = thoát app

if __name__ == "__main__":
    main()
