#!/usr/bin/env bash
#
# SubFa interactive installer for Linux and macOS.
#
# From zero to a running SubFa: checks Python 3.10+ and ffmpeg,
# builds .venv, then lets you pick the Telegram bot, the web app
# or the CLI, and asks only the questions that surface needs.
#
# Usage:  bash install.sh [install] [options]
#
# With no options the interactive wizard runs. Run with --help for
# the scripted flags. When this script is NOT inside a SubFa
# checkout it first clones the project (default ~/subfa) and then
# continues the wizard inside the clone, so a copy fetched on its
# own is enough:
#
#   curl -fsSL https://raw.githubusercontent.com/E30TZ/subfa/main/install.sh -o /tmp/subfa.sh
#   bash /tmp/subfa.sh install
#
set -u

# ------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------
F_TARGET=""
F_TOKEN=""
F_ADMIN=""
F_PORT=""
F_DOMAIN=""
F_IP=0
F_MODELS=""
F_RUN=""
F_LANG=""

usage() {
  cat <<'EOF'
Usage: bash install.sh [install] [options]

Options:
  --target bot|web|cli   Install only this surface (skip the menu)
  --token TOKEN          Telegram bot token (bot target)
  --admin-id NUMBER      Your numeric Telegram ID (bot target)
  --port NUMBER          Web app port (web target, default 8000)
  --domain DOMAIN        Serve the web app behind this domain (web target)
  --ip                   Serve the web app on this machine's IP (web target)
  --models               Download the speech and translation models
  --no-models            Skip the model download
  --run now|service|none How to run it after the install
  --lang fa|en           Installer language
  -h, --help             Show this help

With no options the interactive wizard runs. Given flags fill in
the matching wizard answers; anything still missing is asked.
Environment: SUBFA_INSTALL_DIR overrides the clone directory and
SUBFA_REPO_URL overrides the repository cloned in standalone mode.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    install) shift ;;
    --target)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_TARGET="$2"; shift 2 ;;
    --token)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_TOKEN="$2"; shift 2 ;;
    --admin-id)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_ADMIN="$2"; shift 2 ;;
    --port)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_PORT="$2"; shift 2 ;;
    --domain)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_DOMAIN="$2"; shift 2 ;;
    --ip) F_IP=1; shift ;;
    --models) F_MODELS="yes"; shift ;;
    --no-models) F_MODELS="no"; shift ;;
    --run)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_RUN="$2"; shift 2 ;;
    --lang)
      [ $# -ge 2 ] || { usage >&2; exit 2; }
      F_LANG="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

case "$F_TARGET" in
  ""|bot|web|cli) ;;
  *) echo "Invalid --target: $F_TARGET" >&2; usage >&2; exit 2 ;;
esac
case "$F_RUN" in
  ""|now|service|none) ;;
  *) echo "Invalid --run: $F_RUN" >&2; usage >&2; exit 2 ;;
esac
case "$F_LANG" in
  ""|fa|en) ;;
  *) echo "Invalid --lang: $F_LANG" >&2; usage >&2; exit 2 ;;
esac
if [ -n "$F_ADMIN" ]; then
  case "$F_ADMIN" in
    *[!0-9]*) echo "Invalid --admin-id: digits only" >&2; usage >&2; exit 2 ;;
  esac
fi
if [ -n "$F_PORT" ]; then
  case "$F_PORT" in
    *[!0-9]*) echo "Invalid --port: $F_PORT" >&2; usage >&2; exit 2 ;;
  esac
  if [ "$F_PORT" -lt 1 ] || [ "$F_PORT" -gt 65535 ]; then
    echo "Invalid --port: $F_PORT" >&2; usage >&2; exit 2
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OS_NAME="$(uname -s)"

# ------------------------------------------------------------------
# Language: Persian by default, English on request.
# ------------------------------------------------------------------
printf 'SubFa installer\n'
if [ -n "$F_LANG" ]; then
  UI_LANG="$F_LANG"
else
  printf '1) فارسی\n'
  printf '2) English\n'
  printf 'Language / زبان [1]: '
  read -r LANG_CHOICE || LANG_CHOICE=""
  case "$LANG_CHOICE" in
    2|en|En|EN|english|English) UI_LANG="en" ;;
    *) UI_LANG="fa" ;;
  esac
fi

