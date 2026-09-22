@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem ============================================================
rem  机上有几个 Python 是不确定的（系统版 / venv / 商店版），
rem  这里逐个候选去试，取第一个版本 >= 3.9 的。
rem  本项目 0 第三方依赖，只要能跑 Python 即可，不需要 pip install。
rem ============================================================

call :pick
if errorlevel 1 exit /b 1

if not exist "data\vocab.db" (
  if not exist "data\ecdict.csv" (
    echo.
    echo [提示] 还缺第三方数据（音标 / 词典 / 例句，约 74 MB）。
    echo        请先运行：  python fetch_data.py
    echo        下完再双击本文件即可。
    echo.
    pause
    exit /b 1
  )
  echo 首次运行，正在建库（约 60-90 秒）...
  %PY% -X utf8 import_data.py
  if errorlevel 1 (
    echo.
    echo [错误] 建库失败。若缺少 data\ecdict.csv，请见 README 的说明。
    pause
    exit /b 1
  )
)

echo.
echo   考研单词背诵系统  http://127.0.0.1:5178
echo   按 Ctrl+C 停止
echo.
%PY% -X utf8 app.py
pause
exit /b 0

:pick
set "PY="
set "PYVER="
for %%A in ("py -3" "python3" "python") do (
  if not defined PY (
    %%~A -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=%%~A"
  )
)
if not defined PY (
  echo.
  echo [错误] 没有找到 Python 3.9 或更高版本。
  echo        请到 https://www.python.org/downloads/ 安装，
  echo        安装时务必勾选 "Add python.exe to PATH"。
  echo.
  echo        也可以手动指定解释器，例如：
  echo            "C:\path\to\python.exe" -X utf8 app.py
  echo.
  exit /b 1
)
for /f "delims=" %%V in ('%PY% -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYVER=%%V"
echo [解释器] %PY%   版本 %PYVER%
exit /b 0
