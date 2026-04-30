import os
import json
import time
from flask import (
    Blueprint, request, redirect, url_for, session,
    render_template, current_app,
)
from app.services.order import load_orders, save_orders, find_order
from app.services.printer import print_pdf_windows, PRINTER_LOCK
from app.services.queue_worker import mark_order_paid_for_queue
from app.utils.helpers import admin_required

admin_bp = Blueprint("admin", __name__)


def load_admin_password():
    pass_path = current_app.config["ADMIN_PASS_PATH"]
    default = current_app.config["ADMIN_PASSWORD_DEFAULT"]
    if not os.path.exists(pass_path):
        return default
    try:
        with open(pass_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("password", default)
    except Exception:
        return default


def save_admin_password(new_pass):
    pass_path = current_app.config["ADMIN_PASS_PATH"]
    with open(pass_path, "w", encoding="utf-8") as f:
        json.dump({"password": new_pass}, f, indent=2)


# ── Admin auth ────────────────────────────────────────────────
@admin_bp.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    current_pass = load_admin_password()
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == current_pass:
            session["admin_logged_in"] = True
            return redirect(url_for("admin.admin_panel"))
        error = "Wrong password"

    return render_template("admin_login.html", title="Admin Login", error=error)


@admin_bp.route("/admin-logout")
def admin_logout():
    session["admin_logged_in"] = False
    return redirect(url_for("public.print_page"))


# ── Admin panel — Orders ──────────────────────────────────────
@admin_bp.route("/admin")
def admin_panel():
    if not admin_required():
        return redirect(url_for("admin.admin_login"))

    orders = list(reversed(load_orders()))
    return render_template(
        "admin.html",
        title="Admin Panel",
        orders=orders,
        active_tab="orders",
    )



# ── Admin — Reprint ───────────────────────────────────────────
@admin_bp.route("/admin-reprint/<order_id>")
def admin_reprint(order_id):
    if not admin_required():
        return redirect(url_for("admin.admin_login"))

    orders = load_orders()
    order = find_order(orders, order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found"), 404

    if not order.get("filepath") or not os.path.exists(order.get("filepath", "")):
        return render_template(
            "message.html", title="Reprint Failed",
            headline="❌ File not found (may have been auto-deleted after 24h).",
            headline_class="text-danger",
        ), 400

    try:
        with PRINTER_LOCK:
            print_pdf_windows(order["filepath"], order["copies"])
            time.sleep(1)

        order["status"] = "PRINTED"
        order["printed_time"] = int(time.time())
        save_orders(orders)
        return redirect(url_for("admin.admin_panel"))

    except Exception as e:
        order["status"] = "PRINT_FAILED"
        save_orders(orders)
        return render_template(
            "message.html", title="Reprint Failed",
            headline=f"❌ {e}", headline_class="text-danger",
        ), 500


@admin_bp.route("/admin-mark-paid/<order_id>", methods=["POST"])
def admin_mark_paid(order_id):
    if not admin_required():
        return redirect(url_for("admin.admin_login"))

    order = mark_order_paid_for_queue(order_id)
    if not order:
        return render_template("message.html", title="Error", body_html="Order not found"), 404

    return redirect(url_for("admin.admin_panel"))


# ── Admin — Change password ───────────────────────────────────
@admin_bp.route("/admin-change-password", methods=["GET", "POST"])
def admin_change_password():
    if not admin_required():
        return redirect(url_for("admin.admin_login"))

    current_pass = load_admin_password()
    error = None

    if request.method == "POST":
        old_pass = request.form.get("old_password", "")
        new_pass = request.form.get("new_password", "")
        confirm_pass = request.form.get("confirm_password", "")

        if old_pass != current_pass:
            error = "Old password is wrong"
        elif len(new_pass) < 4:
            error = "New password too short"
        elif new_pass != confirm_pass:
            error = "Passwords do not match"
        else:
            save_admin_password(new_pass)
            session["admin_logged_in"] = False
            body = "<p class='text-muted'>Login again</p><a class='btn btn-primary w-full' href='/admin-login'>Login</a>"
            return render_template(
                "message.html", title="Password Changed",
                headline="✅ Password Updated", center=True, body_html=body,
            )

    return render_template("admin_change_password.html", title="Change Password", error=error)
