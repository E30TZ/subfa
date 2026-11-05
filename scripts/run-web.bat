@echo off
rem Start the SubFa web app (Windows). Creates and reuses .venv.
cd /d "%~dp0.."
if not exist .venv (
    py -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements\web.txt
uvicorn web.app:app --host 0.0.0.0 --port 8000
