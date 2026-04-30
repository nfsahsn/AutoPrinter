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
5. In `/admin`, click `Paid` for a pending order to move it into the print queue.
6. The local worker prints queued jobs.

## Current Limitation

Payment/gateway restoration is still separate. Until it is restored, use the admin `Paid` button to approve pending jobs.