if [ "$UI_LANG" = "fa" ]; then
  MSG_WELCOME="به نصب‌کننده SubFa خوش آمدید."
  MSG_PY_MISSING="Python نسخه 3.10 یا بالاتر پیدا نشد."
  MSG_FFMPEG_MISSING="ffmpeg پیدا نشد."
  MSG_INSTALL_OFFER_SUFFIX="با مدیر بسته سیستم نصب شود؟"
  MSG_INSTALLING="در حال نصب"
  MSG_STILL_MISSING="هنوز در دسترس نیست؛ لطفا دستی نصب کنید و دوباره اجرا کنید."
  MSG_MANUAL_PY="لطفا Python 3.10 یا بالاتر را از python.org نصب کنید و این اسکریپت را دوباره اجرا کنید."
  MSG_MANUAL_FFMPEG="لطفا ffmpeg را نصب کنید (از مدیر بسته سیستم یا ffmpeg.org) و دوباره اجرا کنید."
  MSG_VENV_CREATE="در حال ساخت محیط مجازی (.venv) ..."
  MSG_VENV_REUSE="محیط مجازی .venv از قبل هست؛ همان استفاده شود؟"
  MSG_VENV_FAIL="ساخت محیط مجازی ناموفق بود. در لینوکس بسته python3-venv لازم است."
  MSG_DEPS="در حال نصب وابستگی‌های پروژه؛ ممکن است چند دقیقه طول بکشد ..."
  MSG_PIP_FAIL="نصب وابستگی‌ها ناموفق بود. اتصال اینترنت و پیام pip در بالا را بررسی کنید."
  MSG_MENU_TITLE="کدام بخش SubFa نصب شود؟"
  MSG_MENU_1="بات تلگرام"
  MSG_MENU_2="صفحه وب"
  MSG_MENU_3="خط فرمان (CLI)"
  MSG_CHOOSE="شماره را وارد کنید"
  MSG_INVALID="انتخاب نامعتبر است."
  MSG_TOKEN_SAVED="یک توکن بات در .env ذخیره شده است؛ همان استفاده شود؟"
  MSG_TOKEN_Q="توکن بات تلگرام (از BotFather؛ هنگام تایپ دیده نمی‌شود):"
  MSG_TOKEN_BAD="تلگرام این توکن را قبول نکرد؛ مقدارش را بررسی کنید."
  MSG_TRY_AGAIN="دوباره تلاش شود؟"
  MSG_ABORT="نصب متوقف شد."
  MSG_BOT_OK="توکن درست است؛ بات شما:"
  MSG_ADMIN_Q="آیدی عددی تلگرام شما (مالک بات)"
  MSG_ADMIN_BAD="آیدی باید فقط عدد باشد."
  MSG_ADMIN_NOTE="این آیدی فقط در .env ذخیره می‌شود تا برای استفاده خودتان دم دست باشد؛ رفتار بات را تغییر نمی‌دهد."
  MSG_ENV_SAVED="در فایل تنظیمات ذخیره شد:"
  MSG_MODELS_Q="مدل‌های گفتار و ترجمه همین حالا دانلود شوند؟ (حجم بالا، ولی بعدش همه‌چیز آفلاین کار می‌کند)"
  MSG_MODELS_Q_CLI="مدل‌های گفتار و ترجمه همین حالا دانلود شوند؟ (حجم بالا؛ بعدا هم با دستور subfa download-models می‌شود)"
  MSG_MODELS_RUN="در حال دانلود مدل‌ها؛ این مرحله ممکن است طول بکشد ..."
  MSG_MODELS_FAIL="دانلود مدل‌ها کامل نشد؛ بعدا با دستور subfa download-models ادامه دهید."
  MSG_RUNMODE_TITLE="روش اجرا:"
  MSG_RUNMODE_NOW="همین حالا در همین ترمینال اجرا شود"
  MSG_RUNMODE_SYSTEMD="نصب سرویس systemd (روی سرور: اجرای دائمی و شروع خودکار با روشن شدن سیستم)"
  MSG_RUNMODE_NONE="فقط نصب شود؛ خودم بعدا اجرا می‌کنم"
  MSG_SYSTEMD_SUDO="برای نصب سرویس، دسترسی sudo لازم است."
  MSG_SYSTEMD_OK="نصب و روشن شد:"
  MSG_SYSTEMD_FAIL="نصب سرویس کامل نشد؛ از دستور اجرای دستی پایین استفاده کنید."
  MSG_STARTING="در حال اجرا... برای توقف Ctrl+C را بزنید."
  MSG_RUN_CMD="دستور اجرا:"
  MSG_WEB_PORT_Q="پورت صفحه وب"
  MSG_WEB_PORT_BAD="پورت باید عددی بین 1 تا 65535 باشد."
  MSG_WEB_MODE_TITLE="صفحه وب چطور در دسترس باشد؟"
  MSG_WEB_MODE_1="دامنه دارم (HTTPS با گواهی رایگان)"
  MSG_WEB_MODE_2="دامنه ندارم؛ روی آی‌پی همین ماشین/سرور"
  MSG_DOMAIN_Q="نام دامنه (مثلا sub.example.com)"
  MSG_DOMAIN_BAD="نام دامنه معتبر به نظر نمی‌رسد."
  MSG_NGINX_Q="پروکسی nginx و گواهی HTTPS رایگان (Let's Encrypt) هم نصب و تنظیم شود؟"
  MSG_NGINX_INSTALL_Q="nginx و certbot نصب شوند؟"
  MSG_NGINX_INSTALL="در حال نصب nginx و certbot ..."
  MSG_NGINX_DONE="nginx تنظیم شد؛ در حال گرفتن گواهی HTTPS ..."
  MSG_NGINX_SKIP="بدون nginx ادامه می‌دهم؛ برنامه روی پورت انتخابی اجرا می‌شود و پروکسی را خودتان تنظیم کنید."
  MSG_NGINX_MANUAL="تنظیم خودکار nginx اینجا ممکن نیست؛ برنامه روی پورت انتخابی اجرا می‌شود. نمونه تنظیم nginx در docs/INSTALL.md هست."
  MSG_HTTPS_FAIL="گواهی HTTPS کامل نشد؛ صفحه فعلا با http روی دامنه جواب می‌دهد. دستور صدور گواهی برای تلاش دوباره:"
  MSG_ADDR="آدرس صفحه وب:"
  MSG_CLI_EXAMPLES="چند نمونه دستور واقعی:"
  MSG_SUMMARY="خلاصه نصب"
  MSG_SUM_INSTALLED="نصب شد:"
  MSG_SUM_ENV="فایل تنظیمات:"
  MSG_SUM_START="شروع:"
  MSG_SUM_STOP="توقف:"
  MSG_SUM_FG="در همان ترمینالی که اجرا شده با Ctrl+C متوقف می‌شود."
  MSG_DONE="تمام شد."
  MSG_GIT_MISSING="git پیدا نشد؛ برای دریافت کد پروژه لازم است."
  MSG_GIT_MANUAL="لطفا git را نصب کنید و این اسکریپت را دوباره اجرا کنید."
  MSG_DIR_TITLE="پروژه کجا نصب شود؟"
  MSG_CLONE_INTO="در حال دریافت کد پروژه در:"
  MSG_CLONE_FAIL="دریافت کد پروژه ناموفق بود؛ اتصال اینترنت و آدرس مخزن را بررسی کنید."
  MSG_DIR_BAD="این پوشه هست ولی چک‌اوت SubFa نیست؛ یک پوشه دیگر انتخاب کنید یا آن را خالی کنید:"
  MSG_REPO_REUSE="از چک‌اوت موجود استفاده می‌شود:"
