@echo off
cd /d %~dp0
start "ClassificaJa Backend" cmd /k "cd /d %~dp0backend && iniciar_backend.bat"
timeout /t 3 >nul
start "ClassificaJa Site" cmd /k "cd /d %~dp0frontend && iniciar_site.bat"
exit
