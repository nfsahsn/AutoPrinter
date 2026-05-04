import os
import json
from app import create_app
from app.extensions import db
from app.models import User, Order, Deposit
from config import Config

def run_migration():
    app = create_app(Config)
    with app.app_context():
        # Migrate Users
        print("Migrating users...")
        users_file = app.config.get("USERS_DB", "users.json")
        if os.path.exists(users_file):
            with open(users_file, "r", encoding="utf-8") as f:
                try:
                    users_data = json.load(f)
                    for u in users_data:
                        if not User.query.get(u["phone"]):
                            user = User(
                                phone=u["phone"],
                                name=u.get("name", "Unknown"),
                                password=u["password"],
                                balance=u.get("balance", 0.0),
                                due=u.get("due", 0.0),
                                created_at=u.get("created_at", "")
                            )
                            db.session.add(user)
                    db.session.commit()
                    print(f"Migrated {len(users_data)} users.")
                except Exception as e:
                    print("Error loading users.json:", e)

        # Migrate Orders
        print("Migrating orders...")
        orders_file = app.config.get("DB_FILE", "orders.json")
        if os.path.exists(orders_file):
            with open(orders_file, "r", encoding="utf-8") as f:
                try:
                    orders_data = json.load(f)
                    count = 0
                    for o in orders_data:
                        if not Order.query.get(o["order_id"]):
                            # Ensure the user exists, if not, create a dummy user to satisfy foreign key
                            phone = o.get("phone")
                            if not phone:
                                phone = "guest"
                            if phone and not User.query.get(phone):
                                dummy = User(phone=phone, name="Guest", password="none")
                                db.session.add(dummy)
                                db.session.commit()

                            order = Order(
                                order_id=o["order_id"],
                                queue_no=o.get("queue_no"),
                                session_id=o.get("session_id"),
                                phone=phone,
                                filename=o.get("filename"),
                                filepath=o.get("filepath"),
                                pages=o.get("pages"),
                                copies=o.get("copies"),
                                ptype=o.get("ptype"),
                                total=o.get("total"),
                                status=o.get("status"),
                                time=o.get("time"),
                                created_time=o.get("created_time"),
                                paid_time=o.get("paid_time"),
                                printed_time=o.get("printed_time"),
                                print_start_time=o.get("print_start_time")
                            )
                            db.session.add(order)
                            count += 1
                    db.session.commit()
                    print(f"Migrated {count} orders.")
                except Exception as e:
                    print("Error loading orders.json:", e)

        # Migrate Deposits
        print("Migrating deposits...")
        deposits_file = app.config.get("DEPOSITS_DB", "deposits.json")
        if os.path.exists(deposits_file):
            with open(deposits_file, "r", encoding="utf-8") as f:
                try:
                    deposits_data = json.load(f)
                    count = 0
                    for d in deposits_data:
                        if not Deposit.query.get(d["deposit_id"]):
                            phone = d.get("phone")
                            if not phone:
                                phone = "guest"
                            if phone and not User.query.get(phone):
                                dummy = User(phone=phone, name="Guest", password="none")
                                db.session.add(dummy)
                                db.session.commit()

                            gw_resp = json.dumps(d.get("gateway_response", {}))
                            deposit = Deposit(
                                deposit_id=d["deposit_id"],
                                phone=phone,
                                amount=d.get("amount"),
                                status=d.get("status"),
                                payment_url=d.get("payment_url"),
                                created_at=d.get("created_at"),
                                completed_at=d.get("completed_at"),
                                invoice_id=d.get("invoice_id"),
                                gateway_response=gw_resp
                            )
                            db.session.add(deposit)
                            count += 1
                    db.session.commit()
                    print(f"Migrated {count} deposits.")
                except Exception as e:
                    print("Error loading deposits.json:", e)

        print("Migration complete!")

if __name__ == "__main__":
    run_migration()
