# SubFa interactive installer for Windows (PowerShell).
#
# From zero to a running SubFa: checks Python 3.10+ and ffmpeg,
# builds .venv, then lets you pick the Telegram bot, the web app
# or the CLI, and asks only the questions that surface needs.
#
# Usage:  powershell -ExecutionPolicy Bypass -File install.ps1 [install] [-Target bot|web|cli] [...]
#
# Mirrors install.sh (Linux and macOS) flow for flow. The systemd
# and nginx/Let's Encrypt steps are Linux VPS features and are not
# offered here; the web branch says so honestly.
#
# When this script is NOT inside a SubFa checkout it first clones
# the project (default %USERPROFILE%\subfa) and then continues the
# wizard inside the clone, so a copy fetched on its own is enough:
#
#   irm https://raw.githubusercontent.com/E30TZ/subfa/main/install.ps1 | iex

param(
    [Parameter(Position = 0)][string]$Command,
    [string]$Target,
    [string]$Token,
    [string]$AdminId,
    [int]$Port = 0,
    [string]$Domain,
    [switch]$Ip,
    [switch]$Models,
    [switch]$NoModels,
    [string]$Run,
    [string]$Lang
)

function Print-Usage {
    Write-Host 'Usage: install.ps1 [install] [options]'
    Write-Host ''
    Write-Host 'Options:'
    Write-Host '  -Target bot|web|cli  Install only this surface (skip the menu)'
    Write-Host '  -Token TOKEN         Telegram bot token (bot target)'
    Write-Host '  -AdminId NUMBER      Your numeric Telegram ID (bot target)'
    Write-Host '  -Port NUMBER         Web app port (web target, default 8000)'
    Write-Host '  -Domain DOMAIN       Serve the web app behind this domain (web target)'
    Write-Host '  -Ip                  Serve the web app on this machine''s IP (web target)'
    Write-Host '  -Models              Download the speech and translation models'
    Write-Host '  -NoModels            Skip the model download'
    Write-Host '  -Run now|none        How to run it after the install'
    Write-Host '  -Lang fa|en          Installer language'
    Write-Host ''
    Write-Host 'With no parameters the interactive wizard runs. Given parameters'
    Write-Host 'fill in the matching wizard answers; anything still missing is asked.'
    Write-Host 'Environment: SUBFA_INSTALL_DIR overrides the clone directory and'
    Write-Host 'SUBFA_REPO_URL overrides the repository cloned in standalone mode.'
}

if ($Command -and $Command -ne 'install') { Print-Usage; exit 2 }
if ($Target -and $Target -notin @('bot', 'web', 'cli')) { Print-Usage; exit 2 }
if ($Run -and $Run -notin @('now', 'service', 'none')) { Print-Usage; exit 2 }
if ($Lang -and $Lang -notin @('fa', 'en')) { Print-Usage; exit 2 }
if ($AdminId -and $AdminId -notmatch '^\d+$') { Print-Usage; exit 2 }
if ($Port -ne 0 -and ($Port -lt 1 -or $Port -gt 65535)) { Print-Usage; exit 2 }

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = 'Continue'

$RepoDir = $PSScriptRoot
if (-not $RepoDir) { $RepoDir = (Get-Location).Path }

# ------------------------------------------------------------------
# Language: Persian by default, English on request.
# ------------------------------------------------------------------
Write-Host 'SubFa installer'
if ($Lang) {
    $UiLang = $Lang
} else {
    Write-Host '1) فارسی'
    Write-Host '2) English'
    $LangChoice = Read-Host 'Language / زبان [1]'
    if ($LangChoice -eq '2' -or $LangChoice -match '^(en|english)$') {
        $UiLang = 'en'
    } else {
        $UiLang = 'fa'
    }
}

