from flask import Blueprint, request, redirect, url_for, session, render_template

from app.services.user import authenticate_user, register_user

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["POST"])
def login():
    phone = request.form.get("phone")
    password = request.form.get("password")
    
    if not phone or not password:
        return render_template("message.html", title="Login Failed", body_html="Phone and password are required.", headline="❌ Error"), 400
        
    success, user_or_msg = authenticate_user(phone, password)
    if success:
        session["user_phone"] = user_or_msg["phone"]
        return redirect(url_for("public.print_page"))
    else:
        return render_template("message.html", title="Login Failed", body_html=user_or_msg, headline="❌ Error"), 401

@auth_bp.route("/register", methods=["POST"])
def register():
    phone = request.form.get("phone")
    name = request.form.get("name")
    password = request.form.get("password")
    
    if not phone or not name or not password:
        return render_template("message.html", title="Registration Failed", body_html="All fields are required.", headline="❌ Error"), 400
        
    success, user_or_msg = register_user(phone, name, password)
    if success:
        session["user_phone"] = user_or_msg["phone"]
        return redirect(url_for("public.wallet"))
    else:
        return render_template("message.html", title="Registration Failed", body_html=user_or_msg, headline="❌ Error"), 400

@auth_bp.route("/logout")
def logout():
    session.pop("user_phone", None)
    return redirect(url_for("public.index"))
