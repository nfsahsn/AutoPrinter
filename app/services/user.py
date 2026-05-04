import os
import json
import hashlib
from datetime import datetime
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app

from app.extensions import db
from app.models import User

def load_users():
    return [u.to_dict() for u in User.query.all()]

def save_users(users):
    pass # No longer needed, handled by SQLAlchemy db.session.commit()

def hash_password(password):
    return generate_password_hash(password)

def _legacy_hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_user(phone):
    user = User.query.get(phone)
    if user:
        return user.to_dict()
    return None

def register_user(phone, name, password):
    phone = str(phone).strip()
    if User.query.get(phone):
        return False, "Phone number already registered"
    
    user = User(
        phone=phone,
        name=name,
        password=hash_password(password),
        balance=0.0,
        due=0.0,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(user)
    db.session.commit()
    return True, user.to_dict()

def authenticate_user(phone, password):
    phone = str(phone).strip()
    user_db = User.query.get(phone)
    if not user_db:
        return False, "User not found"
    
    if user_db.password.startswith("scrypt:") or user_db.password.startswith("pbkdf2:"):
        if check_password_hash(user_db.password, password):
            return True, user_db.to_dict()
    elif user_db.password == _legacy_hash_password(password):
        user_db.password = generate_password_hash(password)
        db.session.commit()
        return True, user_db.to_dict()
        
    return False, "Incorrect password"

def update_user_balance(phone, amount_to_add):
    phone = str(phone).strip()
    user = User.query.get(phone)
    if user:
        user.balance = float(user.balance or 0.0) + float(amount_to_add)
        db.session.commit()
        return True, user.balance
    return False, 0.0

def update_user_password(phone, new_password):
    phone = str(phone).strip()
    user = User.query.get(phone)
    if user:
        user.password = hash_password(new_password)
        db.session.commit()
        return True, "Password updated successfully"
    return False, "User not found"