if ($UiLang -eq 'fa') {
    $M = @{
        Welcome        = 'به نصب‌کننده SubFa خوش آمدید.'
        PyMissing      = 'Python نسخه 3.10 یا بالاتر پیدا نشد.'
        FfmpegMissing  = 'ffmpeg پیدا نشد.'
        InstallOffer   = 'با winget نصب شود؟'
        Installing     = 'در حال نصب'
        StillMissing   = 'هنوز در دسترس نیست؛ لطفا دستی نصب کنید و دوباره اجرا کنید.'
        ManualPy       = 'لطفا Python 3.10 یا بالاتر را از python.org نصب کنید و این اسکریپت را دوباره اجرا کنید.'
        ManualFfmpeg   = 'لطفا ffmpeg را نصب کنید (از ffmpeg.org یا winget) و دوباره اجرا کنید.'
        ReopenNote     = 'نصب شد؛ این پنجره PowerShell را ببندید، یک پنجره تازه باز کنید و اسکریپت را دوباره اجرا کنید تا PATH تازه شود.'
        VenvCreate     = 'در حال ساخت محیط مجازی (.venv) ...'
        VenvReuse      = 'محیط مجازی .venv از قبل هست؛ همان استفاده شود؟'
        VenvFail       = 'ساخت محیط مجازی ناموفق بود.'
        Deps           = 'در حال نصب وابستگی‌های پروژه؛ ممکن است چند دقیقه طول بکشد ...'
        PipFail        = 'نصب وابستگی‌ها ناموفق بود. اتصال اینترنت و پیام pip در بالا را بررسی کنید.'
        MenuTitle      = 'کدام بخش SubFa نصب شود؟'
        Menu1          = 'بات تلگرام'
        Menu2          = 'صفحه وب'
        Menu3          = 'خط فرمان (CLI)'
        Choose         = 'شماره را وارد کنید'
        Invalid        = 'انتخاب نامعتبر است.'
        TokenSaved     = 'یک توکن بات در .env ذخیره شده است؛ همان استفاده شود؟'
        TokenQ         = 'توکن بات تلگرام (از BotFather؛ هنگام تایپ دیده نمی‌شود)'
        TokenBad       = 'تلگرام این توکن را قبول نکرد؛ مقدارش را بررسی کنید.'
        TryAgain       = 'دوباره تلاش شود؟'
        Abort          = 'نصب متوقف شد.'
        BotOk          = 'توکن درست است؛ بات شما:'
        AdminQ         = 'آیدی عددی تلگرام شما (مالک بات)'
        AdminBad       = 'آیدی باید فقط عدد باشد.'
        AdminNote      = 'این آیدی فقط در .env ذخیره می‌شود تا برای استفاده خودتان دم دست باشد؛ رفتار بات را تغییر نمی‌دهد.'
        EnvSaved       = 'در فایل تنظیمات ذخیره شد:'
        ModelsQ        = 'مدل‌های گفتار و ترجمه همین حالا دانلود شوند؟ (حجم بالا، ولی بعدش همه‌چیز آفلاین کار می‌کند)'
        ModelsQCli     = 'مدل‌های گفتار و ترجمه همین حالا دانلود شوند؟ (حجم بالا؛ بعدا هم با دستور subfa download-models می‌شود)'
        ModelsRun      = 'در حال دانلود مدل‌ها؛ این مرحله ممکن است طول بکشد ...'
        ModelsFail     = 'دانلود مدل‌ها کامل نشد؛ بعدا با دستور subfa download-models ادامه دهید.'
        RunModeTitle   = 'روش اجرا:'
        RunModeNow     = 'همین حالا در همین پنجره اجرا شود'
        RunModeNone    = 'فقط نصب شود؛ خودم بعدا اجرا می‌کنم'
        Starting       = 'در حال اجرا... برای توقف Ctrl+C را بزنید.'
        RunCmd         = 'دستور اجرا:'
        WebPortQ       = 'پورت صفحه وب'
        WebPortBad     = 'پورت باید عددی بین 1 تا 65535 باشد.'
        WebModeTitle   = 'صفحه وب چطور در دسترس باشد؟'
        WebMode1       = 'دامنه دارم'
        WebMode2       = 'دامنه ندارم؛ روی آی‌پی همین ماشین'
        DomainQ        = 'نام دامنه (مثلا sub.example.com)'
        DomainBad      = 'نام دامنه معتبر به نظر نمی‌رسد.'
        WinDomainNote  = 'در ویندوز این نصب‌کننده nginx و گواهی HTTPS نصب نمی‌کند؛ برنامه روی پورت انتخابی اجرا می‌شود. رکورد DNS دامنه را به آی‌پی این ماشین وصل کنید و اگر پروکسی معکوس دارید، آن را به همین پورت وصل کنید. برای HTTPS آماده روی سرور لینوکسی، همین نصب‌کننده را روی VPS اجرا کنید.'
        Addr           = 'آدرس صفحه وب:'
        CliExamples    = 'چند نمونه دستور واقعی:'
        Summary        = 'خلاصه نصب'
        SumInstalled   = 'نصب شد:'
        SumEnv         = 'فایل تنظیمات:'
        Done           = 'تمام شد.'
        GitMissing     = 'git پیدا نشد؛ برای دریافت کد پروژه لازم است.'
        GitManual      = 'لطفا git را نصب کنید و این اسکریپت را دوباره اجرا کنید.'
        CloneInto      = 'در حال دریافت کد پروژه در:'
        CloneFail      = 'دریافت کد پروژه ناموفق بود؛ اتصال اینترنت و آدرس مخزن را بررسی کنید.'
        DirBad         = 'این پوشه هست ولی چک‌اوت SubFa نیست؛ یک پوشه دیگر انتخاب کنید یا آن را خالی کنید:'
        RepoReuse      = 'از چک‌اوت موجود استفاده می‌شود:'
        ServiceNA      = 'سرویس systemd گزینه لینوکسی است؛ در ویندوز از دستور اجرا استفاده کنید.'
    }
} else {
    $M = @{
        Welcome        = 'Welcome to the SubFa installer.'
        PyMissing      = 'Python 3.10 or newer was not found.'
        FfmpegMissing  = 'ffmpeg was not found.'
        InstallOffer   = 'Install it with winget?'
        Installing     = 'Installing'
        StillMissing   = 'is still not available; install it manually and run this script again.'
        ManualPy       = 'Please install Python 3.10 or newer from python.org and run this script again.'
        ManualFfmpeg   = 'Please install ffmpeg (ffmpeg.org or winget) and run this script again.'
        ReopenNote     = 'Installed. Close this PowerShell window, open a fresh one, and run the script again so PATH is refreshed.'
        VenvCreate     = 'Creating the virtual environment (.venv) ...'
        VenvReuse      = 'A .venv already exists. Reuse it?'
        VenvFail       = 'Could not create the virtual environment.'
        Deps           = 'Installing project dependencies; this can take a few minutes ...'
        PipFail        = 'Dependency installation failed. Check your network and the pip output above.'
        MenuTitle      = 'Which SubFa surface should be installed?'
        Menu1          = 'Telegram bot'
        Menu2          = 'Web app'
        Menu3          = 'Command line (CLI)'
        Choose         = 'Enter a number'
        Invalid        = 'Invalid choice.'
        TokenSaved     = 'A bot token is already saved in .env. Use it?'
        TokenQ         = 'Telegram bot token (from BotFather; hidden while typing)'
        TokenBad       = 'Telegram did not accept this token; check the value.'
        TryAgain       = 'Try again?'
        Abort          = 'Installation stopped.'
        BotOk          = 'Token accepted. Your bot is:'
        AdminQ         = 'Your numeric Telegram ID (the bot owner)'
        AdminBad       = 'The ID must be digits only.'
        AdminNote      = 'This ID is only stored in .env for your own use; it does not change the bot''s behavior.'
        EnvSaved       = 'Saved to the settings file:'
        ModelsQ        = 'Download the speech and translation models now? (large, but afterwards everything works offline)'
        ModelsQCli     = 'Download the speech and translation models now? (large; you can also run subfa download-models later)'
        ModelsRun      = 'Downloading models; this can take a while ...'
        ModelsFail     = 'Model download did not finish; run subfa download-models later to complete it.'
        RunModeTitle   = 'How should it run?'
        RunModeNow     = 'Run now in this window'
        RunModeNone    = 'Install only; I will start it myself'
        Starting       = 'Starting... press Ctrl+C to stop.'
        RunCmd         = 'Run command:'
        WebPortQ       = 'Web app port'
        WebPortBad     = 'Port must be a number between 1 and 65535.'
        WebModeTitle   = 'How will the web app be reached?'
        WebMode1       = 'I have a domain'
        WebMode2       = 'No domain; serve on this machine''s IP'
        DomainQ        = 'Domain name (for example sub.example.com)'
        DomainBad      = 'That domain name does not look valid.'
        WinDomainNote  = 'On Windows this installer does not install nginx or an HTTPS certificate; the app runs on the chosen port. Point the domain DNS at this machine, and your own reverse proxy at this port if you use one. For ready HTTPS on a Linux server, run this same installer on the VPS.'
        Addr           = 'Web app address:'
        CliExamples    = 'A few real example commands:'
        Summary        = 'Install summary'
        SumInstalled   = 'Installed:'
        SumEnv         = 'Settings file:'
        Done           = 'All done.'
        GitMissing     = 'git was not found; it is needed to fetch the project.'
        GitManual      = 'Please install git and run this script again.'
        CloneInto      = 'Fetching the project into:'
        CloneFail      = 'Fetching the project failed; check your network and the repository URL.'
        DirBad         = 'This folder exists but is not a SubFa checkout; pick another folder or empty it:'
        RepoReuse      = 'Using the existing checkout at:'
        ServiceNA      = 'systemd services are a Linux option; on Windows use the run command.'
    }
}

# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
function Say($Text) { Write-Host $Text }

function AskDefault($Prompt, $Default) {
    if ($Default) {
        $v = Read-Host "$Prompt [$Default]"
    } else {
        $v = Read-Host $Prompt
    }
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v.Trim()
}

function AskYes($Prompt) {
    $v = Read-Host "$Prompt (Y/n)"
    return ($v -notmatch '^(n|no)$')
}

function AskNo($Prompt) {
    $v = Read-Host "$Prompt (y/N)"
    return ($v -match '^(y|yes)$')
}

function Get-EnvValue($Key) {
    if (-not (Test-Path $EnvFile)) { return '' }
    $pat = '^' + [regex]::Escape($Key) + '='
    $line = Get-Content $EnvFile | Where-Object { $_ -match $pat } | Select-Object -Last 1
    if ($line) { return $line.Substring($Key.Length + 1) }
    return ''
}

function Set-EnvValue($Key, $Value) {
    $pat = '^' + [regex]::Escape($Key) + '='
    $lines = @()
    if (Test-Path $EnvFile) {
        $lines = @(Get-Content $EnvFile | Where-Object { $_ -notmatch $pat })
    }
    $lines += ($Key + '=' + $Value)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($EnvFile, [string[]]$lines, $enc)
    try {
        icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
    } catch { }
}

