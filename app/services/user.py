import os
import json
import hashlib
from datetime import datetime
from flask import current_app

def _get_users_db_path():
    return current_app.config.get("USERS_DB", "users.json")

def load_users():
    db_path = _get_users_db_path()
    if not os.path.exists(db_path):
        return []
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_users(users):
    db_path = _get_users_db_path()
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_user(phone):
    users = load_users()
    for u in users:
        if u.get("phone") == phone:
            return u
    return None

def register_user(phone, name, password):
    phone = str(phone).strip()
    users = load_users()
    for u in users:
        if str(u.get("phone")).strip() == phone:
            return False, "Phone number already registered"
    
    new_user = {
        "phone": phone,
        "name": name,
        "password": hash_password(password),
        "balance": 0.0,
        "due": 0.0,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    users.append(new_user)
    save_users(users)
    return True, new_user

def authenticate_user(phone, password):
    phone = str(phone).strip()
    user = get_user(phone)
    if not user:
        return False, "User not found"
    
    if user.get("password") == hash_password(password):
        return True, user
    return False, "Incorrect password"

def update_user_balance(phone, amount_to_add):
    phone = str(phone).strip()
    users = load_users()
    for u in users:
        if str(u.get("phone")).strip() == phone:
            current_balance = float(u.get("balance", 0.0))
            u["balance"] = current_balance + float(amount_to_add)
            save_users(users)
            return True, u["balance"]
    return False, 0.0
