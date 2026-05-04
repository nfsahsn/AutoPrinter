import os
import json
import math
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app


from app.extensions import db
from app.models import Order

def load_orders() -> List[Dict[str, Any]]:
    with current_app.app_context():
        return [o.to_dict() for o in Order.query.all()]

def save_orders(orders: List[Dict[str, Any]]) -> None:
    with current_app.app_context():
        for o in orders:
            db_order = Order.query.get(o["order_id"])
            if not db_order:
                db_order = Order(order_id=o["order_id"])
                db.session.add(db_order)
                
            db_order.queue_no = o.get("queue_no")
            db_order.session_id = o.get("session_id")
            db_order.phone = o.get("phone")
            db_order.filename = o.get("filename")
            db_order.filepath = o.get("filepath")
            db_order.pages = o.get("pages")
            db_order.copies = o.get("copies")
            db_order.ptype = o.get("ptype")
            db_order.total = o.get("total")
            db_order.status = o.get("status")
            db_order.time = o.get("time")
            db_order.created_time = o.get("created_time")
            db_order.paid_time = o.get("paid_time")
            db_order.printed_time = o.get("printed_time")
            db_order.print_start_time = o.get("print_start_time")
        db.session.commit()


def find_order(orders: List[Dict[str, Any]], order_id: str) -> Optional[Dict[str, Any]]:
    return next((o for o in orders if o.get("order_id") == order_id), None)


def get_next_queue_number(orders: List[Dict[str, Any]]) -> int:
    today = date.today().strftime("%Y-%m-%d")
    today_orders = [o for o in orders if str(o.get("time", "")).startswith(today)]
    return len(today_orders) + 1


def get_job_pages(order: Dict[str, Any]) -> int:
    pages = int(order.get("pages") or 0)
    copies = int(order.get("copies") or 1)
    return pages * copies


def get_sec_per_page(order: Dict[str, Any]) -> int:
    ptype = order.get("ptype") or "bw"
    if ptype == "bw":
        return int(current_app.config["BW_SECONDS_PER_PAGE"])
    return int(current_app.config["COLOR_SECONDS_PER_PAGE"])


def job_seconds(order: Dict[str, Any]) -> int:
    return get_job_pages(order) * get_sec_per_page(order)


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _printing_remaining_pages(order: Dict[str, Any], now: float) -> int:
    """
    Page-by-page virtual clearing:
      - if PRINTING has print_start_time, remaining = total_pages - floor(elapsed/sec_per_page)
      - clamped to [0..total_pages]
    """
    job_pages = get_job_pages(order)
    if job_pages <= 0:
        return 0

    print_start_time = order.get("print_start_time")
    if not print_start_time:
        # If we don't know when printing started, assume the whole job is still remaining.
        return job_pages

    elapsed_sec = max(0.0, float(now) - float(print_start_time))
    sec_per_page = get_sec_per_page(order)
    if sec_per_page <= 0:
        return 0

    pages_printed = int(math.floor(elapsed_sec / sec_per_page))
    pages_printed = _clamp(pages_printed, 0, job_pages)
    remaining = job_pages - pages_printed
    return _clamp(remaining, 0, job_pages)


def get_effective_used_pages(orders: List[Dict[str, Any]], now: Optional[float] = None) -> int:
    """
    Capacity model (page-based, max 40 physical pages):
      - QUEUED jobs count full pages
      - PRINTING job counts only remaining pages (virtual clearing)
      - WAITING_QUEUE does NOT count until admitted
    """
    if now is None:
        now = time.time()

    total_pages = 0
    for o in orders:
        if o.get("status") in ["QUEUED", "PRINTING"]:
            total_pages += get_effective_remaining_pages_for_queue(o, now=now)

    return total_pages


def get_paid_queue_pages(
    orders: Optional[List[Dict[str, Any]]] = None,
    now: Optional[float] = None,
) -> int:
    """
    Total pages currently consuming the queue capacity
    (QUEUED full pages + PRINTING remaining pages).
    """
    if orders is None:
        orders = load_orders()
    return get_effective_used_pages(orders, now=now)


def get_paid_queue_info() -> Tuple[int, int]:
    """
    Returns: (used_pages, total_seconds_for_used_queue)
    Note: total_seconds uses the same remaining-page model for PRINTING.
    """
    orders = load_orders()
    now = time.time()

    used_pages = 0
    used_seconds = 0

    for o in orders:
        if o.get("status") in ["QUEUED", "PRINTING"]:
            pages = get_effective_remaining_pages_for_queue(o, now=now)
            used_pages += pages
            used_seconds += pages * get_sec_per_page(o)

    return used_pages, int(used_seconds)


