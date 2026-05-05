import os
import json
import time
import uuid
import requests
from datetime import datetime
from flask import current_app
from app.services.user import update_user_balance

from app.extensions import db
from app.models import Deposit

def load_deposits():
    return [d.to_dict() for d in Deposit.query.all()]

def save_deposits(deposits):
    pass # No longer needed


def create_deposit_session(phone, amount):
    amount = float(amount)
    if amount < 20.0:
        return False, "Minimum deposit is 20 taka."
        
    deposit_id = str(uuid.uuid4())[:12]
    
    api_key = str(current_app.config.get("XPAY_API_KEY") or "").strip()
    create_url = str(current_app.config.get("XPAY_CREATE_URL") or "").strip()
    
    if not api_key or not create_url:
        return False, "Payment gateway is not configured."

    public_base_url = str(current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    payload = {
        "full_name": phone,
        "email_address": "user@autoprinter.com",
        "mobile_number": phone,
        "amount": str(amount),
        "currency": "BDT",
        "metadata": {
            "deposit_id": deposit_id,
            "phone": phone,
            "type": "wallet_deposit"
        },
        "return_url": f"{public_base_url}/wallet/success/{deposit_id}",
        "cancel_url": f"{public_base_url}/wallet/cancel/{deposit_id}",
        "webhook_url": f"{public_base_url}/wallet/webhook"
    }
    
    headers = {
        "MHS-PIPRAPAY-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(create_url, headers=headers, json=payload, timeout=20)
        data = response.json()
        
        # In PipraPay v3, response is {"pp_id": "...", "pp_url": "..."}
        payment_url = data.get("pp_url") or data.get("payment_url") or data.get("url")
        
        if not payment_url:
            error_msg = data.get("error", {}).get("message", "Payment link not received.")
            return False, f"Gateway error: {error_msg}"
            
        new_deposit = Deposit(
            deposit_id=deposit_id,
            phone=phone,
            amount=amount,
            status="PENDING",
            payment_url=payment_url,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            gateway_response=json.dumps(data)
        )
        db.session.add(new_deposit)
        db.session.commit()
        
        return True, payment_url

    except Exception as e:
        return False, f"Gateway error: {str(e)}"

def verify_and_credit_deposit(deposit_id, pp_id=None):
    deposit = Deposit.query.get(deposit_id)
    
    if not deposit:
        return False, "Deposit not found."
        
    if deposit.status == "COMPLETED":
        return True, "Already completed."

    api_key = str(current_app.config.get("XPAY_API_KEY") or "").strip()
    verify_url = str(current_app.config.get("XPAY_VERIFY_URL") or "").strip()
    
    if pp_id and api_key and verify_url:
        headers = {
            "MHS-PIPRAPAY-API-KEY": api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(verify_url, headers=headers, json={"pp_id": pp_id}, timeout=10)
            verify_data = resp.json()
            
            # PipraPay v3 verify response usually contains 'status'
            # If status is missing, we check if response contains success data
            status_value = str(verify_data.get("status", "")).strip().lower()
            
            success_statuses = {"completed", "complete", "success", "successful", "paid", "payment_success", "payment.completed", "captured"}
            
            if status_value in success_statuses or verify_data.get("pp_id"):
                deposit.status = "COMPLETED"
                deposit.invoice_id = pp_id
                deposit.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.session.commit()
                
                update_user_balance(deposit.phone, deposit.amount)
                return True, "Wallet credited successfully."
        except Exception:
            pass
            
    return False, "Verification failed or payment not completed."

def get_user_deposits(phone):
    deposits = Deposit.query.filter_by(phone=phone).order_by(Deposit.created_at.desc()).all()
    return [d.to_dict() for d in deposits]

def process_webhook(payload):
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        
    deposit_id = metadata.get("deposit_id")
    if not deposit_id:
        return False, "deposit_id missing"
        
    status_value = str(payload.get("status") or payload.get("payment_status") or payload.get("event") or "").strip().lower()
    success_statuses = {"completed", "complete", "success", "successful", "paid", "payment_success", "payment.completed", "captured"}
    
    if status_value not in success_statuses:
        return True, "ignored non-success webhook"
        
    pp_id = payload.get("pp_id") or payload.get("invoice_id")
    
    success, msg = verify_and_credit_deposit(deposit_id, pp_id=pp_id)
    return success, msg
