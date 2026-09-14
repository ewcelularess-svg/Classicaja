@echo off
cd /d %~dp0
if not exist .venv py -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