else
  MSG_WELCOME="Welcome to the SubFa installer."
  MSG_PY_MISSING="Python 3.10 or newer was not found."
  MSG_FFMPEG_MISSING="ffmpeg was not found."
  MSG_INSTALL_OFFER_SUFFIX="Install it with the system package manager?"
  MSG_INSTALLING="Installing"
  MSG_STILL_MISSING="is still not available; install it manually and run this script again."
  MSG_MANUAL_PY="Please install Python 3.10 or newer from python.org and run this script again."
  MSG_MANUAL_FFMPEG="Please install ffmpeg (system package manager or ffmpeg.org) and run this script again."
  MSG_VENV_CREATE="Creating the virtual environment (.venv) ..."
  MSG_VENV_REUSE="A .venv already exists. Reuse it?"
  MSG_VENV_FAIL="Could not create the virtual environment. On Linux the python3-venv package is required."
  MSG_DEPS="Installing project dependencies; this can take a few minutes ..."
  MSG_PIP_FAIL="Dependency installation failed. Check your network and the pip output above."
  MSG_MENU_TITLE="Which SubFa surface should be installed?"
  MSG_MENU_1="Telegram bot"
  MSG_MENU_2="Web app"
  MSG_MENU_3="Command line (CLI)"
  MSG_CHOOSE="Enter a number"
  MSG_INVALID="Invalid choice."
  MSG_TOKEN_SAVED="A bot token is already saved in .env. Use it?"
  MSG_TOKEN_Q="Telegram bot token (from BotFather; hidden while typing):"
  MSG_TOKEN_BAD="Telegram did not accept this token; check the value."
  MSG_TRY_AGAIN="Try again?"
  MSG_ABORT="Installation stopped."
  MSG_BOT_OK="Token accepted. Your bot is:"
  MSG_ADMIN_Q="Your numeric Telegram ID (the bot owner)"
  MSG_ADMIN_BAD="The ID must be digits only."
  MSG_ADMIN_NOTE="This ID is only stored in .env for your own use; it does not change the bot's behavior."
  MSG_ENV_SAVED="Saved to the settings file:"
  MSG_MODELS_Q="Download the speech and translation models now? (large, but afterwards everything works offline)"
  MSG_MODELS_Q_CLI="Download the speech and translation models now? (large; you can also run subfa download-models later)"
  MSG_MODELS_RUN="Downloading models; this can take a while ..."
  MSG_MODELS_FAIL="Model download did not finish; run subfa download-models later to complete it."
  MSG_RUNMODE_TITLE="How should it run?"
  MSG_RUNMODE_NOW="Run now in this terminal"
  MSG_RUNMODE_SYSTEMD="Install a systemd service (VPS: always on, starts at boot)"
  MSG_RUNMODE_NONE="Install only; I will start it myself"
  MSG_SYSTEMD_SUDO="Installing the service needs sudo."
  MSG_SYSTEMD_OK="Installed and running:"
  MSG_SYSTEMD_FAIL="Service setup did not finish; use the manual run command below."
  MSG_STARTING="Starting... press Ctrl+C to stop."
  MSG_RUN_CMD="Run command:"
  MSG_WEB_PORT_Q="Web app port"
  MSG_WEB_PORT_BAD="Port must be a number between 1 and 65535."
  MSG_WEB_MODE_TITLE="How will the web app be reached?"
  MSG_WEB_MODE_1="I have a domain (HTTPS with a free certificate)"
  MSG_WEB_MODE_2="No domain; serve on this machine's IP"
  MSG_DOMAIN_Q="Domain name (for example sub.example.com)"
  MSG_DOMAIN_BAD="That domain name does not look valid."
  MSG_NGINX_Q="Also install and configure the nginx proxy and a free Let's Encrypt HTTPS certificate?"
  MSG_NGINX_INSTALL_Q="Install nginx and certbot?"
  MSG_NGINX_INSTALL="Installing nginx and certbot ..."
  MSG_NGINX_DONE="nginx is configured; requesting the HTTPS certificate ..."
  MSG_NGINX_SKIP="Continuing without nginx; the app will run on the chosen port and you can proxy it yourself."
  MSG_NGINX_MANUAL="Automatic nginx setup is not possible here; the app will run on the chosen port. A sample nginx config is in docs/INSTALL.md."
  MSG_HTTPS_FAIL="The HTTPS certificate step did not complete; the app answers on http for now. Retry the certificate later with:"
  MSG_ADDR="Web app address:"
  MSG_CLI_EXAMPLES="A few real example commands:"
  MSG_SUMMARY="Install summary"
  MSG_SUM_INSTALLED="Installed:"
  MSG_SUM_ENV="Settings file:"
  MSG_SUM_START="Start:"
  MSG_SUM_STOP="Stop:"
  MSG_SUM_FG="Stop it with Ctrl+C in the terminal where it runs."
  MSG_DONE="All done."
  MSG_GIT_MISSING="git was not found; it is needed to fetch the project."
  MSG_GIT_MANUAL="Please install git and run this script again."
  MSG_DIR_TITLE="Where should the project be installed?"
  MSG_CLONE_INTO="Fetching the project into:"
  MSG_CLONE_FAIL="Fetching the project failed; check your network and the repository URL."
  MSG_DIR_BAD="This folder exists but is not a SubFa checkout; pick another folder or empty it:"
  MSG_REPO_REUSE="Using the existing checkout at:"
