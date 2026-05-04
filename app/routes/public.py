import os
import uuid
import time
from datetime import datetime
from flask import (
    Blueprint, request, redirect, url_for, jsonify,
    render_template, current_app, session, flash
)
from app.services.order import (
    load_orders, save_orders, find_order,
    get_next_queue_number, job_seconds,
    get_paid_queue_info, get_paid_queue_pages,
    get_job_pages, get_sec_per_page,
    get_effective_remaining_pages_for_queue,
    get_user_orders,
)
from app.services.queue_worker import mark_order_paid_for_queue
from app.services.user import update_user_balance, get_user
from app.utils.helpers import get_pdf_pages, make_receipt_qr, login_required, admin_required

public_bp = Blueprint("public", __name__)

def _safe_unlink(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def _status_page_url(order_id):
    return url_for("public.status", order_id=order_id)

@public_bp.route("/")
def index():
    if "user_phone" in session:
        return redirect(url_for("public.print_page"))
    return render_template("index.html", title="AutoPrinter • Welcome")

@public_bp.route("/print")
@login_required
def print_page():
    user = get_user(session["user_phone"])
    return render_template(
        "print.html",
        title="AutoPrinter • Upload",
        user=user
    )

@public_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if not file:
        return render_template("message.html", title="Error", body_html="No file uploaded!"), 400
    if not file.filename.lower().endswith(".pdf"):
        return render_template("message.html", title="Error", body_html="Only PDF allowed!"), 400

    try:
        copies = int(request.form.get("copies", 1))
    except (TypeError, ValueError):
        copies = 1
    if copies < 1:
        return render_template("message.html", title="Error", body_html="Copies must be at least 1."), 400

    ptype = request.form.get("ptype", "bw")
    now = time.time()

    orders = load_orders()
    tmp_filename = f".uploading_{uuid.uuid4().hex}.pdf"
    tmp_filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], tmp_filename)
    file.save(tmp_filepath)

    pages = get_pdf_pages(tmp_filepath)
    total_pages = pages * copies

    if total_pages > 40:
        _safe_unlink(tmp_filepath)
        return render_template("message.html", title="Error", body_html="Cannot print more than 40 pages at once."), 400

    used_pages = get_paid_queue_pages(orders, now=now)
    capacity_pages = int(current_app.config.get("MAX_PAID_QUEUE_PAGES", 40))
    if used_pages + total_pages > capacity_pages:
        _safe_unlink(tmp_filepath)
        body_html = (
            "Queue full. Try again in a few minutes.<br>"
            "<span class='text-muted' style='font-size:12px;'>"
            "Capacity frees automatically as printing progresses."
            "</span>"
        )
        return render_template("message.html", title="Queue Full", body_html=body_html), 429

    order_id = str(uuid.uuid4())[:8]
    filename = f"{order_id}.pdf"
    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    os.replace(tmp_filepath, filepath)

    total = float(total_pages * current_app.config["PRICE_PER_PAGE"])
    queue_no = get_next_queue_number(orders)

    orders.append({
        "queue_no": queue_no,
        "order_id": order_id,
        "session_id": session.get("session_id", ""),
        "phone": session["user_phone"],
        "filename": filename,
        "filepath": os.path.abspath(filepath),
        "pages": pages,
        "copies": copies,
        "ptype": ptype,
        "total": total,
        "status": "PAYMENT_PENDING",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "created_time": int(time.time()),
        "printed_time": None,
    })
    save_orders(orders)

    return redirect(url_for("public.token", order_id=order_id))


