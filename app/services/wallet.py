import os
import json
import time
import uuid
import requests
from datetime import datetime
from flask import current_app
from app.services.user import update_user_balance

def _get_deposits_db_path():
    return current_app.config.get("DEPOSITS_DB", "deposits.json")

def load_deposits():
    db_path = _get_deposits_db_path()
    if not os.path.exists(db_path):
        return []
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_deposits(deposits):
    db_path = _get_deposits_db_path()
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(deposits, f, indent=2)

def create_deposit_session(phone, amount):
    amount = float(amount)
    if amount < 20.0:
        return False, "Minimum deposit is 20 taka."
        
    deposits = load_deposits()
    deposit_id = str(uuid.uuid4())[:12]
    
    api_key = str(current_app.config.get("PAYMENTLY_API_KEY") or "").strip()
    create_url = str(current_app.config.get("PAYMENTLY_CREATE_URL") or "").strip()
    
    if not api_key or not create_url:
        return False, "Payment gateway is not configured."

    public_base_url = str(current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    payload = {
        "full_name": phone,
        "email": "user@autoprinter.com",
        "amount": str(amount),
        "metadata": {
            "deposit_id": deposit_id,
            "phone": phone,
            "type": "wallet_deposit"
        },
        "redirect_url": f"{public_base_url}/wallet/success/{deposit_id}",
        "cancel_url": f"{public_base_url}/wallet/cancel/{deposit_id}",
        "webhook_url": f"{public_base_url}/wallet/webhook",
        "return_type": "GET"
    }
    
    headers = {
        "RT-UDDOKTAPAY-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(create_url, headers=headers, json=payload, timeout=20)
        data = response.json()
        payment_url = data.get("payment_url") or data.get("url") or data.get("redirect_url")
        
        if not payment_url:
            return False, "Payment link not received from gateway."
            
        new_deposit = {
            "deposit_id": deposit_id,
            "phone": phone,
            "amount": amount,
            "status": "PENDING",
            "payment_url": payment_url,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "gateway_response": data
        }
        deposits.append(new_deposit)
        save_deposits(deposits)
        
        return True, payment_url

    except Exception as e:
        return False, f"Gateway error: {str(e)}"

def verify_and_credit_deposit(deposit_id, invoice_id=None):
    deposits = load_deposits()
    deposit = next((d for d in deposits if d.get("deposit_id") == deposit_id), None)
    
    if not deposit:
        return False, "Deposit not found."
        
    if deposit.get("status") == "COMPLETED":
        return True, "Already completed."

    api_key = str(current_app.config.get("PAYMENTLY_API_KEY") or "").strip()
    verify_url = str(current_app.config.get("PAYMENTLY_VERIFY_URL") or "").strip()
    
    if invoice_id and api_key and verify_url:
        headers = {
            "RT-UDDOKTAPAY-API-KEY": api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(verify_url, headers=headers, json={"invoice_id": invoice_id}, timeout=10)
            verify_data = resp.json()
            status_value = str(verify_data.get("status", "")).strip().lower()
            
            success_statuses = {"completed", "complete", "success", "successful", "paid", "payment_success", "payment.completed", "captured"}
            
            if status_value in success_statuses:
                deposit["status"] = "COMPLETED"
                deposit["invoice_id"] = invoice_id
                deposit["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_deposits(deposits)
                
                update_user_balance(deposit["phone"], deposit["amount"])
                return True, "Wallet credited successfully."
        except Exception:
            pass
            
    return False, "Verification failed or payment not completed."

def get_user_deposits(phone):
    deposits = load_deposits()
    user_deps = [d for d in deposits if d.get("phone") == phone]
    user_deps.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return user_deps

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
        
    invoice_id = payload.get("invoice_id") or payload.get("transactionId") or payload.get("trxid")
    
    success, msg = verify_and_credit_deposit(deposit_id, invoice_id=invoice_id)
    return success, msg