fi

# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
say() { printf '%s\n' "$*"; }
sayf() { local _f="$1"; shift; printf "$_f\n" "$@"; }

ask() { # ask VAR "prompt"
  local _var="$1" _prompt="$2" _val=""
  printf '%s ' "$_prompt"
  read -r _val || _val=""
  printf -v "$_var" '%s' "$_val"
}

ask_default() { # ask_default VAR "prompt" "default"
  local _var="$1" _prompt="$2" _def="$3" _val=""
  if [ -n "$_def" ]; then
    printf '%s [%s]: ' "$_prompt" "$_def"
  else
    printf '%s: ' "$_prompt"
  fi
  read -r _val || _val=""
  [ -z "$_val" ] && _val="$_def"
  printf -v "$_var" '%s' "$_val"
}

ask_yes() { # default yes
  local _val=""
  printf '%s (Y/n): ' "$1"
  read -r _val || _val=""
  case "$_val" in n|N|no|No|NO) return 1 ;; *) return 0 ;; esac
}

ask_no() { # default no
  local _val=""
  printf '%s (y/N): ' "$1"
  read -r _val || _val=""
  case "$_val" in y|Y|yes|Yes|YES) return 0 ;; *) return 1 ;; esac
}

die() { say "$*"; exit 1; }

env_get() { # env_get KEY -> value on stdout ("" when absent)
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

env_set() { # env_set KEY VALUE ; preserves other lines, chmod 600
  local _key="$1" _val="$2" _tmp
  touch "$ENV_FILE"
  _tmp="$(mktemp)"
  grep -v -E "^${_key}=" "$ENV_FILE" > "$_tmp" || true
  printf '%s=%s\n' "$_key" "$_val" >> "$_tmp"
  mv "$_tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
}

# ------------------------------------------------------------------
# Prerequisites
# ------------------------------------------------------------------
find_python() {
  local _cand
  for _cand in python3 python; do
    if command -v "$_cand" >/dev/null 2>&1; then
      if "$_cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        PYBIN="$_cand"
        return 0
      fi
    fi
  done
  return 1
}

pkg_install() { # pkg_install <apt pkgs...> or <brew pkgs...>
  if [ "$OS_NAME" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    brew install "$@"
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y "$@"
  else
    return 1
  fi
}

have_pkg_manager() {
  if [ "$OS_NAME" = "Darwin" ]; then
    command -v brew >/dev/null 2>&1
  else
    command -v apt-get >/dev/null 2>&1
  fi
}

# ------------------------------------------------------------------
# Standalone bootstrap: when this script is not inside a SubFa
# checkout, clone the project first and continue inside the clone.
# ------------------------------------------------------------------
REPO_DIR="$SCRIPT_DIR"
if [ ! -f "$SCRIPT_DIR/pyproject.toml" ]; then
  REPO_URL="${SUBFA_REPO_URL:-https://github.com/E30TZ/subfa}"
  if ! command -v git >/dev/null 2>&1; then
    say "$MSG_GIT_MISSING"
    if have_pkg_manager && ask_yes "$MSG_INSTALL_OFFER_SUFFIX"; then
      say "$MSG_INSTALLING git ..."
      pkg_install git || true
    fi
    command -v git >/dev/null 2>&1 || die "$MSG_GIT_MANUAL"
  fi
  INSTALL_DIR="${SUBFA_INSTALL_DIR:-}"
  if [ -z "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/subfa"
    if [ "$OS_NAME" = "Linux" ] && [ -t 0 ] && command -v sudo >/dev/null 2>&1; then
      say "$MSG_DIR_TITLE"
      say "  1) $HOME/subfa"
      say "  2) /opt/subfa (sudo)"
      _dir_pick=""
      ask_default _dir_pick "$MSG_CHOOSE" "1"
      if [ "$_dir_pick" = "2" ]; then
        INSTALL_DIR="/opt/subfa"
      fi
    fi
  fi
  if [ -f "$INSTALL_DIR/pyproject.toml" ]; then
    say "$MSG_REPO_REUSE $INSTALL_DIR"
  else
    if [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
      die "$MSG_DIR_BAD $INSTALL_DIR"
    fi
    say "$MSG_CLONE_INTO $INSTALL_DIR"
    if git clone "$REPO_URL" "$INSTALL_DIR"; then
      :
    elif command -v sudo >/dev/null 2>&1 && sudo git clone "$REPO_URL" "$INSTALL_DIR"; then
      sudo chown -R "$(id -un)" "$INSTALL_DIR" || true
    else
      die "$MSG_CLONE_FAIL"
    fi
  fi
  REPO_DIR="$INSTALL_DIR"
fi
VENV_DIR="$REPO_DIR/.venv"
ENV_FILE="$REPO_DIR/.env"
cd "$REPO_DIR" || exit 1

if ! find_python; then
  say "$MSG_PY_MISSING"
  if have_pkg_manager && ask_yes "$MSG_INSTALL_OFFER_SUFFIX"; then
    say "$MSG_INSTALLING Python ..."
    if [ "$OS_NAME" = "Darwin" ]; then
      pkg_install python || true
    else
      pkg_install python3 python3-venv python3-pip || true
    fi
  fi
  if ! find_python; then
    say "Python $MSG_STILL_MISSING"
    die "$MSG_MANUAL_PY"
  fi
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  say "$MSG_FFMPEG_MISSING"
  if have_pkg_manager && ask_yes "$MSG_INSTALL_OFFER_SUFFIX"; then
    say "$MSG_INSTALLING ffmpeg ..."
    pkg_install ffmpeg || true
  fi
  if ! command -v ffmpeg >/dev/null 2>&1; then
    say "ffmpeg $MSG_STILL_MISSING"
    die "$MSG_MANUAL_FFMPEG"
  fi
fi

say "$MSG_WELCOME"

# ------------------------------------------------------------------
# Virtual environment
# ------------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
  if ask_yes "$MSG_VENV_REUSE"; then
    :
  else
    rm -rf "$VENV_DIR"
  fi
fi
if [ ! -d "$VENV_DIR" ]; then
  say "$MSG_VENV_CREATE"
  "$PYBIN" -m venv "$VENV_DIR" || die "$MSG_VENV_FAIL"
fi
VPY="$VENV_DIR/bin/python"
[ -x "$VPY" ] || die "$MSG_VENV_FAIL"
"$VPY" -m pip install --upgrade pip >/dev/null 2>&1 || true

install_pkg() { # install_pkg "extra1,extra2"
  say "$MSG_DEPS"
  "$VPY" -m pip install -e ".[$1]" || die "$MSG_PIP_FAIL"
}

run_models() {
  say "$MSG_MODELS_RUN"
  if "$VENV_DIR/bin/subfa" download-models; then
    return 0
  fi
  say "$MSG_MODELS_FAIL"
  return 1
}

# ------------------------------------------------------------------
# Run modes (bot and web share this menu)
# ------------------------------------------------------------------
# Globals used: SERVICE_NAME, SERVICE_DESC, EXEC_START, RUN_HINT
install_systemd() {
  local _unit _tmp
  _unit="/etc/systemd/system/${SERVICE_NAME}.service"
  _tmp="$(mktemp)"
  cat > "$_tmp" <<EOF
[Unit]
Description=${SERVICE_DESC}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${EXEC_START}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  say "$MSG_SYSTEMD_SUDO"
  if sudo cp "$_tmp" "$_unit" && sudo systemctl daemon-reload && sudo systemctl enable --now "$SERVICE_NAME"; then
    rm -f "$_tmp"
    say "$MSG_SYSTEMD_OK ${SERVICE_NAME}"
    return 0
  fi
  rm -f "$_tmp"
  say "$MSG_SYSTEMD_FAIL"
  return 1
}

run_mode_menu() { # run_mode_menu <now-command-as-string for printing>
  local _print_cmd="$1" _mode _has_systemd=0
  if [ "$OS_NAME" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
    _has_systemd=1
  fi
  say "$MSG_RUNMODE_TITLE"
  say "  1) $MSG_RUNMODE_NOW"
  if [ "$_has_systemd" = "1" ]; then
    say "  2) $MSG_RUNMODE_SYSTEMD"
    say "  3) $MSG_RUNMODE_NONE"
  else
    say "  2) $MSG_RUNMODE_NONE"
  fi
  ask_default _mode "$MSG_CHOOSE" "1"
  case "$_mode" in
    2)
      if [ "$_has_systemd" = "1" ]; then
        install_systemd || true
        return 2
      fi
      ;;
    3)
      if [ "$_has_systemd" = "1" ]; then
        say "$MSG_RUN_CMD $_print_cmd"
        return 3
      fi
      ;;
  esac
  if [ "$_mode" != "1" ]; then
    say "$MSG_INVALID"
    say "$MSG_RUN_CMD $_print_cmd"
    return 3
  fi
  return 1
}

# run_mode <print-cmd> : like run_mode_menu, but a --run flag wins.
# Same return codes: 1 = run now, 2 = systemd installed, 3 = not run.
run_mode() {
  local _print_cmd="$1"
  case "$F_RUN" in
    now) return 1 ;;
    none)
      say "$MSG_RUN_CMD $_print_cmd"
      return 3
      ;;
    service)
      if [ "$OS_NAME" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
        if install_systemd; then
          return 2
        fi
        say "$MSG_RUN_CMD $_print_cmd"
        return 3
      fi
      say "$MSG_SYSTEMD_FAIL"
      say "$MSG_RUN_CMD $_print_cmd"
      return 3
      ;;
  esac
  run_mode_menu "$_print_cmd"
}

# want_models <yes|no> <question> : a --models/--no-models flag wins,
# otherwise ask with the given default style.
want_models() {
  case "$F_MODELS" in
    yes) return 0 ;;
    no) return 1 ;;
  esac
  if [ "$1" = "yes" ]; then
    ask_yes "$2"
  else
    ask_no "$2"
  fi
}

