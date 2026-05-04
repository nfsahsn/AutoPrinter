import os
import fitz
import qrcode
from flask import session, current_app, redirect, url_for
from functools import wraps

def safe_delete_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            return True
    except:
        pass
    return False

def get_pdf_pages(filepath):
    try:
        doc = fitz.open(filepath)
        pages = doc.page_count
        doc.close()
        return pages
    except:
        return 1

def make_receipt_qr(order_id):
    qr_filename = f"qr_{order_id}.png"
    qr_path = os.path.join(current_app.config['STATIC_FOLDER'], qr_filename)
    url = f"{current_app.config['PUBLIC_BASE_URL']}/status/{order_id}"
    img = qrcode.make(url)
    img.save(qr_path)
    return f"/static/{qr_filename}"

def admin_required():
    return session.get("admin_logged_in") is True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_phone" not in session:
            return redirect(url_for('public.index'))
        return f(*args, **kwargs)
    return decorated_function