function Test-PyCandidate($Cmd, $Launcher) {
    if (-not (Get-Command $Cmd -ErrorAction SilentlyContinue)) { return $false }
    if ($Launcher) {
        & $Cmd -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
    } else {
        & $Cmd -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
    }
    return ($LASTEXITCODE -eq 0)
}

function Find-Python {
    if (Test-PyCandidate 'python' $false) { $script:UseLauncher = $false; return $true }
    if (Test-PyCandidate 'py' $true) { $script:UseLauncher = $true; return $true }
    return $false
}

function Invoke-BasePy {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)
    if ($script:UseLauncher) { & py -3 @Rest } else { & python @Rest }
}

function Test-BotToken($Token) {
    try {
        $r = Invoke-RestMethod -Method Get -Uri ("https://api.telegram.org/bot" + $Token + "/getMe") -TimeoutSec 20
        if ($r.ok -and $r.result.username) { return $r.result.username }
    } catch { }
    return $null
}

function Read-Token {
    $sec = Read-Host $M.TokenQ -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Want-Models($Style, $Question) {
    if ($Models) { return $true }
    if ($NoModels) { return $false }
    if ($Style -eq 'yes') { return (AskYes $Question) }
    return (AskNo $Question)
}

# ------------------------------------------------------------------
# Standalone bootstrap: when this script is not inside a SubFa
# checkout, clone the project first and continue inside the clone.
# ------------------------------------------------------------------
if (-not (Test-Path (Join-Path $RepoDir 'pyproject.toml'))) {
    $repoUrl = $env:SUBFA_REPO_URL
    if (-not $repoUrl) { $repoUrl = 'https://github.com/E30TZ/subfa' }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Say $M.GitMissing
        if ((Get-Command winget -ErrorAction SilentlyContinue) -and (AskYes $M.InstallOffer)) {
            Say "$($M.Installing) Git ..."
            winget install --exact --id Git.Git --accept-package-agreements --accept-source-agreements
            Say $M.ReopenNote
            exit 0
        }
        Say $M.GitManual
        exit 1
    }
    $installDir = $env:SUBFA_INSTALL_DIR
    if (-not $installDir) { $installDir = Join-Path $env:USERPROFILE 'subfa' }
    if (Test-Path (Join-Path $installDir 'pyproject.toml')) {
        Say "$($M.RepoReuse) $installDir"
    } else {
        if ((Test-Path $installDir) -and (Get-ChildItem $installDir -Force | Select-Object -First 1)) {
            Say "$($M.DirBad) $installDir"
            exit 1
        }
        Say "$($M.CloneInto) $installDir"
        git clone $repoUrl $installDir
        if ($LASTEXITCODE -ne 0) { Say $M.CloneFail; exit 1 }
    }
    $RepoDir = $installDir
}
Set-Location $RepoDir
$VenvDir = Join-Path $RepoDir '.venv'
$EnvFile = Join-Path $RepoDir '.env'

