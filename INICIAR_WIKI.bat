@echo off
cd /d "%~dp0"
python iniciar_wiki.py
if errorlevel 1 pause