@public_bp.route("/token/<order_id>")
@login_required
def token(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404
    
    if order.get("phone") != session["user_phone"] and not admin_required():
        return render_template("message.html", title="Error", body_html="Access Denied!"), 403

    qr_img = make_receipt_qr(order_id)
    paid_pages, paid_seconds = get_paid_queue_info()
    my_seconds = job_seconds(order)
    estimated_total = int(paid_seconds + my_seconds)

    user = get_user(session["user_phone"])

    return render_template(
        "token.html",
        title="AutoPrinter • Token",
        order=order,
        qr_img=qr_img,
        paid_pages=paid_pages,
        estimated_total=estimated_total,
        user=user
    )


@public_bp.route("/pay/<order_id>", methods=["POST", "GET"])
@login_required
def pay(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404
        
    if order.get("phone") != session["user_phone"]:
        return render_template("message.html", title="Error", body_html="Access Denied!"), 403

    if order.get("status") in {"WAITING_QUEUE", "QUEUED", "PRINTING", "PRINTED", "PRINT_FAILED"}:
        return redirect(_status_page_url(order_id))

    user = get_user(session["user_phone"])
    total_cost = float(order.get("total", 0.0))
    current_balance = float(user.get("balance", 0.0))

    if request.method == "POST":
        if current_balance >= total_cost:
            success, new_bal = update_user_balance(session["user_phone"], -total_cost)
            if success:
                mark_order_paid_for_queue(order_id)
                return redirect(_status_page_url(order_id))
            else:
                return render_template("message.html", title="Error", body_html="Failed to deduct balance.", headline="❌ Error"), 500
        else:
            return redirect(url_for("wallet.dashboard"))

    # GET request shows confirmation
    return render_template(
        "message.html",
        title="Confirm Payment",
        headline="Confirm Payment",
        body_html=f"Order Total: {total_cost} TK<br>Wallet Balance: {current_balance} TK<br><br>" + 
        (f"<form method='post'><button type='submit' class='btn btn-primary w-full'>Pay Now</button></form>" if current_balance >= total_cost else f"<div class='alert-error'>Insufficient balance! You need {total_cost - current_balance} TK more.</div><a href='/wallet' class='btn btn-primary w-full mt-2'>Top Up Wallet</a>")
    )


@public_bp.route("/status/<order_id>")
def status(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404
    return render_template("status.html", title="AutoPrinter • Status", order=order)


@public_bp.route("/status-data/<order_id>")
def status_data(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return jsonify({"ok": False}), 404

    now = time.time()
    status = order.get("status")
    paid_pages = get_paid_queue_pages(orders, now=now)
    my_pages = get_job_pages(order)
    paid_time = order.get("paid_time")

    def response(remaining=None, progress=None, pages_before=0):
        return jsonify({
            "ok": True,
            "status": status,
            "remaining": remaining,
            "progress": progress,
            "pages_before": int(pages_before),
            "jobs_before": int(pages_before),
            "paid_queue_pages": paid_pages,
            "my_pages": my_pages,
            "queue_no": order.get("queue_no"),
            "total": order.get("total"),
        })

    if status == "PRINTED":
        return response(remaining=0, progress=100)

    if status == "PRINT_FAILED":
        return response()

    if not paid_time:
        return response()

    active_statuses = {"WAITING_QUEUE", "QUEUED", "PRINTING"}

    def paid_fifo_key(o):
        try:
            order_paid_time = int(o.get("paid_time") or 0)
        except (TypeError, ValueError):
            order_paid_time = 0
        return order_paid_time, str(o.get("order_id") or "")

    queue = [
        o for o in orders
        if o.get("paid_time") and o.get("status") in active_statuses
    ]
    queue_sorted = sorted(queue, key=paid_fifo_key)

    my_idx = next((i for i, o in enumerate(queue_sorted) if o.get("order_id") == order_id), None)
    if my_idx is None:
        return response()

    def remaining_pages_for_queue_job(o):
        return get_effective_remaining_pages_for_queue(o, now=now)

    pages_before = 0
    seconds_before = 0
    for o in queue_sorted[:my_idx]:
        rp = remaining_pages_for_queue_job(o)
        pages_before += rp
        seconds_before += rp * get_sec_per_page(o)

    my_remaining_pages = remaining_pages_for_queue_job(order)
    seconds_remaining = seconds_before + (my_remaining_pages * get_sec_per_page(order))

    progress = None
    if status == "PRINTING":
        printed_pages = my_pages - my_remaining_pages
        if my_pages > 0:
            progress = int((printed_pages / my_pages) * 100)
            progress = max(0, min(100, progress))

    return response(
        remaining=int(max(0, seconds_remaining)),
        progress=progress,
        pages_before=pages_before,
    )


@public_bp.route("/history")
@login_required
def history():
    orders = load_orders()
    my_orders = [o for o in orders if o.get("phone") == session["user_phone"]]
    my_orders.sort(key=lambda x: x.get("created_time", 0), reverse=True)

    return render_template(
        "history.html",
        title="AutoPrinter • History",
        orders=my_orders[:20],
    )

@public_bp.route("/public-qr")
def public_qr():
    qr_filename = "public_qr.png"
    qr_path = os.path.join(current_app.config["STATIC_FOLDER"], qr_filename)
    redirect_link = f"{current_app.config['PUBLIC_BASE_URL']}/print"

    import qrcode
    img = qrcode.make(redirect_link)
    img.save(qr_path)

    body_html = """
      <div class="text-muted">Scan this QR to open AutoPrinter</div>
      <div class="softLine"></div>
      <img src="/static/public_qr.png" width="220"
           style="border-radius:18px;border:1px solid rgba(255,255,255,0.15);padding:10px;">
      <div class="softLine"></div>
      <a class="btn btn-primary w-full" href="/print">Open Website</a>
    """
    return render_template(
        "message.html",
        title="Public QR",
        headline="📲 Scan to Open AutoPrinter",
        center=True,
        body_html=body_html,
    )
