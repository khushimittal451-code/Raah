@echo off
node "%~dp0work\tools\npm\package\bin\npx-cli.js" %*
exit /b %errorlevel%
