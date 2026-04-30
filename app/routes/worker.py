import hmac
import os

from flask import Blueprint, current_app, jsonify, request, send_file, url_for

from app.services.order import find_order, get_job_pages, load_orders
from app.services.queue_worker import claim_next_job_for_printing, finish_print_job

worker_bp = Blueprint("worker", __name__, url_prefix="/worker")


def _request_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.headers.get("X-Worker-Token", "").strip()


def _require_worker_auth():
    expected = str(current_app.config.get("WORKER_API_TOKEN") or "").strip()
    if not expected:
        return jsonify({"ok": False, "error": "worker token is not configured"}), 503

    provided = _request_token()
    if not provided or not hmac.compare_digest(provided, expected):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    return None


def _public_order_payload(order):
    return {
        "order_id": order.get("order_id"),
        "queue_no": order.get("queue_no"),
        "filename": order.get("filename"),
        "pages": int(order.get("pages") or 0),
        "copies": int(order.get("copies") or 1),
        "ptype": order.get("ptype") or "bw",
        "total_pages": get_job_pages(order),
        "total": order.get("total"),
        "status": order.get("status"),
        "file_url": url_for("worker.download_job_file", order_id=order.get("order_id"), _external=True),
    }


@worker_bp.route("/next-job")
def next_job():
    auth_error = _require_worker_auth()
    if auth_error:
        return auth_error

    order = claim_next_job_for_printing()
    if not order:
        return jsonify({"ok": True, "job": None})

    return jsonify({"ok": True, "job": _public_order_payload(order)})


@worker_bp.route("/jobs/<order_id>/file")
def download_job_file(order_id):
    auth_error = _require_worker_auth()
    if auth_error:
        return auth_error

    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    if order.get("status") != "PRINTING":
        return jsonify({"ok": False, "error": "order is not claimed for printing"}), 409

    filepath = order.get("filepath")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"ok": False, "error": "file not found"}), 404

    return send_file(filepath, mimetype="application/pdf", as_attachment=True, download_name=order.get("filename"))


@worker_bp.route("/jobs/<order_id>/complete", methods=["POST"])
def complete_job(order_id):
    auth_error = _require_worker_auth()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status") or "").upper()
    success = status == "PRINTED"
    failed = status == "PRINT_FAILED"
    if not success and not failed:
        return jsonify({"ok": False, "error": "status must be PRINTED or PRINT_FAILED"}), 400

    order = finish_print_job(order_id, success=success, error=payload.get("error"))
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404

    return jsonify({"ok": True, "order": _public_order_payload(order)})


@worker_bp.route("/health")
def health():
    auth_error = _require_worker_auth()
    if auth_error:
        return auth_error
    return jsonify({"ok": True})
