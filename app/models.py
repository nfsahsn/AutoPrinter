from app.extensions import db
import json

class User(db.Model):
    __tablename__ = "users"
    phone = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(128), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    due = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.String(50))
    
    orders = db.relationship("Order", backref="user", lazy=True)
    deposits = db.relationship("Deposit", backref="user", lazy=True)

    def to_dict(self):
        return {
            "phone": self.phone,
            "name": self.name,
            "password": self.password,
            "balance": self.balance,
            "due": self.due,
            "created_at": self.created_at
        }

class Order(db.Model):
    __tablename__ = "orders"
    order_id = db.Column(db.String(20), primary_key=True)
    queue_no = db.Column(db.Integer)
    session_id = db.Column(db.String(100))
    phone = db.Column(db.String(20), db.ForeignKey("users.phone"), nullable=False)
    filename = db.Column(db.String(255))
    filepath = db.Column(db.String(500))
    pages = db.Column(db.Integer)
    copies = db.Column(db.Integer)
    ptype = db.Column(db.String(20))
    total = db.Column(db.Float)
    status = db.Column(db.String(50))
    time = db.Column(db.String(50))
    created_time = db.Column(db.Integer)
    paid_time = db.Column(db.Integer, nullable=True)
    printed_time = db.Column(db.Integer, nullable=True)
    print_start_time = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "queue_no": self.queue_no,
            "session_id": self.session_id,
            "phone": self.phone,
            "filename": self.filename,
            "filepath": self.filepath,
            "pages": self.pages,
            "copies": self.copies,
            "ptype": self.ptype,
            "total": self.total,
            "status": self.status,
            "time": self.time,
            "created_time": self.created_time,
            "paid_time": self.paid_time,
            "printed_time": self.printed_time,
            "print_start_time": self.print_start_time
        }

class Deposit(db.Model):
    __tablename__ = "deposits"
    deposit_id = db.Column(db.String(50), primary_key=True)
    phone = db.Column(db.String(20), db.ForeignKey("users.phone"), nullable=False)
    amount = db.Column(db.Float)
    status = db.Column(db.String(50))
    payment_url = db.Column(db.String(500))
    created_at = db.Column(db.String(50))
    completed_at = db.Column(db.String(50), nullable=True)
    invoice_id = db.Column(db.String(100), nullable=True)
    gateway_response = db.Column(db.Text, nullable=True)  # Store as JSON string

    def to_dict(self):
        try:
            gw_resp = json.loads(self.gateway_response) if self.gateway_response else {}
        except Exception:
            gw_resp = {}
        return {
            "deposit_id": self.deposit_id,
            "phone": self.phone,
            "amount": self.amount,
            "status": self.status,
            "payment_url": self.payment_url,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "invoice_id": self.invoice_id,
            "gateway_response": gw_resp
        }
