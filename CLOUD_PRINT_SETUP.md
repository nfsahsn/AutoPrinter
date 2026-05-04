# Cloud Website + Local Printer Setup

This app now supports a cloud web server plus a local PC print worker.

## How It Works

- The cloud server runs the Flask website, accepts uploads, stores PDFs, and shows status pages.
- The local PC runs `local_print_worker.py`.
- The local worker polls the cloud for the next `QUEUED` job, downloads the PDF, prints it on the local printer, then reports `PRINTED` or `PRINT_FAILED`.
- Your local PC does not need to expose any public port.

## Cloud Environment

Set these on the cloud server:

```bash
SECRET_KEY=change-this-to-a-long-random-value
PUBLIC_BASE_URL=https://your-cloud-domain.example
WORKER_API_TOKEN=change-this-to-a-long-random-token
ENABLE_IN_PROCESS_PRINTER=0
ENABLE_CLEANUP_THREAD=1
NAGORIKPAY_API_KEY=your-gateway-api-key
NAGORIKPAY_CREATE_URL=https://secure-pay.nagorikpay.com/api/payment/create
```

Important: `ENABLE_IN_PROCESS_PRINTER=0` prevents the cloud machine from trying to print.

The cloud host must keep `orders.json` and `uploads/` persistent. Use a VPS, persistent disk, or another storage-backed deployment.

## Render Deployment

This repo includes `render.yaml` for Render Blueprint deployment.

1. Push this project to GitHub.
2. In Render, choose `New` -> `Blueprint`.
3. Connect the GitHub repo and let Render read `render.yaml`.
4. Create the service.
5. After the first deploy, copy the generated Render URL, for example:

```text
https://autoprinter.onrender.com
```

6. In the Render service environment variables, set:

```bash
PUBLIC_BASE_URL=https://your-render-url.onrender.com
```

7. Copy the generated `WORKER_API_TOKEN` value from Render. Use the same token on your local PC worker.

The included Render config:

- runs `gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT run:app`
- disables cloud-side printing with `ENABLE_IN_PROCESS_PRINTER=0`
- stores `orders.json`, uploads, reports, and user data under the persistent disk at `/opt/render/project/src/data`

Do not scale this service above one instance while it uses JSON files and a persistent disk.

## Local PC Worker

Install the same project dependencies, then run:

```bash
CLOUD_BASE_URL=https://your-render-url.onrender.com \
WORKER_API_TOKEN=change-this-to-a-long-random-token \
venv_new/bin/python local_print_worker.py
```

On Windows, run the equivalent command in PowerShell and make sure SumatraPDF is installed at one of the configured paths in `config.py`.

## Basic Flow

1. Deploy the Flask web app to cloud with `ENABLE_IN_PROCESS_PRINTER=0`.
2. Keep the local PC on and connected to the printer.
3. Run `local_print_worker.py` on the local PC.
4. Users upload PDFs through the cloud website.
5. Customer pays through `/pay/<order_id>`.
6. Success callback/webhook marks order as paid and admits it into `QUEUED` or `WAITING_QUEUE`.
7. The local worker prints queued jobs.

## Notes

- The admin `Paid` button remains available as a manual fallback for demo or gateway outage scenarios.
