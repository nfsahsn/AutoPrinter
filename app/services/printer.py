import os
import subprocess
import platform
from threading import Lock
from flask import current_app

PRINTER_LOCK = Lock()

def get_sumatra_path():
    paths = [
        current_app.config.get('SUMATRA_PATH_1'),
        current_app.config.get('SUMATRA_PATH_2'),
        current_app.config.get('SUMATRA_PATH_3')
    ]
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def print_pdf_linux(filepath, copies):
    """Print PDF on Linux using the 'lp' command."""
    # -n: number of copies
    # -d: printer name (optional, uses default if not specified)
    cmd = ["lp", "-n", str(copies), filepath]
    
    # If a specific printer is configured, use it
    printer_name = current_app.config.get('LINUX_PRINTER_NAME')
    if printer_name:
        cmd.insert(1, "-d")
        cmd.insert(2, printer_name)
        
    subprocess.run(cmd, check=True)

def print_pdf_windows(filepath, copies):
    """Print PDF on Windows using SumatraPDF."""
    sumatra = get_sumatra_path()
    if not sumatra:
        raise Exception("SumatraPDF not found! Please install SumatraPDF.")

    cmd = [
        sumatra,
        "-print-to-default",
        "-silent",
        "-exit-on-print",
        "-print-settings",
        f"copies={copies}",
        filepath
    ]
    subprocess.run(cmd, check=True)

def print_pdf(filepath, copies):
    """Cross-platform print handler."""
    if platform.system() == "Windows":
        print_pdf_windows(filepath, copies)
    else:
        # Assume Linux/Ubuntu
        print_pdf_linux(filepath, copies)