def get_queue_seconds_before(order_id: str) -> int:
    """
    Legacy helper: keep for compatibility, but will be superseded once we update /status-data.
    """
    orders = load_orders()
    total = 0
    for o in orders:
        if o.get("status") in ["QUEUED", "PRINTING"]:
            if o.get("order_id") == order_id:
                continue
            # If PRINTING, we should use remaining pages (virtual clearing).
            if o.get("status") == "PRINTING":
                total += _printing_remaining_pages(o, now=time.time()) * get_sec_per_page(o)
            else:
                total += get_job_pages(o) * get_sec_per_page(o)
    return int(total)


def get_jobs_before(order_id: str) -> int:
    """
    Legacy: counts jobs before based on created_time.
    For the new gateway-agnostic queue model, we will update /status-data to use paid_time FIFO.
    """
    orders = load_orders()
    me = find_order(orders, order_id)
    if not me or not me.get("created_time"):
        return 0

    me_time = int(me.get("created_time") or 0)
    count = 0
    for o in orders:
        if o.get("status") in ["QUEUED", "PRINTING"]:
            if o.get("order_id") == order_id:
                continue
            if o.get("created_time") and int(o["created_time"]) <= me_time:
                count += 1
    return count


def get_user_orders(user_ref: str) -> List[Dict[str, Any]]:
    """Get user orders by session_id (guest flow) or phone, newest first."""
    orders = load_orders()
    return list(reversed([
        o for o in orders
        if o.get("session_id") == user_ref or o.get("phone") == user_ref
    ]))


def get_effective_printing_pages_before_order(
    orders: List[Dict[str, Any]], order_id: str, now: Optional[float] = None
) -> Tuple[int, int]:
    """
    Compute (pages_ahead, total_pages_for_order) for UI queue display.

    New queue rule:
      - FIFO by paid_time (not created_time)
      - WAITING_QUEUE/QUEUED jobs count full pages
      - PRINTING job counts remaining pages (virtual clearing)
    """
    if now is None:
        now = time.time()

    me = find_order(orders, order_id)
    if not me:
        return 0, 0

    me_job_pages = get_job_pages(me)

    active = [
        o for o in orders
        if o.get("status") in ["WAITING_QUEUE", "QUEUED", "PRINTING"] and o.get("paid_time")
    ]

    # Sort by paid_time FIFO (and tie-breaker: order_id for stability)
    active_sorted = sorted(active, key=lambda o: (int(o.get("paid_time") or 0), str(o.get("order_id") or "")))

    pages_ahead = 0
    for o in active_sorted:
        if o.get("order_id") == order_id:
            break

        pages_ahead += get_effective_remaining_pages_for_queue(o, now=now)

    return int(pages_ahead), int(me_job_pages)


def get_printing_pages_remaining(order: Dict[str, Any], now: Optional[float] = None) -> int:
    """
    For PRINTING jobs: remaining pages after virtual clearing.
    For non-PRINTING jobs: returns full job pages.
    """
    if now is None:
        now = time.time()
    if order.get("status") != "PRINTING":
        return get_job_pages(order)
    return _printing_remaining_pages(order, now=now)


def get_printing_pages_printed(order: Dict[str, Any], now: Optional[float] = None) -> int:
    """
    For PRINTING jobs: pages already printed (virtual).
    For non-PRINTING jobs: returns 0.
    """
    if now is None:
        now = time.time()
    if order.get("status") != "PRINTING":
        return 0
    total_pages = get_job_pages(order)
    remaining_pages = _printing_remaining_pages(order, now=now)
    printed = total_pages - remaining_pages
    return _clamp(int(printed), 0, total_pages)


def get_effective_remaining_pages_for_queue(order: Dict[str, Any], now: Optional[float] = None) -> int:
    """
    Queue "remaining pages" model:
      - PRINTING job => remaining pages (virtual clearing)
      - QUEUED/WAITING_QUEUE => full pages
    """
    if now is None:
        now = time.time()
    status = order.get("status")
    if status == "PRINTING":
        return _printing_remaining_pages(order, now=now)
    return get_job_pages(order)


def get_effective_remaining_seconds_for_queue(order: Dict[str, Any], now: Optional[float] = None) -> int:
    pages = get_effective_remaining_pages_for_queue(order, now=now)
    return int(pages) * int(get_sec_per_page(order))


def get_queue_seconds_remaining_for_order(order: Dict[str, Any], pages_remaining: int) -> int:
    """
    Convert pages_remaining to seconds based on the order's ptype rate.
    """
    return int(pages_remaining) * int(get_sec_per_page(order))
