@echo off
node "%~dp0work\tools\npm\package\bin\npm-cli.js" %*
exit /b %errorlevel%