# ------------------------------------------------------------------
# Branch: Telegram bot
# ------------------------------------------------------------------
branch_bot() {
  install_pkg "bot,translate,persian"

  local _existing _token="$F_TOKEN" _bot_user="" _admin _admin_def
  if [ -z "$_token" ]; then
    _existing="$(env_get BOT_TOKEN)"
    if [ -n "$_existing" ]; then
      if ask_yes "$MSG_TOKEN_SAVED"; then
        _token="$_existing"
      fi
    fi
  fi
  while [ -z "$_token" ]; do
    printf '%s ' "$MSG_TOKEN_Q"
    read -r -s _token || _token=""
    printf '\n'
    [ -n "$_token" ] || continue
    _bot_user="$(validate_token "$_token")" && break
    say "$MSG_TOKEN_BAD"
    _token=""
    ask_yes "$MSG_TRY_AGAIN" || die "$MSG_ABORT"
  done
  if [ -z "$_bot_user" ]; then
    _bot_user="$(validate_token "$_token")" || die "$MSG_TOKEN_BAD"
  fi
  say "$MSG_BOT_OK @${_bot_user}"

  if [ -n "$F_ADMIN" ]; then
    _admin="$F_ADMIN"
  else
    _admin_def="$(env_get SUBFA_ADMIN_ID)"
    while :; do
      ask_default _admin "$MSG_ADMIN_Q" "$_admin_def"
      case "$_admin" in
        ''|*[!0-9]*) say "$MSG_ADMIN_BAD" ;;
        *) break ;;
      esac
    done
  fi
  say "$MSG_ADMIN_NOTE"

  env_set BOT_TOKEN "$_token"
  env_set SUBFA_ADMIN_ID "$_admin"
  say "$MSG_ENV_SAVED $ENV_FILE"

  if want_models yes "$MSG_MODELS_Q"; then
    run_models || true
  fi

  SERVICE_NAME="subfa-bot"
  SERVICE_DESC="SubFa Telegram bot"
  EXEC_START="$VENV_DIR/bin/python -m bot.bot"
  say ""
  say "$MSG_SUMMARY"
  say "  $MSG_SUM_INSTALLED SubFa (bot, translate, persian)"
  say "  $MSG_SUM_ENV $ENV_FILE"
  run_mode "BOT_TOKEN=\$(grep '^BOT_TOKEN=' .env | cut -d= -f2-) $VENV_DIR/bin/python -m bot.bot"
  local _rc=$?
  if [ "$_rc" = "2" ]; then
    say "  $MSG_SUM_START sudo systemctl start subfa-bot"
    say "  $MSG_SUM_STOP sudo systemctl stop subfa-bot"
  elif [ "$_rc" = "1" ]; then
    say "$MSG_STARTING"
    export BOT_TOKEN="$_token"
    export SUBFA_ADMIN_ID="$_admin"
    cd "$REPO_DIR"
    exec "$VPY" -m bot.bot
  fi
  say "$MSG_DONE"
}

