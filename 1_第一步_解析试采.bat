@echo off
chcp 936 >nul
cd /d "%~dp0"
setlocal
set "PY=D:\python\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo   ============================================
echo    寰宇图志 . 第一步：解析 + 试采 5 国
echo   ============================================
echo     0 体检  1 解析 QID  2 试采  3 审核页
echo     大约 10~25 分钟（取决于网络）
echo.
echo   如果代理没被 Python 继承，加参数再跑一次：
echo     --proxy http://127.0.0.1:7890
echo.
echo   ============================================
echo.

"%PY%" scripts\step1_preview.py %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo   [未全部通过] 退出码 %RC% ，看上面的提示。
if "%RC%"=="0" echo   [完成] 审核页已经自动打开，看完再双击 2_全量采集.bat
echo.
pause
