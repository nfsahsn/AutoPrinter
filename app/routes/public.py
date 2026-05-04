import os
import uuid
import time
import requests
from datetime import datetime
from flask import (
    Blueprint, request, redirect, url_for, jsonify,
    render_template, current_app, session,
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
from app.utils.helpers import get_pdf_pages, make_receipt_qr

public_bp = Blueprint("public", __name__)
_SUCCESS_PAYMENT_STATUSES = {
    "completed",
    "complete",
    "success",
    "successful",
    "paid",
    "payment_success",
    "payment.completed",
    "captured",
}


def init_session():
    if not session.get("session_id"):
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def _safe_unlink(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _payment_status_is_success(value):
    return str(value or "").strip().lower() in _SUCCESS_PAYMENT_STATUSES


def _status_page_url(order_id):
    return url_for("public.status", order_id=order_id)


# ── Auth routes ───────────────────────────────────────────────
@public_bp.route("/")
def index():
    return redirect(url_for("public.print_page"))


# ── Print routes ──────────────────────────────────────────────
@public_bp.route("/print")
def print_page():
    init_session()
    return render_template(
        "print.html",
        title="AutoPrinter • Upload",
    )


@public_bp.route("/upload", methods=["POST"])
def upload():
    session_id = init_session()

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

    total = total_pages * current_app.config["PRICE_PER_PAGE"]
    queue_no = get_next_queue_number(orders)

    orders.append({
        "queue_no": queue_no,
        "order_id": order_id,
        "session_id": session_id,
        "phone": "Guest",
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
def token(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404

    qr_img = make_receipt_qr(order_id)
    paid_pages, paid_seconds = get_paid_queue_info()
    my_seconds = job_seconds(order)
    estimated_total = int(paid_seconds + my_seconds)

    return render_template(
        "token.html",
        title="AutoPrinter • Token",
        order=order,
        qr_img=qr_img,
        paid_pages=paid_pages,
        estimated_total=estimated_total,
    )


@public_bp.route("/pay/<order_id>")
def pay(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404

    if order.get("status") in {"WAITING_QUEUE", "QUEUED", "PRINTING", "PRINTED", "PRINT_FAILED"}:
        return redirect(_status_page_url(order_id))

    existing_payment_url = str(order.get("payment_url") or "").strip()
    if order.get("status") == "PAYMENT_LINK_CREATED" and existing_payment_url:
        return redirect(existing_payment_url)

    api_key = str(current_app.config.get("PAYMENTLY_API_KEY") or "").strip()
    create_url = str(current_app.config.get("PAYMENTLY_CREATE_URL") or "").strip()
    if not api_key or not create_url:
        body_html = (
            "Payment gateway is not configured yet.<br>"
            "<span class='text-muted' style='font-size:12px;'>"
            "Please contact admin."
            "</span>"
        )
        return render_template("message.html", title="Payment Unavailable", body_html=body_html), 503

    public_base_url = str(current_app.config.get("PUBLIC_BASE_URL") or request.url_root).rstrip("/")
    payload = {
        "full_name": order.get("phone", "Guest"),
        "email": "guest@autoprinter.com",
        "amount": str(order.get("total") or 0),
        "metadata": {
            "order_id": order_id,
            "queue_no": order.get("queue_no"),
            "pages": order.get("pages"),
            "copies": order.get("copies"),
            "ptype": order.get("ptype"),
            "total": order.get("total"),
        },
        "redirect_url": f"{public_base_url}/paymently-success/{order_id}",
        "cancel_url": f"{public_base_url}/paymently-cancel/{order_id}",
        "webhook_url": f"{public_base_url}/paymently-webhook",
        "return_type": "GET"
    }
    headers = {
        "RT-UDDOKTAPAY-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(create_url, headers=headers, json=payload, timeout=20)
        try:
            data = response.json()
        except Exception:
            data = {
                "status_code": response.status_code,
                "body": (response.text or "")[:2000],
            }
    except Exception as exc:
        return render_template(
            "message.html",
            title="Payment Error",
            body_html=f"Payment create error: {exc}",
        ), 500

    payment_url = data.get("payment_url") or data.get("url") or data.get("redirect_url")
    order["gateway_response"] = data
    order["payment_created_time"] = int(time.time())

    if not payment_url:
        save_orders(orders)
        return render_template(
            "message.html",
            title="Payment Error",
            body_html="Payment link not received from gateway.",
        ), 500

    order["status"] = "PAYMENT_LINK_CREATED"
    order["payment_url"] = payment_url
    save_orders(orders)
    return redirect(payment_url)


@public_bp.route("/paymently-success/<order_id>")
def paymently_success(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404

    query_data = request.args.to_dict(flat=True)
    order["paymently_success_query"] = query_data

    invoice_id = request.args.get("invoice_id")
    if invoice_id:
        order["trxid"] = invoice_id
    save_orders(orders)

    if invoice_id:
        api_key = str(current_app.config.get("PAYMENTLY_API_KEY") or "").strip()
        verify_url = str(current_app.config.get("PAYMENTLY_VERIFY_URL") or "").strip()
        if api_key and verify_url:
            headers = {
                "RT-UDDOKTAPAY-API-KEY": api_key,
                "Content-Type": "application/json",
            }
            try:
                resp = requests.post(verify_url, headers=headers, json={"invoice_id": invoice_id}, timeout=10)
                verify_data = resp.json()
                status_value = verify_data.get("status")
                if _payment_status_is_success(status_value):
                    mark_order_paid_for_queue(order_id)
            except Exception:
                pass

    return redirect(_status_page_url(order_id))


@public_bp.route("/paymently-cancel/<order_id>")
def paymently_cancel(order_id):
    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found!"), 404

    if order.get("status") in {"PAYMENT_LINK_CREATED", "WAITING_PAYMENT", "PAYMENT_PENDING"}:
        order["status"] = "PAYMENT_PENDING"
        save_orders(orders)

    body_html = (
        "You cancelled the payment or closed the gateway.<br>"
        f"<a class='btn btn-primary w-full mt-3' href='/pay/{order_id}'>Try Payment Again</a>"
    )
    return render_template("message.html", title="Payment Cancelled", body_html=body_html)


@public_bp.route("/paymently-webhook", methods=["POST"])
def paymently_webhook():
    payload_json = request.get_json(silent=True) or {}
    payload_form = dict(request.form) if request.form else {}
    payload = payload_json if payload_json else payload_form

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    order_id = (
        metadata.get("order_id")
        or payload.get("order_id")
        or payload.get("reference")
        or request.args.get("order_id")
    )
    if not order_id:
        return jsonify({"ok": False, "error": "order_id missing"}), 400

    orders = load_orders()
    order = find_order(orders, str(order_id))
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    order["paymently_webhook"] = payload
    trxid = (
        payload.get("invoice_id")
        or payload.get("transactionId")
        or payload.get("transaction_id")
        or payload.get("trxid")
        or payload.get("payment_id")
        or ""
    )
    if trxid:
        order["trxid"] = str(trxid)
    save_orders(orders)

    status_value = (
        payload.get("status")
        or payload.get("payment_status")
        or payload.get("event")
    )
    if not _payment_status_is_success(status_value):
        return jsonify({"ok": True, "message": "ignored non-success webhook"}), 202

    admitted = mark_order_paid_for_queue(str(order_id))
    if not admitted:
        return jsonify({"ok": False, "error": "order not found"}), 404

    return jsonify({
        "ok": True,
        "order_id": order_id,
        "status": admitted.get("status"),
    })


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
            # Backward-compatible alias used by the current status template.
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

    # If not paid yet, we can't place them into paid-time FIFO queue math.
    if not paid_time:
        return response()

    # FIFO queue = jobs paid_time sorted, that are already admitted for printing.
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


# ── History routes ────────────────────────────────────────────
@public_bp.route("/history")
def history():
    session_id = init_session()
    my_orders = get_user_orders(session_id)

    return render_template(
        "history.html",
        title="AutoPrinter • History",
        orders=my_orders[:20],
    )


# ── Public QR ─────────────────────────────────────────────────
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
