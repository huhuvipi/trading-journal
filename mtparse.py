"""Đọc báo cáo giao dịch MT4/MT5 (.xlsx, .html, .htm) -> danh sách lệnh + chẩn đoán."""
import io, re, unicodedata
from datetime import datetime, timedelta

def nz(s):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFC", "" if s is None else str(s)).lower())

PROFIT = {"profit", "pnl", "netprofit", "lợinhuận", "lãilỗ"}
BALANCE_LABELS = ("initialbalance", "initialdeposit", "startingbalance", "startbalance", "openingbalance")
ALIAS = {
    "time": ["time", "opentime", "timeopen", "datetime", "date", "thờigian"],
    "ticket": ["position", "ticket", "deal", "order"],
    "symbol": ["symbol", "item", "instrument"],
    "type": ["type", "side", "action", "loại"],
    "direction": ["direction"],
    "volume": ["volume", "size", "lots", "lot", "khốilượng"],
    "profit": sorted(PROFIT),
    "commission": ["commission", "hoahồng"],
    "swap": ["swap", "hoánđổi"],
    "fee": ["fee", "taxes"],
    "balance": ["balance", "accountbalance", "sốdư"],
}
FMT = ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
       "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")

def num(v):
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return float(v)
    s = re.sub(r"\s", "", str(v).replace("\u2212", "-"))
    if "," in s and "." in s: s = s.replace(",", "")
    elif "," in s:
        # 50,000 là cách viết hàng nghìn; 50,5 mới là số thập phân.
        s = s.replace(",", "") if len(s.rsplit(",", 1)[1]) == 3 else s.replace(",", ".")
    try: return float(s)
    except ValueError: return None

def ptime(v):
    if isinstance(v, datetime): return v
    if isinstance(v, (int, float)) and 20000 < v < 100000:
        return datetime(1899, 12, 30) + timedelta(days=v)
    for f in FMT:
        try: return datetime.strptime(str(v).strip(), f)
        except ValueError: pass
    return None

def html_rows(data, mode):
    from lxml import html as LH
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"): text = data.decode("utf-16", "replace")
    elif data[1:2] == b"\x00": text = data.decode("utf-16-le", "replace")
    else: text = data.decode("utf-8-sig", "replace")
    root = LH.fromstring(text.encode("utf-8"), parser=LH.HTMLParser(encoding="utf-8"))
    out = []
    for tr in root.iter("tr"):
        r = []
        for c in tr:
            if c.tag not in ("td", "th"): continue
            r.append(c.text_content().strip())
            if mode == "expand":
                try: r += [""] * (min(int(c.get("colspan") or 1), 40) - 1)
                except ValueError: pass
        out.append([x for x in r if x] if mode == "compact" else r)
    return out

def xlsx_rows(data):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), data_only=True)
    return [["" if v is None else v for v in row] for ws in wb.worksheets for row in ws.iter_rows(values_only=True)]

def is_header(n):
    s = set(n)
    return len(n) > 2 and bool(PROFIT & s or ("type" in s and s & {"symbol", "item"} and s & {"volume", "size", "lots"}))

def tables(rows):
    T, cur = [], None
    for r in rows:
        n = [nz(c) for c in r]
        if is_header(n):
            cur = {"raw": [str(c) for c in r], "h": n, "rows": []}; T.append(cur); continue
        if cur and sum(1 for c in r if str(c).strip()) >= max(3, len(cur["h"]) // 2):
            cur["rows"].append(r)
    return T

def initial_balance(rows):
    """Tìm vốn ban đầu trong phần summary của báo cáo MT4/MT5."""
    fallback = None
    for row in rows:
        cells = list(row)
        for i, cell in enumerate(cells):
            label = nz(cell)
            if not label: continue
            hit = any(key in label for key in BALANCE_LABELS)
            plain = label in ("balance", "vốnbđầu", "vốnbanđầu")
            if not (hit or plain): continue
            for value in cells[i + 1:]:
                amount = num(value)
                if amount is not None and amount > 0:
                    if hit: return amount
                    fallback = amount
    return fallback

def table_trades(t):
    idx = {}
    for i, k in enumerate(t["h"]): idx.setdefault(k, i)
    col = {f: next((idx[a] for a in al if a in idx), None) for f, al in ALIAS.items()}
    out, skip = [], 0
    for r in t["rows"]:
        g = lambda f: r[col[f]] if col[f] is not None and col[f] < len(r) else None
        side = str(g("type") or "").lower()
        drn = str(g("direction") or "").lower()
        p, ts = num(g("profit")), ptime(g("time"))
        if not re.search(r"buy|sell|mua|bán", side) or drn == "in" or p is None or ts is None:
            skip += 1; continue
        net = p + sum(num(g(f)) or 0 for f in ("commission", "swap", "fee"))
        sell = bool(re.search(r"sell|bán", side)) != (drn == "out")
        vol, tk = num(g("volume")) or 0, str(g("ticket") or "")
        iso = ts.strftime("%Y-%m-%d %H:%M:%S")
        out.append({"key": f"{tk}|{iso}|{vol}|{net:.2f}", "ts": iso, "ticket": tk, "symbol": str(g("symbol") or ""),
                    "side": "Sell" if sell else "Buy", "volume": vol, "profit": round(net, 2)})
    return out, skip

def extract(rows):
    T, info = tables(rows), []
    for t in T:
        t["tr"], sk = table_trades(t)
        info.append({"columns": t["raw"], "rows": len(t["rows"]), "trades": len(t["tr"]), "skipped": sk, "deal": "direction" in t["h"]})
    pick = next((t for t in T if t["tr"] and "direction" not in t["h"]), None)
    # MT5 thường đặt số dư ban đầu ở cột Balance, dòng đầu tiên của bảng Deals.
    deals_balance = None
    for t in T:
        if "direction" not in t["h"] or not t["rows"]: continue
        bi = next((i for i, h in enumerate(t["h"]) if h in ALIAS["balance"]), None)
        if bi is not None and bi < len(t["rows"][0]):
            value = num(t["rows"][0][bi])
            if value is not None and value > 0:
                deals_balance = value
                break
    return {"trades": pick["tr"] if pick else [x for t in T for x in t["tr"]],
            "tables": info, "initial_balance": deals_balance or initial_balance(rows)}

def parse(data):
    if data[:2] == b"PK": fmt, variants = "xlsx", [("xlsx", lambda: xlsx_rows(data))]
    elif data[:2] == b"\xd0\xcf": raise ValueError("File .xls nhị phân cũ không đọc được. Hãy lưu lại thành .xlsx hoặc xuất báo cáo HTML.")
    else: fmt, variants = "html", [(m, lambda m=m: html_rows(data, m)) for m in ("raw", "expand", "compact")]
    best = None
    for mode, get in variants:
        rows = get(); res = extract(rows); res["mode"] = mode
        if best is None or len(res["trades"]) > len(best["trades"]):
            best = res; best["head"] = [[str(c) for c in r][:14] for r in rows[:25]]
        if res["trades"]: break
    best["format"] = fmt
    return best
