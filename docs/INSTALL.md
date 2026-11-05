# Installing SubFa from zero

Three ways in:

- **The one-liner (recommended).** Fetch the installer straight
  from this repo; it clones the project for you and then runs the
  wizard inside the clone. See the next section.
- **The wizard from a checkout.** Run `install.ps1` on Windows or
  `install.sh` on Linux, macOS or a Linux VPS. It checks the
  prerequisites, builds the virtual environment, and asks only the
  questions your chosen surface needs (bot token and admin ID for
  the bot; domain or IP for the web app; models for all three).
- **Manually.** This document, which mirrors the wizard step for
  step so you can see and control everything it does.

Persian walkthrough of the same material: the "نصب از صفر" section
in [README.fa.md](../README.fa.md).

## One-line install

Linux, macOS, or a Linux VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/E30TZ/subfa/main/install.sh -o /tmp/subfa.sh && bash /tmp/subfa.sh install
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/E30TZ/subfa/main/install.ps1 | iex
```

Cloning the repo and running
`powershell -ExecutionPolicy Bypass -File install.ps1` does the
same thing on Windows, and that form also takes the PowerShell
parameters listed below.

When the script runs outside a checkout it clones
`https://github.com/E30TZ/subfa` first: into `~/subfa` by default
on Linux and macOS (`%USERPROFILE%\subfa` on Windows). On Linux
the script also offers `/opt/subfa` when sudo is available. Two
environment variables override the defaults:

| Variable | Meaning |
| --- | --- |
| `SUBFA_INSTALL_DIR` | Clone into this directory instead |
| `SUBFA_REPO_URL` | Clone this repository URL (or local path) instead |

If the target directory already holds a SubFa checkout, the
installer reuses it instead of cloning again.

### Scripted flags (bash)

`install` is the only subcommand. With no flags at all, the
interactive wizard runs unchanged. Each flag pre-answers one
wizard question; anything still missing is asked.

```bash
bash /tmp/subfa.sh install --target bot
bash /tmp/subfa.sh install --target bot --token YOUR_TOKEN --admin-id 123456789 --no-models --run service
bash /tmp/subfa.sh install --target web --port 9000 --domain sub.example.com --run service
bash /tmp/subfa.sh install --target web --ip --no-models --run none --lang en
bash /tmp/subfa.sh install --target cli --models
```

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--target bot\|web\|cli` | all | Install only this surface; skips the main menu |
| `--token TOKEN` | bot | Bot token from @BotFather; validated live, never echoed |
| `--admin-id NUMBER` | bot | Your numeric Telegram ID; stored in `.env` like the wizard does |
| `--port NUMBER` | web | Port for the web app (default 8000) |
| `--domain DOMAIN` | web | Serve behind this domain (nginx and HTTPS flow on Linux) |
| `--ip` | web | Serve on this machine's IP instead of a domain |
| `--models` | all | Download the speech and translation models without asking |
| `--no-models` | all | Skip the model download without asking |
| `--run now` | bot, web | Start it in this terminal when the install finishes |
| `--run service` | bot, web | Install the systemd service (Linux only) |
| `--run none` | bot, web | Install only; print the run command |
| `--lang fa\|en` | all | Installer language; skips the language question |

Unknown flags print the usage text and exit with a non-zero
status, as do invalid values (a non-numeric `--admin-id`, an
out-of-range `--port`, an unknown `--target`).

### Parameters (PowerShell)

The same answers can be passed to `install.ps1` when it runs from
a file (the `irm | iex` form runs the plain wizard):

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 install -Target bot -Token YOUR_TOKEN -AdminId 123456789 -NoModels -Run none
powershell -ExecutionPolicy Bypass -File install.ps1 install -Target web -Port 9000 -Ip
powershell -ExecutionPolicy Bypass -File install.ps1 install -Target cli -Lang en
```

| Parameter | Mirrors |
| --- | --- |
| `-Target bot\|web\|cli` | `--target` |
| `-Token TOKEN` | `--token` |
| `-AdminId NUMBER` | `--admin-id` |
| `-Port NUMBER` | `--port` |
| `-Domain DOMAIN` | `--domain` |
| `-Ip` | `--ip` |
| `-Models` / `-NoModels` | `--models` / `--no-models` |
| `-Run now\|service\|none` | `--run` (systemd is Linux-only; on Windows `service` prints the run command instead) |
| `-Lang fa\|en` | `--lang` |

## 1. Get the code

```bash
git clone https://github.com/E30TZ/subfa.git
cd subfa
```

## 2. Prerequisites

You need **Python 3.10 or newer** and **ffmpeg** on your PATH.

| System | Python | ffmpeg |
| --- | --- | --- |
| Windows | `winget install Python.Python.3.12` or python.org | `winget install Gyan.FFmpeg` |
| macOS | `brew install python` | `brew install ffmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt install python3 python3-venv python3-pip` | `sudo apt install ffmpeg` |

On Windows, reopen PowerShell after a winget install so the new
PATH is picked up.

## 3. Virtual environment

```bash
python -m venv .venv
```

Activate it:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Windows (cmd): `.venv\Scripts\activate.bat`
- macOS and Linux: `source .venv/bin/activate`

Every command below assumes the venv is active, or that you use
the venv's binaries directly (`.venv/bin/...` on macOS and Linux,
`.venv\Scripts\...` on Windows).

## 4. Install per surface

SubFa is one project with optional extras per surface:

