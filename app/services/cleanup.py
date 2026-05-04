import os
import time
import threading


def _cleanup_loop(upload_folder, retention_hours):
    """Background loop: delete PDFs older than retention_hours."""
    retention_seconds = retention_hours * 3600
    while True:
        try:
            now = time.time()
            if os.path.isdir(upload_folder):
                for fname in os.listdir(upload_folder):
                    fpath = os.path.join(upload_folder, fname)
                    if os.path.isfile(fpath) and fname.lower().endswith(".pdf"):
                        age = now - os.path.getmtime(fpath)
                        if age > retention_seconds:
                            try:
                                os.remove(fpath)
                                print(f"[cleanup] Deleted {fname} (age: {age/3600:.1f}h)")
                            except Exception as e:
                                print(f"[cleanup] Failed to delete {fname}: {e}")
        except Exception as e:
            print(f"[cleanup] Error: {e}")

        # Check every 10 minutes
        time.sleep(600)


def start_cleanup_thread(app):
    """Start the background cleanup thread using app config."""
    upload_folder = app.config.get("UPLOAD_FOLDER", "uploads")
    retention_hours = app.config.get("PDF_RETENTION_HOURS", 24)

    t = threading.Thread(
        target=_cleanup_loop,
        args=(upload_folder, retention_hours),
        daemon=True,
        name="pdf-cleanup",
    )
    t.start()
    print(f"[cleanup] Started — deleting PDFs older than {retention_hours}h from {upload_folder}")
