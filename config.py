import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE_THIS_SECRET_KEY_123")
    
    # 🔐 Admin password
    ADMIN_PASSWORD_DEFAULT = "hackhobena"
    ADMIN_PASS_FILE = "admin_pass.json"
    ADMIN_PASS_PATH = os.path.join(BASE_DIR, ADMIN_PASS_FILE)
    
    # ✅ Your public host (NO trailing slash)
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5000")

    # 💳 Gateway (Paymently)
    PAYMENTLY_API_KEY = os.environ.get("PAYMENTLY_API_KEY", "gN8DEwrJ4i6jl5t3wqhWa7BVK3LzRgA9vmpko7vI")
    PAYMENTLY_CREATE_URL = os.environ.get(
        "PAYMENTLY_CREATE_URL",
        "https://nfsahsn.paymently.io/api/checkout-v2",
    )
    PAYMENTLY_VERIFY_URL = os.environ.get(
        "PAYMENTLY_VERIFY_URL",
        "https://nfsahsn.paymently.io/api/verify-payment",
    )
    
    # 💰 Pricing
    PRICE_PER_PAGE = 2
    
    # 💳 Due limit (taka) — user blocked from printing when due >= this
    MAX_DUE_LIMIT = 100
    
    # 📱 Payment numbers (shown to users on wallet page)
    BKASH_NUMBER = "01XXXXXXXXX"
    NAGAD_NUMBER = "01XXXXXXXXX"
    
    # 🖨️ Print settings
    ADMIN_REFRESH_SECONDS = 60
    MAX_PAID_QUEUE_PAGES = 40
    BW_SECONDS_PER_PAGE = 10
    COLOR_SECONDS_PER_PAGE = 15
    ENABLE_IN_PROCESS_PRINTER = _env_bool("ENABLE_IN_PROCESS_PRINTER", True)
    ENABLE_CLEANUP_THREAD = _env_bool("ENABLE_CLEANUP_THREAD", True)
    WORKER_API_TOKEN = os.environ.get("WORKER_API_TOKEN", "")
    
    # 📂 PDF retention — auto-delete after N hours
    PDF_RETENTION_HOURS = 1
    
    # 🐧 Linux Printing (Ubuntu)
    # Leave None to use the system default printer
    LINUX_PRINTER_NAME = None
    
    # SumatraPDF paths (Windows)
    SUMATRA_PATH_1 = r"C:\Users\USER\AppData\Local\SumatraPDF\SumatraPDF.exe"
    SUMATRA_PATH_2 = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
    SUMATRA_PATH_3 = r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe"
    
    # Paths
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(DATA_DIR, "uploads"))
    STATIC_FOLDER = os.environ.get("STATIC_FOLDER", os.path.join(BASE_DIR, "app", "static"))
    DB_FILE = os.environ.get("DB_FILE", os.path.join(DATA_DIR, "orders.json"))
    USERS_DB = os.environ.get("USERS_DB", os.path.join(DATA_DIR, "users.json"))
    DEPOSITS_DB = os.environ.get("DEPOSITS_DB", os.path.join(DATA_DIR, "deposits.json"))
    REPORTS_FOLDER = os.environ.get("REPORTS_FOLDER", os.path.join(DATA_DIR, "reports"))
    
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", f"sqlite:///{os.path.join(DATA_DIR, 'autoprinter.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
