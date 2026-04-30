import argparse
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from flask import Flask

from app.services.printer import PRINTER_LOCK, print_pdf
from config import Config


def _clean_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


class CloudPrintWorker:
    def __init__(self, cloud_url: str, token: str, poll_seconds: int) -> None:
        self.cloud_url = _clean_base_url(cloud_url)
        self.token = token
        self.poll_seconds = poll_seconds
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        self.local_app = Flask("local_print_worker")
        self.local_app.config.from_object(Config)

    def api_url(self, path: str) -> str:
        return urljoin(self.cloud_url, path.lstrip("/"))

    def get_next_job(self):
        response = self.session.get(self.api_url("/worker/next-job"), timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "cloud returned ok=false")
        return payload.get("job")

    def download_pdf(self, job, directory: str) -> str:
        filename = job.get("filename") or f"{job['order_id']}.pdf"
        local_path = Path(directory) / filename
        response = self.session.get(job["file_url"], timeout=60)
        response.raise_for_status()
        local_path.write_bytes(response.content)
        return str(local_path)

    def complete_job(self, order_id: str, success: bool, error: str = "") -> None:
        payload = {"status": "PRINTED" if success else "PRINT_FAILED"}
        if error:
            payload["error"] = error
        response = self.session.post(
            self.api_url(f"/worker/jobs/{order_id}/complete"),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

    def print_job(self, job) -> None:
        order_id = job["order_id"]
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = self.download_pdf(job, tmpdir)
                copies = int(job.get("copies") or 1)
                with self.local_app.app_context():
                    with PRINTER_LOCK:
                        print_pdf(pdf_path, copies)
            self.complete_job(order_id, success=True)
            print(f"[worker] Printed order {order_id}")
        except Exception as exc:
            self.complete_job(order_id, success=False, error=str(exc))
            print(f"[worker] Failed order {order_id}: {exc}")

    def run_forever(self) -> None:
        print(f"[worker] Polling {self.cloud_url} every {self.poll_seconds}s")
        while True:
            try:
                job = self.get_next_job()
                if job:
                    print(f"[worker] Claimed order {job['order_id']} ({job.get('total_pages')} pages)")
                    self.print_job(job)
                else:
                    time.sleep(self.poll_seconds)
            except KeyboardInterrupt:
                print("[worker] Stopped")
                return
            except Exception as exc:
                print(f"[worker] Error: {exc}")
                time.sleep(self.poll_seconds)


def parse_args():
    parser = argparse.ArgumentParser(description="Poll cloud AutoPrinter jobs and print them on this PC.")
    parser.add_argument("--cloud-url", default=os.environ.get("CLOUD_BASE_URL", ""))
    parser.add_argument("--token", default=os.environ.get("WORKER_API_TOKEN", ""))
    parser.add_argument("--poll-seconds", type=int, default=int(os.environ.get("WORKER_POLL_SECONDS", "5")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.cloud_url:
        print("Missing cloud URL. Set CLOUD_BASE_URL or pass --cloud-url.")
        return 2
    if not args.token:
        print("Missing worker token. Set WORKER_API_TOKEN or pass --token.")
        return 2

    CloudPrintWorker(args.cloud_url, args.token, args.poll_seconds).run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