| Surface | Command | What it adds |
| --- | --- | --- |
| Telegram bot | `pip install -e ".[bot,translate,persian]"` | python-telegram-bot, offline translation, the Persian speech engine |
| Web app | `pip install -e ".[web,translate,persian]"` | FastAPI and uvicorn, offline translation, the Persian speech engine |
| CLI | `pip install -e ".[translate,persian]"` | The `subfa` command with offline translation and the Persian speech engine |

With no extras (`pip install -e .`) you get the core: faster-whisper
transcription for non-Persian audio and link downloading, but no
offline translation and no Persian fine-tuned engine.

## 5. Configuration (.env)

Copy the example and edit it:

```bash
cp .env.example .env
```

The keys the installer asks about:

| Key | Used by | Meaning |
| --- | --- | --- |
| `BOT_TOKEN` | bot | The token from @BotFather. The bot reads it from its process environment; the systemd unit below loads it from `.env` automatically. |
| `SUBFA_ADMIN_ID` | stored only | Your numeric Telegram ID. SubFa stores it for the owner's own use; it does not change the bot's behavior. |

All other keys (model routing, size caps, style, digits) are
documented with defaults in `.env.example`. Keep `.env` private:
it contains your bot token. The wizard sets its permissions to
owner-only where the system supports it.

## 6. Speech and translation models (once)

```bash
subfa download-models
```

This fills the model cache (`SUBFA_MODEL_CACHE`, default
`~/.cache/subfa/models`) with the faster-whisper model, the
Persian fine-tuned model and the Argos en/fa packages. It is a
large one-time download; afterwards transcription and translation
run fully offline. See the offline section of the README for
mirror options (`HF_ENDPOINT`).

## 7. Run each surface

### Telegram bot

The bot needs `BOT_TOKEN` in its environment:

```bash
# macOS and Linux: load .env, then run
export BOT_TOKEN=$(grep '^BOT_TOKEN=' .env | cut -d= -f2-)
.venv/bin/python -m bot.bot
```

```powershell
# Windows PowerShell
$env:BOT_TOKEN = (Get-Content .env | Where-Object { $_ -match '^BOT_TOKEN=' }) -replace '^BOT_TOKEN=', ''
.venv\Scripts\python.exe -m bot.bot
```

### Web app

```bash
.venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` (or the server IP and port). When a
reverse proxy fronts the app (next section), bind the app itself
to localhost instead: `--host 127.0.0.1`.

### CLI

```bash
subfa lecture.mp4 --target fa --burn -o out/
subfa https://www.youtube.com/watch?v=VIDEO_ID --target fa --burn
subfa lesson.mkv --glossary programming --bilingual -o out/
subfa --help
```

## 8. Linux VPS: systemd services

For an always-on server, run the bot and the web app as systemd
services. Both units load `.env` through `EnvironmentFile`, restart
on failure, and start at boot. Replace `/opt/subfa` with your
checkout path and `YOURUSER` with your user.

`/etc/systemd/system/subfa-bot.service`:

```ini
[Unit]
Description=SubFa Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOURUSER
WorkingDirectory=/opt/subfa
EnvironmentFile=/opt/subfa/.env
ExecStart=/opt/subfa/.venv/bin/python -m bot.bot
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/subfa-web.service`:

```ini
[Unit]
Description=SubFa web app
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOURUSER
WorkingDirectory=/opt/subfa
EnvironmentFile=/opt/subfa/.env
ExecStart=/opt/subfa/.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The web unit binds to localhost because nginx (next section)
faces the internet. If you have no proxy, change the host to
`0.0.0.0` and use `http://YOUR-IP:8000`.

Enable and manage:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now subfa-bot
sudo systemctl enable --now subfa-web
systemctl status subfa-bot
journalctl -u subfa-bot -f
sudo systemctl restart subfa-web
```

## 9. Domain and HTTPS (nginx + Let's Encrypt)

Point your domain's DNS A record at the server first. Then:

```bash
sudo apt install nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/subfa`:

```nginx
server {
    listen 80;
    server_name sub.example.com;

    # Matches the default upload cap (SUBFA_MAX_FILE_MB=200).
    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/subfa /etc/nginx/sites-enabled/subfa
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d sub.example.com
```

Certbot rewrites the nginx site for HTTPS and sets up renewal.
Your web app is now at `https://sub.example.com`.

## 10. Updating

```bash
cd subfa
git pull
.venv/bin/pip install -e ".[bot,translate,persian]"   # use your surface's extras
sudo systemctl restart subfa-bot subfa-web            # if you run the services
```

## 11. Removing the services

```bash
sudo systemctl disable --now subfa-bot subfa-web
sudo rm /etc/systemd/system/subfa-bot.service /etc/systemd/system/subfa-web.service
sudo systemctl daemon-reload
sudo rm /etc/nginx/sites-enabled/subfa /etc/nginx/sites-available/subfa
sudo systemctl reload nginx
```

The checkout, `.venv` and `.env` are just files in your folder;
delete the folder to remove everything else.

## 12. Troubleshooting

- **`python -m venv` fails on Debian/Ubuntu:** install
  `python3-venv` (step 2) and try again.
- **The bot says BOT_TOKEN is not set:** the token must be in the
  process environment. Use the export commands in step 7, or the
  systemd unit, which reads `.env` for you.
- **Telegram rejects the token:** copy it again from @BotFather in
  full; tokens contain a colon and no spaces.
- **Port already in use:** pick another port (the wizard asks;
  manually, change `--port` and the nginx `proxy_pass` to match).
- **First job is slow or fails with a download error:** the models
  are not cached yet. Run `subfa download-models` once with a
  working network (or set `HF_ENDPOINT` to a mirror first).
