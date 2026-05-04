import os
from flask import Flask
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure required folders exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["REPORTS_FOLDER"], exist_ok=True)
    os.makedirs(app.config["STATIC_FOLDER"], exist_ok=True)

    # Register blueprints
    from app.routes.public import public_bp
    from app.routes.admin import admin_bp
    from app.routes.worker import worker_bp
    from app.routes.auth import auth_bp
    from app.routes.wallet import wallet_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(worker_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(wallet_bp)

    # Start background PDF cleanup thread
    if app.config.get("ENABLE_CLEANUP_THREAD", True):
        from app.services.cleanup import start_cleanup_thread
        start_cleanup_thread(app)

    # Local-only mode: web server and printer are on the same machine.
    # Cloud mode should set ENABLE_IN_PROCESS_PRINTER=0 and use local_print_worker.py.
    if app.config.get("ENABLE_IN_PROCESS_PRINTER", True):
        from app.services.queue_worker import start_queue_worker_threads
        start_queue_worker_threads(app)

    return app
