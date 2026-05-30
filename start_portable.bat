@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "ENV_DIR=%ROOT%.pixi\envs\default"
set "PYTHON=%ENV_DIR%\python.exe"

if not exist "%PYTHON%" (
  echo 未找到便携包内置 Python:
  echo %PYTHON%
  echo.
  echo 当前便携包不完整，请使用 scripts\package_portable_release.py 重新打包。
  pause
  exit /b 1
)

for %%D in (
  "%ROOT%runtime"
  "%ROOT%runtime\cache"
  "%ROOT%runtime\logs"
  "%ROOT%runtime\outputs"
  "%ROOT%runtime\temp"
  "%ROOT%runtime\temp\gradio"
  "%ROOT%runtime\temp\uploads"
) do (
  if not exist "%%~D" mkdir "%%~D"
)

set "PATH=%ENV_DIR%;%ENV_DIR%\Scripts;%ENV_DIR%\Library\bin;%ENV_DIR%\Library\usr\bin;%PATH%"
set "PYTHONPATH=%ROOT%;%ROOT%CosyVoice;%ROOT%CosyVoice\third_party\Matcha-TTS;%PYTHONPATH%"
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "TOKENIZERS_PARALLELISM=false"
set "TQDM_DISABLE=1"
set "TMPDIR=%ROOT%runtime\temp"
set "TEMP=%ROOT%runtime\temp"
set "TMP=%ROOT%runtime\temp"
set "GRADIO_TEMP_DIR=%ROOT%runtime\temp\gradio"
set "MODELSCOPE_CACHE=%ROOT%models\_cache\modelscope"
set "MODELSCOPE_MODULES_CACHE=%ROOT%models\_cache\modelscope\modules"
set "HF_HOME=%ROOT%models\_cache\huggingface"
set "HF_HUB_CACHE=%ROOT%models\_cache\huggingface\hub"
set "HUGGINGFACE_HUB_CACHE=%ROOT%models\_cache\huggingface\hub"
set "TRANSFORMERS_CACHE=%ROOT%models\_cache\huggingface\transformers"
set "XDG_CACHE_HOME=%ROOT%models\_cache\xdg"
set "TORCH_HOME=%ROOT%models\_cache\torch"

:menu
echo.
echo Neiroha CosyVoice3 便携版
echo.
echo   1. 启动 API + 管理界面
echo   2. 仅启动 API
echo   3. 仅启动管理界面
echo   4. 启动官方 CosyVoice WebUI
echo   5. 帮助
echo.
set "CHOICE="
set /p CHOICE=请选择 [1-5]，然后按回车：
if "%CHOICE%"=="" set "CHOICE=1"

if "%CHOICE%"=="1" goto api_admin
if "%CHOICE%"=="2" goto api_only
if "%CHOICE%"=="3" goto admin_only
if "%CHOICE%"=="4" goto official_webui
if "%CHOICE%"=="5" goto help
echo 未知选项: %CHOICE%
goto menu

:api_admin
"%PYTHON%" "%ROOT%scripts\launch_engine.py" --surface both
goto end

:api_only
"%PYTHON%" "%ROOT%scripts\launch_engine.py" --surface api
goto end

:admin_only
"%PYTHON%" "%ROOT%scripts\launch_engine.py" --surface admin
goto end

:official_webui
"%PYTHON%" "%ROOT%CosyVoice\webui.py" --port 8000 --model_dir "%ROOT%models\Fun-CosyVoice3-0.5B"
goto end

:help
echo.
echo 默认 FastAPI: http://127.0.0.1:9880
echo 默认管理界面: http://127.0.0.1:7880
echo.
echo 如需修改监听地址、端口、启动模式、预加载、模型预设或界面语言，请编辑 configs\server.toml。
echo 运行输出、日志、临时文件和缓存都会保存在当前便携包目录下。
echo.
pause
goto menu

:end
endlocal
