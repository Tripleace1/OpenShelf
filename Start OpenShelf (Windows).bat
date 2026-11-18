@echo off
title OpenShelf
cd /d "%~dp0"
where py >nul 2>nul && (py -3 openshelf.py & goto :end)
where python >nul 2>nul && (python openshelf.py & goto :end)
echo.
echo  Python is not installed.
echo  Download it from https://www.python.org/downloads/
echo  and tick "Add Python to PATH" during setup, then run this file again.
echo.
:end
pause