# ------------------------------------------------------------------
# Prerequisites
# ------------------------------------------------------------------
if (-not (Find-Python)) {
    Say $M.PyMissing
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (AskYes $M.InstallOffer)) {
        Say "$($M.Installing) Python ..."
        winget install --exact --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Say $M.ReopenNote
        exit 0
    }
    Say "Python $($M.StillMissing)"
    Say $M.ManualPy
    exit 1
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Say $M.FfmpegMissing
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (AskYes $M.InstallOffer)) {
        Say "$($M.Installing) ffmpeg ..."
        winget install --exact --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
        Say $M.ReopenNote
        exit 0
    }
    Say "ffmpeg $($M.StillMissing)"
    Say $M.ManualFfmpeg
    exit 1
}

Say $M.Welcome

# ------------------------------------------------------------------
# Virtual environment
# ------------------------------------------------------------------
if (Test-Path $VenvDir) {
    if (-not (AskYes $M.VenvReuse)) {
        Remove-Item $VenvDir -Recurse -Force
    }
}
if (-not (Test-Path $VenvDir)) {
    Say $M.VenvCreate
    Invoke-BasePy -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Say $M.VenvFail; exit 1 }
}
$VPy = Join-Path $VenvDir 'Scripts\python.exe'
$VUvicorn = Join-Path $VenvDir 'Scripts\uvicorn.exe'
$VSubfa = Join-Path $VenvDir 'Scripts\subfa.exe'
if (-not (Test-Path $VPy)) { Say $M.VenvFail; exit 1 }
& $VPy -m pip install --upgrade pip 2>$null | Out-Null

function Install-Pkg($Extras) {
    Say $M.Deps
    & $VPy -m pip install -e ".[$Extras]"
    if ($LASTEXITCODE -ne 0) { Say $M.PipFail; exit 1 }
}

function Invoke-Models {
    Say $M.ModelsRun
    & $VSubfa download-models
    if ($LASTEXITCODE -ne 0) { Say $M.ModelsFail }
}

function Select-RunMode($PrintCmd) {
    if ($Run) {
        if ($Run -eq 'now') { return 1 }
        if ($Run -eq 'service') { Say $M.ServiceNA }
        Say "$($M.RunCmd) $PrintCmd"
        return 2
    }
    Say $M.RunModeTitle
    Say "  1) $($M.RunModeNow)"
    Say "  2) $($M.RunModeNone)"
    $mode = AskDefault $M.Choose '1'
    if ($mode -eq '1') { return 1 }
    if ($mode -ne '2') { Say $M.Invalid }
    Say "$($M.RunCmd) $PrintCmd"
    return 2
}

# ------------------------------------------------------------------
# Branch: Telegram bot
# ------------------------------------------------------------------
function Install-Bot {
    Install-Pkg 'bot,translate,persian'

    $token = ''
    if ($Token) {
        $token = $Token
    } else {
        $existing = Get-EnvValue 'BOT_TOKEN'
        if ($existing -and (AskYes $M.TokenSaved)) { $token = $existing }
    }
    $botUser = $null
    while (-not $token) {
        $candidate = Read-Token
        if (-not $candidate) { continue }
        $botUser = Test-BotToken $candidate
        if ($botUser) { $token = $candidate; break }
        Say $M.TokenBad
        if (-not (AskYes $M.TryAgain)) { Say $M.Abort; exit 1 }
    }
    if (-not $botUser) { $botUser = Test-BotToken $token }
    if (-not $botUser) { Say $M.TokenBad; exit 1 }
    Say "$($M.BotOk) @$botUser"

    if ($AdminId) {
        $admin = $AdminId
    } else {
        $adminDefault = Get-EnvValue 'SUBFA_ADMIN_ID'
        while ($true) {
            $admin = AskDefault $M.AdminQ $adminDefault
            if ($admin -match '^\d+$') { break }
            Say $M.AdminBad
        }
    }
    Say $M.AdminNote

    Set-EnvValue 'BOT_TOKEN' $token
    Set-EnvValue 'SUBFA_ADMIN_ID' $admin
    Say "$($M.EnvSaved) $EnvFile"

    if (Want-Models 'yes' $M.ModelsQ) { Invoke-Models }

    Say ''
    Say $M.Summary
    Say "  $($M.SumInstalled) SubFa (bot, translate, persian)"
    Say "  $($M.SumEnv) $EnvFile"
    $printCmd = "`$env:BOT_TOKEN = (Get-Content .env | Where-Object { `$_ -match '^BOT_TOKEN=' }) -replace '^BOT_TOKEN=', ''; .venv\Scripts\python.exe -m bot.bot"
    $rc = Select-RunMode $printCmd
    if ($rc -eq 1) {
        Say $M.Starting
        $env:BOT_TOKEN = $token
        $env:SUBFA_ADMIN_ID = $admin
        & $VPy -m bot.bot
    }
    Say $M.Done
}

