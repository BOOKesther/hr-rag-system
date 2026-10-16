$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.uv-python'
$env:GRADIO_ANALYTICS_ENABLED = 'False'
$env:PYTHONIOENCODING = 'utf-8'
uv sync --frozen --python 3.12
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查 uv 和网络连接。' }
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m app
