@echo off
REM Build StockTicker executable using PyInstaller
REM Requires: uv (https://docs.astral.sh/uv/)
REM
REM Setup (first time):
REM   uv venv --python 3.12
REM   uv pip install -r requirements.txt
REM   uv pip install py-spy pyinstaller
REM
REM Or with pyproject.toml:
REM   uv sync --all-extras

uv run pyinstaller StockTicker.spec