# ------------------------------------------------------------------
# Branch: web app
# ------------------------------------------------------------------
function Install-Web {
    Install-Pkg 'web,translate,persian'

    if ($Port -ne 0) {
        $port = $Port
    } else {
        while ($true) {
            $portText = AskDefault $M.WebPortQ '8000'
            $port = 0
            if ([int]::TryParse($portText, [ref]$port) -and $port -ge 1 -and $port -le 65535) { break }
            Say $M.WebPortBad
        }
    }

    if ($Domain) {
        $mode = '1'
    } elseif ($Ip) {
        $mode = '2'
    } else {
        Say $M.WebModeTitle
        Say "  1) $($M.WebMode1)"
        Say "  2) $($M.WebMode2)"
        $mode = AskDefault $M.Choose '2'
    }

    $webHost = '0.0.0.0'
    if ($mode -eq '1') {
        if ($Domain) {
            $domain = $Domain -replace '^https?://', '' -replace '/.*$', ''
            if (-not $domain -or $domain -match '\s' -or $domain -notmatch '\.') {
                Say $M.DomainBad
                exit 1
            }
        } else {
            while ($true) {
                $domain = AskDefault $M.DomainQ ''
                $domain = $domain -replace '^https?://', '' -replace '/.*$', ''
                if ($domain -and $domain -notmatch '\s' -and $domain -match '\.') { break }
                Say $M.DomainBad
            }
        }
        Say $M.WinDomainNote
        Say "$($M.Addr) http://${domain}:${port}"
    } else {
        Say "$($M.Addr) http://localhost:${port}"
        try {
            $ip = Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 5
            if ($ip -match '^\d+\.\d+\.\d+\.\d+$') {
                Say "$($M.Addr) http://${ip}:${port}"
            }
        } catch { }
    }

    if (Want-Models 'yes' $M.ModelsQ) { Invoke-Models }

    Say ''
    Say $M.Summary
    Say "  $($M.SumInstalled) SubFa (web, translate, persian)"
    Say "  $($M.SumEnv) $EnvFile"
    $printCmd = ".venv\Scripts\uvicorn.exe web.app:app --host $webHost --port $port"
    $rc = Select-RunMode $printCmd
    if ($rc -eq 1) {
        Say $M.Starting
        & $VUvicorn web.app:app --host $webHost --port $port
    }
    Say $M.Done
}

# ------------------------------------------------------------------
# Branch: CLI
# ------------------------------------------------------------------
function Install-Cli {
    Install-Pkg 'translate,persian'

    if (Want-Models 'no' $M.ModelsQCli) { Invoke-Models }

    Say ''
    Say $M.CliExamples
    Say '  subfa lecture.mp4 --target fa --burn -o out/'
    Say '  subfa https://www.youtube.com/watch?v=VIDEO_ID --target fa --burn'
    Say '  subfa lesson.mkv --glossary programming --bilingual -o out/'
    Say ''
    Say $M.Summary
    Say "  $($M.SumInstalled) SubFa (core, translate, persian)"
    Say "  $($M.SumEnv) $EnvFile"
    Say "  $($M.RunCmd) .venv\Scripts\subfa.exe --help"
    Say $M.Done
}

# ------------------------------------------------------------------
# Main menu (skipped when -Target was given)
# ------------------------------------------------------------------
if ($Target) {
    switch ($Target) {
        'bot' { Install-Bot }
        'web' { Install-Web }
        'cli' { Install-Cli }
    }
} else {
    Say $M.MenuTitle
    Say "  1) $($M.Menu1)"
    Say "  2) $($M.Menu2)"
    Say "  3) $($M.Menu3)"
    $choice = AskDefault $M.Choose '1'
    switch ($choice) {
        '1' { Install-Bot }
        '2' { Install-Web }
        '3' { Install-Cli }
        default { Say $M.Invalid; exit 1 }
    }
}
