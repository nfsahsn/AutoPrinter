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
from app.services.user import update_user_balance, update_user_password
from app.utils.helpers import admin_required
from werkzeug.security import generate_password_hash, check_password_hash

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
    hashed_pass = generate_password_hash(new_pass)
    with open(pass_path, "w", encoding="utf-8") as f:
        json.dump({"password": hashed_pass}, f, indent=2)


# ── Admin auth ────────────────────────────────────────────────
@admin_bp.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    current_pass = load_admin_password()
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if current_pass.startswith("scrypt:") or current_pass.startswith("pbkdf2:"):
            if check_password_hash(current_pass, password):
                session["admin_logged_in"] = True
                return redirect(url_for("admin.admin_panel"))
        else:
            # Fallback to plaintext and auto-upgrade
            if password == current_pass:
                save_admin_password(password)
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

    tab = request.args.get("tab", "dashboard")

    if tab == "dashboard":
        orders = load_orders()
        from datetime import datetime, timedelta
        import json
        
        # Prepare last 7 days
        today = datetime.now().date()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        revenue_data = {d: 0 for d in dates}
        pages_data = {d: 0 for d in dates}
        
        total_revenue = 0
        total_pages = 0
        total_users = 0
        
        for o in orders:
            if o.get("status") in ["PRINTED", "PRINTING", "QUEUED", "WAITING_QUEUE"]:
                total_revenue += float(o.get("total", 0))
                total_pages += int(o.get("pages", 0)) * int(o.get("copies", 1))
                
                # Check date
                time_str = str(o.get("time", ""))
                if time_str[:10] in revenue_data:
                    day = time_str[:10]
                    revenue_data[day] += float(o.get("total", 0))
                    pages_data[day] += int(o.get("pages", 0)) * int(o.get("copies", 1))
                    
        from app.services.user import load_users
        total_users = len(load_users())
                    
        return render_template(
            "admin.html",
            title="Admin Dashboard",
            active_tab="dashboard",
            chart_labels=json.dumps(dates),
            chart_revenue=json.dumps(list(revenue_data.values())),
            chart_pages=json.dumps(list(pages_data.values())),
            total_revenue=total_revenue,
            total_pages=total_pages,
            total_users=total_users
        )
    elif tab == "users":
        from app.services.user import load_users
        users = load_users()
        return render_template(
            "admin.html",
            title="Admin Panel - Users",
            users=users,
            active_tab="users",
        )
    else:
        orders = list(reversed(load_orders()))
        return render_template(
            "admin.html",
            title="Admin Panel - Orders",
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

# ── Admin — User Management ───────────────────────────────────
@admin_bp.route("/admin/user/balance/<phone>", methods=["POST"])
def admin_user_balance(phone):
    if not admin_required():
        return redirect(url_for("admin.admin_login"))
        
    amount = request.form.get("amount")
    try:
        amount = float(amount)
        update_user_balance(phone, amount)
    except (TypeError, ValueError):
        pass
        
    return redirect(url_for("admin.admin_panel", tab="users"))

@admin_bp.route("/admin/user/password/<phone>", methods=["POST"])
def admin_user_password(phone):
    if not admin_required():
        return redirect(url_for("admin.admin_login"))
        
    new_password = request.form.get("password")
    if new_password and len(new_password) >= 4:
        update_user_password(phone, new_password)
        
    return redirect(url_for("admin.admin_panel", tab="users"))