validate_token() { # validate_token TOKEN -> prints @username, rc 1 when bad
  "$VPY" - "$1" <<'PYEOF'
import json
import sys
import urllib.request

token = sys.argv[1]
try:
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/getMe"
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
except Exception:
    sys.exit(1)
if data.get("ok") and data.get("result", {}).get("username"):
    print(data["result"]["username"])
else:
    sys.exit(1)
PYEOF
}

# ------------------------------------------------------------------
# Branch: web app
# ------------------------------------------------------------------
detect_ip() {
  local _ip=""
  _ip="$(curl -s --max-time 5 https://ifconfig.me 2>/dev/null || true)"
  case "$_ip" in
    ''|*[!0-9.]*) _ip="$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || true)" ;;
  esac
  case "$_ip" in
    ''|*[!0-9.]*) _ip="your-server-ip" ;;
  esac
  printf '%s' "$_ip"
}

setup_nginx() { # uses DOMAIN, WEB_PORT ; sets HTTPS_OK=1 on full success
  HTTPS_OK=0
  if ! command -v nginx >/dev/null 2>&1 || ! command -v certbot >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1 && ask_yes "$MSG_NGINX_INSTALL_Q"; then
      say "$MSG_NGINX_INSTALL"
      sudo apt-get update && sudo apt-get install -y nginx certbot python3-certbot-nginx || true
    fi
  fi
  if ! command -v nginx >/dev/null 2>&1 || ! command -v certbot >/dev/null 2>&1; then
    say "$MSG_NGINX_MANUAL"
    return 1
  fi
  if [ ! -d /etc/nginx/sites-available ]; then
    say "$MSG_NGINX_MANUAL"
    return 1
  fi
  local _tmp
  _tmp="$(mktemp)"
  cat > "$_tmp" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
  say "$MSG_SYSTEMD_SUDO"
  sudo cp "$_tmp" /etc/nginx/sites-available/subfa || { rm -f "$_tmp"; return 1; }
  sudo ln -sf /etc/nginx/sites-available/subfa /etc/nginx/sites-enabled/subfa || true
  rm -f "$_tmp"
  if ! sudo nginx -t; then
    return 1
  fi
  sudo systemctl reload nginx 2>/dev/null || sudo nginx -s reload || true
  say "$MSG_NGINX_DONE"
  if sudo certbot --nginx -d "$DOMAIN"; then
    HTTPS_OK=1
  else
    say "$MSG_HTTPS_FAIL"
    say "  sudo certbot --nginx -d $DOMAIN"
  fi
  return 0
}

