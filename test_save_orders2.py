import uuid
from app import create_app
from config import Config
from app.services.order import load_orders, save_orders
import time
from datetime import datetime

app = create_app(Config)
with app.app_context():
    try:
        orders = load_orders()
        orders.append({
            "queue_no": 999,
            "order_id": str(uuid.uuid4())[:8],
            "session_id": "test",
            "phone": "99999999999", # Non-existent user
            "filename": "test2.pdf",
            "filepath": "/tmp/test2.pdf",
            "pages": 1,
            "copies": 1,
            "ptype": "bw",
            "total": 2.0,
            "status": "PAYMENT_PENDING",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "created_time": int(time.time()),
            "printed_time": None,
        })
        save_orders(orders)
        print("Success without user")
    except Exception as e:
        print("Error:", e)
