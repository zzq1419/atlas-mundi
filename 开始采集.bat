@echo off
setlocal
cd /d "%~dp0"

set "PY="
for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY if exist "D:\python\python.exe" set "PY=D:\python\python.exe"
if not defined PY (
  echo.
  echo [x] 没找到 python。请先安装 Python 3.10+，或把 D:\python\python.exe 改成本机的路径。
  echo.
  pause
  exit /b 1
)

:menu
cls
echo ============================================
echo   寰宇图志 · 全量采集
echo   python: %PY%
echo ============================================
echo.
echo   [1] 看规模（不采集，只统计还差多少）
echo   [2] 解析国家编号（先跑一次，约 10 分钟）
echo   [3] 采集正文+图片（可反复跑，自动跳过已完成）
echo   [4] 大模型处理（需要 DEEPSEEK_API_KEY）
echo   [5] 生成语音（需要 edge-tts）
echo   [6] 收尾：压图 + 重建索引
echo   [7] 上传到华为云 OBS
echo   [8] 全流程（2 到 7）
echo   [0] 退出
echo.
set /p CH=输入序号后回车：
if "%CH%"=="1" goto plan
if "%CH%"=="2" goto ids
if "%CH%"=="3" goto collect
if "%CH%"=="4" goto llm
if "%CH%"=="5" goto speech
if "%CH%"=="6" goto finish
if "%CH%"=="7" goto upload
if "%CH%"=="8" goto all
if "%CH%"=="0" exit /b 0
goto menu

:plan
"%PY%" scripts\collect_all.py --plan
goto done

:ids
echo.
echo 提示：代理没覆盖维基媒体会全部失败。可先在另一个窗口 set HTTPS_PROXY=...
echo.
"%PY%" scripts\collect_all.py --stage ids
goto done

:collect
echo.
set /p N=只跑前几个国家？直接回车 = 全部：
if "%N%"=="" (
  "%PY%" scripts\collect_all.py --stage collect
) else (
  "%PY%" scripts\collect_all.py --stage collect --limit %N%
)
goto done

:llm
if "%DEEPSEEK_API_KEY%"=="" (
  echo.
  echo [!] 没有 DEEPSEEK_API_KEY。先在本窗口执行：
  echo     set DEEPSEEK_API_KEY=sk-xxxx
  echo 然后重新运行本菜单。
  goto done
)
"%PY%" scripts\collect_all.py --stage llm
goto done

:speech
"%PY%" scripts\collect_all.py --stage speech
goto done

:finish
"%PY%" scripts\collect_all.py --stage images
"%PY%" scripts\collect_all.py --stage index
goto done

:upload
if "%HUAWEI_AK%"=="" (
  echo.
  echo [!] 没有 HUAWEI_AK / HUAWEI_SK，先在本窗口 set 好再运行。
  goto done
)
"%PY%" scripts\collect_all.py --stage upload
goto done

:all
"%PY%" scripts\collect_all.py --all
goto done

:done
echo.
echo ---------------- 结束 ----------------
pause
goto menu
