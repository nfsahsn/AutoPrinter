import time
import threading
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.services.order import (
    load_orders,
    save_orders,
    get_job_pages,
    get_effective_used_pages,
)
from app.services.printer import print_pdf, PRINTER_LOCK

_QUEUE_ADMISSION_INTERVAL_SEC = 2
_PRINTER_WORKER_IDLE_SLEEP_SEC = 2


def _now_ts() -> int:
    return int(time.time())


def _sort_by_paid_time_fifo(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def paid_time_key(o: Dict[str, Any]) -> Tuple[int, str]:
        try:
            paid_time = int(o.get("paid_time") or 0)
        except Exception:
            paid_time = 0
        return paid_time, str(o.get("order_id") or "")

    # Older paid first; if missing, treat as 0 so it goes first (but those should
    # generally not be QUEUED/WAITING_QUEUE in well-formed states).
    return sorted(orders, key=paid_time_key)


def _find_next_job_to_print(orders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    queued = [o for o in orders if o.get("status") == "QUEUED" and o.get("paid_time")]
    if not queued:
        return None
    queued = _sort_by_paid_time_fifo(queued)
    return queued[0]


def _find_printing_job(orders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for o in orders:
        if o.get("status") == "PRINTING":
            return o
    return None


def claim_next_job_for_printing(orders: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """
    Mark the next QUEUED job as PRINTING and return it.
    Used by both the in-process local printer and the cloud polling worker API.
    """
    if orders is None:
        orders = load_orders()

    admit_waiting_jobs_once(orders)

    if _find_printing_job(orders):
        return None

    next_job = _find_next_job_to_print(orders)
    if not next_job:
        return None

    next_job["status"] = "PRINTING"
    next_job["print_start_time"] = _now_ts()
    next_job["worker_claimed_time"] = _now_ts()
    save_orders(orders)
    return next_job


def finish_print_job(order_id: str, success: bool, error: Optional[str] = None) -> Optional[Dict[str, Any]]:
    orders = load_orders()
    order = next((o for o in orders if o.get("order_id") == order_id), None)
    if order is None:
        return None

    order["status"] = "PRINTED" if success else "PRINT_FAILED"
    order["printed_time"] = _now_ts()
    if error:
        order["worker_error"] = str(error)[:1000]
    elif success:
        order.pop("worker_error", None)

    save_orders(orders)
    return order


def mark_order_paid_for_queue(order_id: str) -> Optional[Dict[str, Any]]:
    orders = load_orders()
    order = next((o for o in orders if o.get("order_id") == order_id), None)
    if order is None:
        return None

    status = str(order.get("status") or "")
    if status in ["PRINTING", "PRINTED", "PRINT_FAILED"]:
        return order

    # Idempotency: if this order is already admitted into queue flow,
    # repeated webhook/success callbacks should not re-balance it again.
    if status in ["QUEUED", "WAITING_QUEUE"] and order.get("paid_time"):
        return order

    now = time.time()
    if not order.get("paid_time"):
        order["paid_time"] = _now_ts()

    capacity_pages = int(current_app.config.get("MAX_PAID_QUEUE_PAGES", 40))
    # Exclude current order from "used" calculation to avoid self double-counting.
    used_pages = get_effective_used_pages(
        [o for o in orders if o.get("order_id") != order_id],
        now=now,
    )
    job_pages = get_job_pages(order)

    order["status"] = "QUEUED" if used_pages + job_pages <= capacity_pages else "WAITING_QUEUE"
    save_orders(orders)
    return order


def admit_waiting_jobs_once(orders: Optional[List[Dict[str, Any]]] = None) -> Tuple[int, int]:
    """
    Move WAITING_QUEUE -> QUEUED whenever capacity allows.
    Capacity model is page-based:
      - QUEUED jobs count full pages (pages * copies)
      - PRINTING job counts remaining pages only (page-by-page "virtual clearing")
    """
    if orders is None:
        orders = load_orders()

    now = time.time()
    capacity_pages = int(current_app.config.get("MAX_PAID_QUEUE_PAGES", 40))
    used_pages = get_effective_used_pages(orders, now=now)

    waiting = [
        o for o in orders
        if o.get("status") == "WAITING_QUEUE" and o.get("paid_time")
    ]
    waiting = _sort_by_paid_time_fifo(waiting)

    moved = 0
    for job in waiting:
        job_pages = get_job_pages(job)
        if used_pages + job_pages > capacity_pages:
            break

        job["status"] = "QUEUED"
        used_pages += job_pages
        moved += 1

    if moved > 0:
        save_orders(orders)

    return moved, capacity_pages


def _admission_loop(app: Any) -> None:
    with app.app_context():
        while True:
            try:
                orders = load_orders()
                admit_waiting_jobs_once(orders)
            except Exception as e:
                # Keep loop alive; logging to stdout for now.
                print(f"[queue-admission] Error: {e}")
            time.sleep(_QUEUE_ADMISSION_INTERVAL_SEC)


def _printer_worker_loop(app: Any) -> None:
    with app.app_context():
        while True:
            next_job = None
            try:
                orders = load_orders()
                printing_job = _find_printing_job(orders)
                if printing_job:
                    # Real printing is blocking and done in this thread right below,
                    # but if a PRINTING state is left behind due to a crash,
                    # we should wait rather than double-print.
                    time.sleep(5)
                    continue

                next_job = claim_next_job_for_printing(orders)
                if not next_job:
                    time.sleep(_PRINTER_WORKER_IDLE_SLEEP_SEC)
                    continue

                filepath = next_job.get("filepath")
                copies = int(next_job.get("copies") or 1)

                with PRINTER_LOCK:
                    print_pdf(filepath, copies)

                # Success
                finish_print_job(str(next_job.get("order_id")), success=True)

            except Exception as e:
                # Mark last attempted job as failed if we can infer it.
                if next_job and next_job.get("order_id"):
                    finish_print_job(str(next_job.get("order_id")), success=False, error=str(e))
                else:
                    try:
                        orders = load_orders()
                        printing_job = _find_printing_job(orders)
                        if printing_job:
                            finish_print_job(str(printing_job.get("order_id")), success=False, error=str(e))
                    except Exception:
                        pass

                print(f"[printer-worker] Error: {e}")

            time.sleep(0.5)


def start_queue_worker_threads(app: Any) -> None:
    t1 = threading.Thread(
        target=_admission_loop,
        args=(app,),
        daemon=True,
        name="queue-admission",
    )
    t2 = threading.Thread(
        target=_printer_worker_loop,
        args=(app,),
        daemon=True,
        name="printer-worker",
    )
    t1.start()
    t2.start()
    print("[queue] Started queue admission + printer worker threads.")