branch_web() {
  install_pkg "web,translate,persian"

  local _mode _ip
  if [ -n "$F_PORT" ]; then
    WEB_PORT="$F_PORT"
  else
    WEB_PORT=""
    while :; do
      ask_default WEB_PORT "$MSG_WEB_PORT_Q" "8000"
      case "$WEB_PORT" in
        ''|*[!0-9]*) say "$MSG_WEB_PORT_BAD" ;;
        *)
          if [ "$WEB_PORT" -ge 1 ] && [ "$WEB_PORT" -le 65535 ]; then
            break
          fi
          say "$MSG_WEB_PORT_BAD"
          ;;
      esac
    done
  fi

  if [ -n "$F_DOMAIN" ]; then
    _mode="1"
  elif [ "$F_IP" = "1" ]; then
    _mode="2"
  else
    say "$MSG_WEB_MODE_TITLE"
    say "  1) $MSG_WEB_MODE_1"
    say "  2) $MSG_WEB_MODE_2"
    ask_default _mode "$MSG_CHOOSE" "2"
  fi

  WEB_HOST="0.0.0.0"
  DOMAIN=""
  HTTPS_OK=0
  NGINX_USED=0
  if [ "$_mode" = "1" ]; then
    if [ -n "$F_DOMAIN" ]; then
      DOMAIN="$(printf '%s' "$F_DOMAIN" | sed -e 's|^https\?://||' -e 's|/.*$||')"
      case "$DOMAIN" in
        ''|*' '*) die "$MSG_DOMAIN_BAD" ;;
        *.*) : ;;
        *) die "$MSG_DOMAIN_BAD" ;;
      esac
    else
      while :; do
        ask_default DOMAIN "$MSG_DOMAIN_Q" ""
        DOMAIN="$(printf '%s' "$DOMAIN" | sed -e 's|^https\?://||' -e 's|/.*$||')"
        case "$DOMAIN" in
          ''|*' '*) say "$MSG_DOMAIN_BAD" ;;
          *.*) break ;;
          *) say "$MSG_DOMAIN_BAD" ;;
        esac
      done
    fi
    if [ "$OS_NAME" = "Linux" ]; then
      if ask_yes "$MSG_NGINX_Q"; then
        if setup_nginx; then
          NGINX_USED=1
          WEB_HOST="127.0.0.1"
        else
          say "$MSG_NGINX_SKIP"
        fi
      else
        say "$MSG_NGINX_SKIP"
      fi
    else
      say "$MSG_NGINX_MANUAL"
    fi
    if [ "$HTTPS_OK" = "1" ]; then
      say "$MSG_ADDR https://${DOMAIN}"
    elif [ "$NGINX_USED" = "1" ]; then
      say "$MSG_ADDR http://${DOMAIN}"
    else
      say "$MSG_ADDR http://${DOMAIN}:${WEB_PORT}"
    fi
  else
    _ip="$(detect_ip)"
    say "$MSG_ADDR http://${_ip}:${WEB_PORT}"
  fi

  if want_models yes "$MSG_MODELS_Q"; then
    run_models || true
  fi

  SERVICE_NAME="subfa-web"
  SERVICE_DESC="SubFa web app"
  EXEC_START="$VENV_DIR/bin/uvicorn web.app:app --host $WEB_HOST --port $WEB_PORT"
  say ""
  say "$MSG_SUMMARY"
  say "  $MSG_SUM_INSTALLED SubFa (web, translate, persian)"
  say "  $MSG_SUM_ENV $ENV_FILE"
  run_mode "$VENV_DIR/bin/uvicorn web.app:app --host $WEB_HOST --port $WEB_PORT"
  local _rc=$?
  if [ "$_rc" = "2" ]; then
    say "  $MSG_SUM_START sudo systemctl start subfa-web"
    say "  $MSG_SUM_STOP sudo systemctl stop subfa-web"
  elif [ "$_rc" = "1" ]; then
    say "$MSG_STARTING"
    cd "$REPO_DIR"
    exec "$VENV_DIR/bin/uvicorn" web.app:app --host "$WEB_HOST" --port "$WEB_PORT"
  fi
  say "$MSG_DONE"
}

