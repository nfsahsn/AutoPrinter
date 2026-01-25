from flask import Flask, request, redirect, url_for, session, send_file, jsonify
import os, json, uuid, subprocess, csv
from datetime import datetime, date
import requests
import fitz
import qrcode
import time
from threading import Lock

app = Flask(__name__)

# ---------------- SETTINGS ----------------

app.secret_key = "CHANGE_THIS_SECRET_KEY_123"

# 🔐 Admin password (changeable from admin panel)
ADMIN_PASSWORD_DEFAULT = "hackhobena"
ADMIN_PASS_FILE = "admin_pass.json"

# ✅ Your public host (NO trailing slash)
PUBLIC_BASE_URL = "https://campanological-unwinning-clifford.ngrok-free.dev"

# ✅ NagarikPay API
NAGORIKPAY_API_KEY = "Y398rPST8FwhzzCpEJMcymljefa0jBwBmWzMqXKjCpKj9BeGAn"
NAGORIKPAY_CREATE_URL = "https://secure-pay.nagorikpay.com/api/payment/create"

PRICE_PER_PAGE = 2

AUTO_DELETE_AFTER_PRINT = True
ADMIN_REFRESH_SECONDS = 5

# Paid queue limit (pages)
MAX_PAID_QUEUE_PAGES = 50

# Estimated print speed
BW_SECONDS_PER_PAGE = 5
COLOR_SECONDS_PER_PAGE = 10

# Payment link expire
PAYMENT_LINK_EXPIRE_SECONDS = 10 * 60  # 10 minutes

PRINTER_LOCK = Lock()

# SumatraPDF paths (Windows)
SUMATRA_PATH_1 = r"C:\Users\USER\AppData\Local\SumatraPDF\SumatraPDF.exe"
SUMATRA_PATH_2 = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
SUMATRA_PATH_3 = r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe"

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
STATIC_FOLDER = os.path.join(BASE_DIR, "static")
DB_FILE = os.path.join(BASE_DIR, "orders.json")
REPORTS_FOLDER = os.path.join(BASE_DIR, "reports")
ADMIN_PASS_PATH = os.path.join(BASE_DIR, ADMIN_PASS_FILE)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)


# ---------------- ADMIN PASSWORD STORAGE ----------------

