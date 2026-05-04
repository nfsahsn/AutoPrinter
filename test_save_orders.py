import os
from app import create_app
from config import Config
from app.services.order import load_orders, save_orders
import uuid
import time
from datetime import datetime

app = create_app(Config)
with app.app_context():
    try:
        orders = load_orders()
        print(f"Loaded {len(orders)} orders")
        
        order_id = str(uuid.uuid4())[:8]
        orders.append({
            "queue_no": len(orders) + 1,
            "order_id": order_id,
            "session_id": "test",
            "phone": "01700000000",
            "filename": "test.pdf",
            "filepath": "/tmp/test.pdf",
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
        print("Saved orders successfully")
    except Exception as e:
        print("Error saving orders:")
        import traceback
        traceback.print_exc()
