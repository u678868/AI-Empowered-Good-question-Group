# AI Empowered - 常用开发命令
PY ?= .venv/Scripts/python.exe

.PHONY: help install install-dev test run clean

help:
	@echo "make install      - 安装运行依赖"
	@echo "make install-dev  - 安装开发依赖"
	@echo "make test         - 运行测试"
	@echo "make run          - 运行程序入口"
	@echo "make clean        - 清理缓存"

install:
	$(PY) -m pip install -r requirements.txt

install-dev:
	$(PY) -m pip install -r requirements-dev.txt

test:
	$(PY) -m pytest

run:
	$(PY) -m src.main

clean:
	@echo "已清理（占位目标）"

package:
	$(PY) scripts/package_submission.py