def load_admin_password():
    if not os.path.exists(ADMIN_PASS_PATH):
        return ADMIN_PASSWORD_DEFAULT
    try:
        with open(ADMIN_PASS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("password", ADMIN_PASSWORD_DEFAULT)
    except:
        return ADMIN_PASSWORD_DEFAULT

def save_admin_password(new_pass):
    with open(ADMIN_PASS_PATH, "w", encoding="utf-8") as f:
        json.dump({"password": new_pass}, f, indent=2)


# ---------------- UI TEMPLATE ----------------

def page_template(title, body, extra_head=""):
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{title}</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
      {extra_head}
      <style>
        :root {{
          --bg1:#050812; --bg2:#0b1220;
          --card:rgba(255,255,255,0.06);
          --border:rgba(255,255,255,0.12);
          --text:#eaf0ff;
          --muted:rgba(234,240,255,0.7);
        }}
        body {{
          background: radial-gradient(1200px 700px at 20% 0%, rgba(96,165,250,0.14), transparent 60%),
                      radial-gradient(900px 600px at 90% 10%, rgba(34,197,94,0.14), transparent 60%),
                      linear-gradient(180deg,var(--bg1),var(--bg2));
          color:var(--text);
          overflow-x:hidden;
        }}
        .wrap {{ max-width:780px; margin:0 auto; padding:18px 14px 40px; }}
        .cardx {{
          background:var(--card);
          border:1px solid var(--border);
          border-radius:20px;
          padding:18px;
          box-shadow:0 18px 45px rgba(0,0,0,0.4);
          backdrop-filter: blur(12px);
          animation: pop 0.5s ease both;
        }}
        @keyframes pop {{
          from {{ opacity:0; transform: translateY(16px); }}
          to {{ opacity:1; transform: translateY(0); }}
        }}
        .muted {{ color:var(--muted); }}
        .btn {{
          border-radius:16px;
          padding:12px 14px;
          font-weight:800;
        }}
        .btn-primary {{
          background: linear-gradient(90deg, rgba(96,165,250,1), rgba(34,197,94,1));
          border:none;
        }}
        .form-control, .form-select {{
          background: rgba(255,255,255,0.06) !important;
          border: 1px solid rgba(255,255,255,0.12) !important;
          color: #eaf0ff !important;
          border-radius: 16px !important;
          padding: 12px 14px !important;
        }}
        .metric {{
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.12);
          border-radius: 16px;
          padding: 12px;
        }}
        .metric .k {{ font-size:12px; font-weight:900; color:rgba(234,240,255,0.65); }}
        .metric .v {{ font-size:16px; font-weight:900; }}
        .softLine {{
          height:1px;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent);
          margin: 14px 0;
        }}
        pre {{
          background: rgba(0,0,0,0.35);
          padding: 12px;
          border-radius: 12px;
          color: #eaf0ff;
          overflow-x: auto;
          font-size: 12px;
        }}
        a {{ color:#9ecbff; }}

        /* Progress bar */
        .pwrap {{
          width: 100%;
          height: 14px;
          border-radius: 999px;
          border: 1px solid rgba(255,255,255,0.14);
          background: rgba(255,255,255,0.05);
          overflow: hidden;
        }}
        .pbar {{
          height: 100%;
          width: 0%;
          border-radius: 999px;
          background: linear-gradient(90deg, rgba(96,165,250,1), rgba(34,197,94,1));
          transition: width 0.8s ease;
        }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="mb-3">
          <h3 class="fw-bold mb-1">📄 AutoPrinter</h3>
          <div class="muted">Scan • Upload • Pay • Print • PDF Only</div>
        </div>

        {body}

        <div class="text-center muted mt-4" style="font-size:12px;">
          Price: {PRICE_PER_PAGE} taka per page
        </div>
      </div>
    </body>
    </html>
    """


# ---------------- HELPERS ----------------

def get_sumatra_path():
    for p in [SUMATRA_PATH_1, SUMATRA_PATH_2, SUMATRA_PATH_3]:
        if os.path.exists(p):
            return p
    return None

def load_orders():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_orders(orders):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)

def find_order(orders, order_id):
    return next((o for o in orders if o.get("order_id") == order_id), None)

def safe_delete_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            return True
    except:
        pass
    return False

def get_pdf_pages(filepath):
    try:
        doc = fitz.open(filepath)
        pages = doc.page_count
        doc.close()
        return pages
    except:
        return 1

def get_next_queue_number(orders):
    today = date.today().strftime("%Y-%m-%d")
    today_orders = [o for o in orders if str(o.get("time", "")).startswith(today)]
    return len(today_orders) + 1

def print_pdf_windows(filepath, copies):
    sumatra = get_sumatra_path()
    if not sumatra:
        raise Exception("SumatraPDF not found! Please install SumatraPDF.")

    cmd = [
        sumatra,
        "-print-to-default",
        "-silent",
        "-exit-on-print",
        "-print-settings",
        f"copies={copies}",
        filepath
    ]
    subprocess.run(cmd, check=True)

def job_seconds(order):
    pages = int(order.get("pages", 0))
    copies = int(order.get("copies", 1))
    ptype = order.get("ptype", "bw")
    sec_per_page = BW_SECONDS_PER_PAGE if ptype == "bw" else COLOR_SECONDS_PER_PAGE
    return pages * copies * sec_per_page

def get_paid_queue_pages(orders):
    total_pages = 0
    for o in orders:
        if o.get("status") in ["PAID", "PRINTING"]:
            total_pages += int(o.get("pages", 0)) * int(o.get("copies", 1))
    return total_pages

def get_paid_queue_info():
    orders = load_orders()
    total_pages = 0
    total_seconds = 0
    for o in orders:
        if o.get("status") in ["PAID", "PRINTING"]:
            total_pages += int(o.get("pages", 0)) * int(o.get("copies", 1))
            total_seconds += job_seconds(o)
    return total_pages, total_seconds

def get_paid_queue_seconds_before(order_id):
    orders = load_orders()
    total = 0
    for o in orders:
        if o.get("status") in ["PAID", "PRINTING"]:
            if o.get("order_id") == order_id:
                continue
            total += job_seconds(o)
    return total

def get_paid_jobs_before(order_id):
    """
    Count how many PAID/PRINTING jobs are before this order.
    (based on paid_time)
    """
    orders = load_orders()
    me = find_order(orders, order_id)
    if not me or not me.get("paid_time"):
        return 0

    me_paid_time = int(me.get("paid_time") or 0)
    count = 0
    for o in orders:
        if o.get("status") in ["PAID", "PRINTING"]:
            if o.get("order_id") == order_id:
                continue
            if o.get("paid_time") and int(o["paid_time"]) <= me_paid_time:
                count += 1
    return count

def make_receipt_qr(order_id):
    # Status QR
    qr_path = os.path.join(STATIC_FOLDER, f"qr_{order_id}.png")
    url = f"{PUBLIC_BASE_URL}/status/{order_id}"
    img = qrcode.make(url)
    img.save(qr_path)
    return f"/static/qr_{order_id}.png"

def admin_required():
    return session.get("admin_logged_in") is True


# ---------------- QR Redirect (PRO) ----------------

@app.route("/go")
def go():
    target = request.args.get("to", f"{PUBLIC_BASE_URL}/print")
    if not target.startswith("http"):
        target = f"{PUBLIC_BASE_URL}/print"

    body = f"""
    <div class="cardx text-center">
      <h3 style="margin:0;">🔗 Connecting...</h3>
      <div class="muted" style="margin-top:8px;">Opening AutoPrinter</div>

      <div style="margin-top:18px;">
        <div class="spinner-border text-light" role="status"></div>
      </div>

      <div class="muted" style="margin-top:14px;font-size:12px;">
        Please wait...
      </div>
    </div>

    <script>
      setTimeout(() => {{
        window.location.href = "{target}";
      }}, 1200);
    </script>
    """
    return page_template("Redirecting...", body)


@app.route("/public-qr")
def public_qr():
    qr_path = os.path.join(STATIC_FOLDER, "public_qr.png")
    redirect_link = f"{PUBLIC_BASE_URL}/go?to={PUBLIC_BASE_URL}/print"
    img = qrcode.make(redirect_link)
    img.save(qr_path)

    body = f"""
    <div class="cardx text-center">
      <h4 class="fw-bold mb-2">📲 Scan to Open AutoPrinter</h4>
      <div class="muted">This QR shows a loading page then redirects.</div>
      <div class="softLine"></div>
      <img src="/static/public_qr.png" width="260"
           style="border-radius:18px;border:1px solid rgba(255,255,255,0.15);padding:10px;">
      <div class="softLine"></div>
      <a class="btn btn-primary w-100" href="/print">Open Website</a>
    </div>
    """
    return page_template("Public QR", body)


# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return redirect(url_for("print_page"))

@app.route("/print")
def print_page():
    body = """
    <div class="cardx">
      <h4 class="fw-bold mb-1">Upload PDF</h4>
      <div class="muted">Only PDF allowed • A4 Printer</div>
      <div class="softLine"></div>

      <form action="/upload" method="post" enctype="multipart/form-data">
        <div class="mb-3">
          <label class="form-label fw-bold muted">PDF File</label>
          <input class="form-control" type="file" name="file" accept="application/pdf" required>
        </div>

        <div class="row g-3">
          <div class="col-6">
            <label class="form-label fw-bold muted">Copies</label>
            <input class="form-control" type="number" name="copies" min="1" value="1" required>
          </div>
          <div class="col-6">
            <label class="form-label fw-bold muted">Type</label>
            <select class="form-select" name="ptype">
              <option value="bw">B/W</option>
              <option value="color">Color</option>
            </select>
          </div>
        </div>

        <button class="btn btn-primary w-100 mt-3" type="submit">Continue →</button>

        <div class="text-center mt-3">
          <a class="muted" href="/public-qr">📲 Public QR</a> •
          <a class="muted" href="/admin-login">Admin Login</a>
        </div>
      </form>
    </div>
    """
    return page_template("AutoPrinter • Upload", body)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return page_template("Error", "<div class='cardx'>No file uploaded!</div>"), 400

    if not file.filename.lower().endswith(".pdf"):
        return page_template("Error", "<div class='cardx'>Only PDF allowed!</div>"), 400

    copies = int(request.form.get("copies", 1))
    ptype = request.form.get("ptype", "bw")

    orders = load_orders()

    order_id = str(uuid.uuid4())[:8]
    filename = f"{order_id}.pdf"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    pages = get_pdf_pages(filepath)
    total = pages * copies * PRICE_PER_PAGE
    queue_no = get_next_queue_number(orders)

    orders.append({
        "queue_no": queue_no,
        "order_id": order_id,
        "filename": filename,
        "filepath": os.path.abspath(filepath),
        "pages": pages,
        "copies": copies,
        "ptype": ptype,
        "total": total,
        "trxid": "",
        "status": "WAITING_PAYMENT",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "paid_time": None,
        "printed_time": None,
        "payment_created_time": None
    })
    save_orders(orders)

    return redirect(url_for("token", order_id=order_id))

@app.route("/token/<order_id>")
def token(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return "Order not found!", 404

    qr_img = make_receipt_qr(order_id)

    paid_pages, paid_seconds = get_paid_queue_info()
    my_seconds = job_seconds(order)
    estimated_total = paid_seconds + my_seconds

    body = f"""
    <div class="cardx text-center">
      <div class="muted">Your Token Number</div>
      <h1 style="font-size:60px;font-weight:900;">#{order["queue_no"]}</h1>

      <div class="row g-3 mt-2 text-start">
        <div class="col-6"><div class="metric"><div class="k">Pages</div><div class="v">{order["pages"]}</div></div></div>
        <div class="col-6"><div class="metric"><div class="k">Copies</div><div class="v">{order["copies"]}</div></div></div>
        <div class="col-12"><div class="metric"><div class="k">Total</div><div class="v" style="color:#22c55e;">{order["total"]} taka</div></div></div>
      </div>

      <div class="softLine"></div>

      <div class="row g-3 text-start">
        <div class="col-6">
          <div class="metric">
            <div class="k">Paid Queue Pages</div>
            <div class="v">{paid_pages} pages</div>
          </div>
        </div>
        <div class="col-6">
          <div class="metric">
            <div class="k">Estimated Time</div>
            <div class="v">{int(estimated_total)} sec</div>
          </div>
        </div>
      </div>

      <div class="softLine"></div>

      <div class="muted">Scan QR to check status</div>
      <img src="{qr_img}" width="220" style="border-radius:18px;border:1px solid rgba(255,255,255,0.15);padding:10px;">

      <a class="btn btn-primary w-100 mt-3" href="/pay/{order_id}">Go to Payment →</a>
      <a class="btn btn-dark w-100 mt-2" href="/status/{order_id}">Open Status</a>
    </div>
    """
    return page_template("AutoPrinter • Token", body)


# ---------------- PAYMENT ----------------

@app.route("/pay/<order_id>")
def pay(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return "Order not found!", 404

    if order["status"] in ["PAID", "PRINTING", "PRINTED"]:
        return redirect(url_for("status", order_id=order_id))

    paid_queue_pages = get_paid_queue_pages(orders)
    this_job_pages = int(order.get("pages", 0)) * int(order.get("copies", 1))

    if paid_queue_pages + this_job_pages > MAX_PAID_QUEUE_PAGES:
        return page_template(
            "Queue Full",
            f"""
            <div class='cardx text-center'>
              <h4 class='fw-bold text-danger'>❌ Queue Full</h4>
              <p class='muted'>Paid queue limit is {MAX_PAID_QUEUE_PAGES} pages.</p>
              <p class='muted'>Currently in paid queue: <b>{paid_queue_pages}</b> pages</p>
              <p class='muted'>Your job: <b>{this_job_pages}</b> pages</p>
              <a class="btn btn-dark w-100 mt-2" href="/status/{order_id}">Back</a>
            </div>
            """
        ), 400

    payload = {
        "success_url": f"{PUBLIC_BASE_URL}/np-success/{order_id}",
        "cancel_url": f"{PUBLIC_BASE_URL}/np-cancel/{order_id}",
        "webhook_url": f"{PUBLIC_BASE_URL}/np-webhook",
        "metadata": {
            "order_id": order_id,
            "queue_no": order["queue_no"],
            "pages": order["pages"],
            "copies": order["copies"],
            "ptype": order["ptype"],
            "total": order["total"]
        },
        "amount": str(order["total"])
    }

    headers = {
        "API-KEY": NAGORIKPAY_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(NAGORIKPAY_CREATE_URL, headers=headers, json=payload, timeout=20)
        data = r.json()
        payment_url = data.get("payment_url") or data.get("url") or data.get("redirect_url")

        order["gateway_response"] = data
        order["payment_created_time"] = int(time.time())
        save_orders(orders)

        if not payment_url:
            return page_template(
                "Payment Error",
                f"""
                <div class='cardx'>
                  <h4 class='fw-bold text-danger'>❌ Payment link not received</h4>
                  <div class='muted'>Gateway response:</div>
                  <pre>{json.dumps(data, indent=2)}</pre>
                  <a class="btn btn-dark w-100 mt-3" href="/status/{order_id}">Back</a>
                </div>
                """
            ), 500

        order["status"] = "PAYMENT_LINK_CREATED"
        order["payment_url"] = payment_url
        save_orders(orders)

        return redirect(payment_url)

    except Exception as e:
        return page_template("Payment Error", f"<div class='cardx'>Payment create error: {e}</div>"), 500


@app.route("/np-success/<order_id>")
def np_success(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return "Order not found!", 404

    # NagarikPay usually sends these in URL
    status = (request.args.get("status") or "").lower()
    trxid = request.args.get("transactionId") or request.args.get("transaction_id") or ""

    # If payment completed, auto print
    if status == "completed":
        if trxid:
            order["trxid"] = trxid

        # prevent double print
        if order.get("status") not in ["PRINTING", "PRINTED"]:
            order["paid_time"] = int(time.time())
            order["status"] = "PAID"
            save_orders(orders)

            try:
                order["status"] = "PRINTING"
                save_orders(orders)

                with PRINTER_LOCK:
                    print_pdf_windows(order["filepath"], order["copies"])
                    time.sleep(1)

                order["status"] = "PRINTED"
                order["printed_time"] = int(time.time())

                if AUTO_DELETE_AFTER_PRINT:
                    safe_delete_file(order["filepath"])
                    order["filepath"] = ""
                    order["filename"] = ""

                save_orders(orders)

            except Exception as e:
                order["status"] = "PRINT_FAILED"
                save_orders(orders)
                return page_template(
                    "Print Failed",
                    f"<div class='cardx'><h4 class='fw-bold text-danger'>❌ Print Failed</h4><pre>{e}</pre><a class='btn btn-dark w-100 mt-3' href='/status/{order_id}'>Back</a></div>"
                ), 500

    body = f"""
    <div class="cardx text-center">
      <h3 class="fw-bold">✅ Payment Completed</h3>
      <p class="muted">Printing will start automatically now.</p>
      <a class="btn btn-primary w-100" href="/status/{order_id}">Check Status</a>
    </div>
    """
    return page_template("Payment Success", body)

@app.route("/np-cancel/<order_id>")
def np_cancel(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)

    if order and order.get("status") in ["PAYMENT_LINK_CREATED", "WAITING_PAYMENT"]:
        order["status"] = "WAITING_PAYMENT"
        save_orders(orders)

    body = f"""
    <div class="cardx text-center">
      <h3 class="fw-bold text-danger">❌ Payment Cancelled</h3>
      <p class="muted">You cancelled the payment or closed the gateway.</p>
      <a class="btn btn-primary w-100 mt-2" href="/pay/{order_id}">💳 Try Payment Again</a>
      <a class="btn btn-dark w-100 mt-2" href="/status/{order_id}">Back to Status</a>
    </div>
    """
    return page_template("Payment Cancelled", body)


# ---------------- WEBHOOK (AUTO PRINT) ----------------

@app.route("/np-webhook", methods=["POST"])
def np_webhook():
    payload_json = request.get_json(silent=True) or {}
    payload_form = dict(request.form) if request.form else {}
    payload = payload_json if payload_json else payload_form

    metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {}
    order_id = metadata.get("order_id") or payload.get("order_id") or request.args.get("order_id")

    if not order_id:
        return {"ok": False, "error": "order_id missing"}, 400

    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return {"ok": False, "error": "order not found"}, 404

    if order.get("status") == "PRINTED":
        return {"ok": True, "message": "Already printed"}, 200

    order["np_webhook"] = payload

    trxid = payload.get("transactionId") or payload.get("trxid") or payload.get("transaction_id") or payload.get("payment_id") or ""
    if trxid:
        order["trxid"] = str(trxid)

    order["paid_time"] = int(time.time())
    order["status"] = "PAID"
    save_orders(orders)

    try:
        order["status"] = "PRINTING"
        save_orders(orders)

        with PRINTER_LOCK:
            print_pdf_windows(order["filepath"], order["copies"])
            time.sleep(1)

        order["status"] = "PRINTED"
        order["printed_time"] = int(time.time())

        if AUTO_DELETE_AFTER_PRINT:
            safe_delete_file(order["filepath"])
            order["filepath"] = ""
            order["filename"] = ""

        save_orders(orders)
        return {"ok": True, "message": "Printed successfully"}, 200

    except Exception as e:
        order["status"] = "PRINT_FAILED"
        save_orders(orders)
        return {"ok": False, "error": str(e)}, 500


# ---------------- STATUS + REALTIME COUNTDOWN + QUEUE POSITION ----------------

@app.route("/status-data/<order_id>")
def status_data(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return jsonify({"ok": False}), 404

    paid_pages, paid_seconds = get_paid_queue_info()
    my_seconds = job_seconds(order)
    my_pages = int(order.get("pages", 0)) * int(order.get("copies", 1))

    jobs_before = 0
    remaining = None
    progress = None  # 0..100

    if order.get("paid_time"):
        jobs_before = get_paid_jobs_before(order_id)
        seconds_before = get_paid_queue_seconds_before(order_id)
        total_wait = seconds_before + my_seconds
        passed = int(time.time()) - int(order["paid_time"])
        remaining = max(0, total_wait - passed)

        # progress only for my job time (after my queue)
        if total_wait > 0:
            progress = int(((total_wait - remaining) / total_wait) * 100)
            progress = max(0, min(100, progress))

    return jsonify({
        "ok": True,
        "status": order.get("status"),
        "remaining": remaining,
        "progress": progress,
        "jobs_before": jobs_before,
        "paid_queue_pages": paid_pages,
        "my_pages": my_pages,
        "my_seconds": my_seconds,
        "queue_no": order.get("queue_no"),
        "total": order.get("total")
    })


@app.route("/status/<order_id>")
def status(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return "Order not found!", 404

    body = f"""
    <div class="cardx text-center">
      <h4 class="fw-bold mb-2">Order Status</h4>

      <div class="row g-3 text-start mt-1">
        <div class="col-6"><div class="metric"><div class="k">Token</div><div class="v">#{order["queue_no"]}</div></div></div>
        <div class="col-6"><div class="metric"><div class="k">Status</div><div class="v" id="st">{order["status"]}</div></div></div>
        <div class="col-12"><div class="metric"><div class="k">Total</div><div class="v">{order["total"]} taka</div></div></div>
      </div>

      <div class="softLine"></div>

      <div class="p-3" style="border-radius:16px;border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.04);">
        <b id="msg">Loading...</b>

        <div class="muted mt-2" id="jobsBefore" style="font-size:14px;"></div>

        <div class="muted mt-2" id="timer" style="font-size:22px;font-weight:900;"></div>

        <div class="mt-3" id="progressBox" style="display:none;">
          <div class="pwrap">
            <div class="pbar" id="pbar"></div>
          </div>
          <div class="muted mt-2" style="font-size:12px;" id="ptext"></div>
        </div>

        <div class="softLine"></div>

        <div class="row g-2 text-start">
          <div class="col-6">
            <div class="metric">
              <div class="k">Paid Queue Pages</div>
              <div class="v" id="paidPages">-</div>
            </div>
          </div>
          <div class="col-6">
            <div class="metric">
              <div class="k">Your Job Pages</div>
              <div class="v" id="myPages">-</div>
            </div>
          </div>
        </div>
      </div>

      <div id="payAgainBox" style="display:none;">
        <a class="btn btn-primary w-100 mt-3" href="/pay/{order_id}">💳 Pay Again</a>
      </div>

      <a class="btn btn-dark w-100 mt-2" href="/print">New Print</a>
    </div>

    <script>
      function formatTime(sec) {{
        sec = Math.max(0, sec);
        let m = Math.floor(sec / 60);
        let s = sec % 60;
        return m + "m " + s + "s";
      }}

      async function refreshStatus() {{
        let r = await fetch("/status-data/{order_id}");
        let d = await r.json();
        if(!d.ok) return;

        document.getElementById("st").innerText = d.status;

        document.getElementById("paidPages").innerText = (d.paid_queue_pages ?? "-") + " pages";
        document.getElementById("myPages").innerText = (d.my_pages ?? "-") + " pages";

        let payAgain = document.getElementById("payAgainBox");
        let progressBox = document.getElementById("progressBox");

        if(d.status === "WAITING_PAYMENT") {{
          document.getElementById("msg").innerText = "💳 Waiting for payment...";
          document.getElementById("timer").innerText = "";
          document.getElementById("jobsBefore").innerText = "";
          progressBox.style.display = "none";
          payAgain.style.display = "block";
        }}
        else if(d.status === "PAYMENT_LINK_CREATED") {{
          document.getElementById("msg").innerText = "💳 Payment link created. Complete payment...";
          document.getElementById("timer").innerText = "";
          document.getElementById("jobsBefore").innerText = "";
          progressBox.style.display = "none";
          payAgain.style.display = "block";
        }}
        else if(d.status === "PAID" || d.status === "PRINTING") {{
          document.getElementById("msg").innerText = "🖨️ Estimated time remaining:";
          payAgain.style.display = "none";

          if(d.jobs_before !== null && d.jobs_before !== undefined) {{
            document.getElementById("jobsBefore").innerText =
              "📌 Jobs before you: " + d.jobs_before;
          }}

          if(d.remaining !== null) {{
            document.getElementById("timer").innerText = formatTime(d.remaining);
          }}

          progressBox.style.display = "block";
          let pct = d.progress ?? 0;
          document.getElementById("pbar").style.width = pct + "%";
          document.getElementById("ptext").innerText = "Progress: " + pct + "%";
        }}
        else if(d.status === "PRINTED") {{
          document.getElementById("msg").innerText = "✅ Printed Successfully!";
          document.getElementById("timer").innerText = "";
          document.getElementById("jobsBefore").innerText = "";
          progressBox.style.display = "none";
          payAgain.style.display = "none";
        }}
        else if(d.status === "PRINT_FAILED") {{
          document.getElementById("msg").innerText = "❌ Print failed. Contact admin.";
          document.getElementById("timer").innerText = "";
          document.getElementById("jobsBefore").innerText = "";
          progressBox.style.display = "none";
          payAgain.style.display = "block";
        }}
      }}

      setInterval(refreshStatus, 1000);
      refreshStatus();
    </script>
    """
    return page_template("AutoPrinter • Status", body)


# ---------------- ADMIN ----------------

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    current_pass = load_admin_password()

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == current_pass:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        return page_template("Admin Login", "<div class='cardx'>❌ Wrong password</div>")

    body = """
    <div class="cardx">
      <h4 class="fw-bold mb-2">🔐 Admin Login</h4>
      <form method="post">
        <label class="form-label fw-bold muted">Password</label>
        <input class="form-control mb-3" type="password" name="password" required>
        <button class="btn btn-primary w-100" type="submit">Login</button>
      </form>
    </div>
    """
    return page_template("Admin Login", body)

@app.route("/admin-logout")
def admin_logout():
    session["admin_logged_in"] = False
    return redirect(url_for("print_page"))

@app.route("/admin")
def admin():
    if not admin_required():
        return redirect(url_for("admin_login"))

    orders = load_orders()

    rows = ""
    for o in reversed(orders):
        oid = o.get("order_id", "")
        status = o.get("status", "")

        reprint_btn = ""
        if status in ["PAID", "PRINTING", "PRINTED", "PRINT_FAILED"]:
            reprint_btn = f"""
            <a class="btn btn-sm btn-outline-light" href="/admin-reprint/{oid}">
              🔁 Reprint
            </a>
            """

        rows += f"""
        <tr>
          <td><b>#{o.get("queue_no","")}</b></td>
          <td>{oid}</td>
          <td>{o.get("total","")}</td>
          <td>{o.get("pages","")}</td>
          <td>{o.get("copies","")}</td>
          <td>{o.get("ptype","")}</td>
          <td style="max-width:150px;word-break:break-word;">{o.get("trxid","")}</td>
          <td>{status}</td>
          <td>{reprint_btn if reprint_btn else "<span class='muted'>—</span>"}</td>
        </tr>
        """

    body = f"""
    <div class="cardx">
      <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div>
          <h4 class="fw-bold mb-0">🛠 Admin Panel</h4>
          <div class="muted">Auto refresh every {ADMIN_REFRESH_SECONDS}s</div>
        </div>
        <div class="d-flex gap-2">
          <a class="btn btn-outline-light" href="/admin-change-password">Change Password</a>
          <a class="btn btn-outline-light" href="/admin-logout">Logout</a>
        </div>
      </div>

      <div class="softLine"></div>

      <div class="table-responsive">
        <table class="table table-bordered table-sm align-middle">
          <thead>
            <tr>
              <th>Token</th><th>Order</th><th>Total</th><th>Pages</th>
              <th>Copies</th><th>Type</th><th>TrxID</th><th>Status</th><th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows if rows else "<tr><td colspan='9' class='text-center muted'>No orders yet</td></tr>"}
          </tbody>
        </table>
      </div>
    </div>
    """

    return page_template(
        "Admin Panel",
        body,
        extra_head=f"<meta http-equiv='refresh' content='{ADMIN_REFRESH_SECONDS}'>"
    )

@app.route("/admin-reprint/<order_id>")
def admin_reprint(order_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return page_template("Error", "<div class='cardx'>Order not found</div>"), 404

    if not order.get("filepath") or not os.path.exists(order.get("filepath", "")):
        return page_template(
            "Reprint Failed",
            "<div class='cardx'>❌ File not found (maybe auto deleted after print).</div>"
        ), 400

    try:
        with PRINTER_LOCK:
            print_pdf_windows(order["filepath"], order["copies"])
            time.sleep(1)

        order["status"] = "PRINTED"
        order["printed_time"] = int(time.time())
        save_orders(orders)

        return redirect(url_for("admin"))

    except Exception as e:
        order["status"] = "PRINT_FAILED"
        save_orders(orders)
        return page_template("Reprint Failed", f"<div class='cardx'>❌ {e}</div>"), 500

@app.route("/admin-change-password", methods=["GET", "POST"])
def admin_change_password():
    if not admin_required():
        return redirect(url_for("admin_login"))

    current_pass = load_admin_password()

    if request.method == "POST":
        old_pass = request.form.get("old_password", "")
        new_pass = request.form.get("new_password", "")
        confirm_pass = request.form.get("confirm_password", "")

        if old_pass != current_pass:
            return page_template("Change Password", "<div class='cardx'>❌ Old password is wrong</div>"), 400

        if len(new_pass) < 4:
            return page_template("Change Password", "<div class='cardx'>❌ New password too short</div>"), 400

        if new_pass != confirm_pass:
            return page_template("Change Password", "<div class='cardx'>❌ Passwords do not match</div>"), 400

        save_admin_password(new_pass)
        session["admin_logged_in"] = False

        return page_template(
            "Password Changed",
            "<div class='cardx text-center'><h4 class='fw-bold'>✅ Password Updated</h4><p class='muted'>Login again</p><a class='btn btn-primary w-100' href='/admin-login'>Login</a></div>"
        )

    body = """
    <div class="cardx">
      <h4 class="fw-bold mb-2">🔑 Change Admin Password</h4>
      <form method="post">
        <label class="form-label fw-bold muted">Old Password</label>
        <input class="form-control mb-3" type="password" name="old_password" required>

        <label class="form-label fw-bold muted">New Password</label>
        <input class="form-control mb-3" type="password" name="new_password" required>

        <label class="form-label fw-bold muted">Confirm Password</label>
        <input class="form-control mb-3" type="password" name="confirm_password" required>

        <button class="btn btn-primary w-100" type="submit">Update Password</button>
        <a class="btn btn-dark w-100 mt-2" href="/admin">Back</a>
      </form>
    </div>
    """
    return page_template("Change Password", body)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