# ------------------------------------------------------------------
# Branch: CLI
# ------------------------------------------------------------------
branch_cli() {
  install_pkg "translate,persian"

  if want_models no "$MSG_MODELS_Q_CLI"; then
    run_models || true
  fi

  say ""
  say "$MSG_CLI_EXAMPLES"
  say "  subfa lecture.mp4 --target fa --burn -o out/"
  say "  subfa https://www.youtube.com/watch?v=VIDEO_ID --target fa --burn"
  say "  subfa lesson.mkv --glossary programming --bilingual -o out/"
  say ""
  say "$MSG_SUMMARY"
  say "  $MSG_SUM_INSTALLED SubFa (core, translate, persian)"
  say "  $MSG_SUM_ENV $ENV_FILE"
  say "  $MSG_RUN_CMD $VENV_DIR/bin/subfa --help"
  say "$MSG_DONE"
}

# ------------------------------------------------------------------
# Main menu (skipped when --target was given)
# ------------------------------------------------------------------
if [ -n "$F_TARGET" ]; then
  case "$F_TARGET" in
    bot) branch_bot ;;
    web) branch_web ;;
    cli) branch_cli ;;
  esac
else
  say "$MSG_MENU_TITLE"
  say "  1) $MSG_MENU_1"
  say "  2) $MSG_MENU_2"
  say "  3) $MSG_MENU_3"
  ask_default MENU_CHOICE "$MSG_CHOOSE" "1"
  case "$MENU_CHOICE" in
    1) branch_bot ;;
    2) branch_web ;;
    3) branch_cli ;;
    *) die "$MSG_INVALID" ;;
  esac
fi
