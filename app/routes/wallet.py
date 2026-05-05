from flask import Blueprint, request, redirect, url_for, session, render_template, current_app, flash, jsonify
from app.services.user import get_user
from app.services.wallet import create_deposit_session, get_user_deposits, process_webhook
from app.utils.helpers import login_required

wallet_bp = Blueprint("wallet", __name__)

@wallet_bp.route("/wallet")
@login_required
def dashboard():
    user = get_user(session["user_phone"])
    if not user:
        session.pop("user_phone", None)
        return redirect(url_for("public.index"))
        
    deposits = get_user_deposits(session["user_phone"])
    return render_template("wallet.html", title="Wallet Dashboard", user=user, deposits=deposits)

@wallet_bp.route("/wallet/topup", methods=["POST"])
@login_required
def topup():
    amount = request.form.get("amount")
    if not amount:
        flash("Amount is required", "error")
        return redirect(url_for("wallet.dashboard"))
        
    success, payment_url_or_msg = create_deposit_session(session["user_phone"], amount)
    if success:
        return redirect(payment_url_or_msg)
    else:
        flash(payment_url_or_msg, "error")
        return redirect(url_for("wallet.dashboard"))

@wallet_bp.route("/wallet/success/<deposit_id>")
def success(deposit_id):
    # This route is visited after gateway success
    return render_template("message.html", title="Payment Success", headline="✅ Processing Deposit", body_html="Your deposit is being processed. It will reflect in your wallet shortly.<br><a class='btn btn-primary w-full mt-3' href='/wallet'>Go to Wallet</a>")

@wallet_bp.route("/wallet/cancel/<deposit_id>")
def cancel(deposit_id):
    return render_template("message.html", title="Payment Cancelled", headline="❌ Cancelled", body_html="You cancelled the deposit.<br><a class='btn btn-primary w-full mt-3' href='/wallet'>Go to Wallet</a>")

@wallet_bp.route("/wallet/webhook", methods=["POST"])
def webhook():
    # Validate XPay API key header for security
    incoming_key = request.headers.get("MHS-PIPRAPAY-API-KEY", "")
    expected_key = current_app.config.get("XPAY_API_KEY", "")
    if incoming_key and expected_key and incoming_key != expected_key:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    
    payload_json = request.get_json(silent=True) or {}
    payload_form = dict(request.form) if request.form else {}
    payload = payload_json if payload_json else payload_form
    
    success, msg = process_webhook(payload)
    if success:
        return jsonify({"ok": True, "message": msg}), 200
    else:
        return jsonify({"ok": False, "error": msg}), 400
