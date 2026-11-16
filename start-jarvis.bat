@echo off
cd /d C:\jarvis
:loop
.venv\Scripts\python.exe bot.py
echo Bot stopped. Restarting in 10 seconds... (close this window to stop it)
timeout /t 10
goto loop
