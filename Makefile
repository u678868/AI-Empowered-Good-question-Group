# AI Empowered - 常用开发命令
PY ?= .venv/Scripts/python.exe

.PHONY: help install install-dev test run clean audit submission package check

help:
	@echo "make install      - 安装运行依赖"
	@echo "make install-dev  - 安装开发依赖"
	@echo "make test         - 运行测试"
	@echo "make run          - 运行程序入口"
	@echo "make audit        - 红线扫描 + 全量测试 + 前端语法检查"
	@echo "make submission   - 生成 submission/ 镜像（推送到 Group 仓库的内容）"
	@echo "make package      - 生成镜像与邮件提交压缩包"
	@echo "make check        - 校验 submission/ 镜像是否干净"
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

audit:
	$(PY) scripts/scan_guardrails.py
	$(PY) -m pytest -q -p no:cacheprovider
	node --check web/app.js

submission:
	$(PY) scripts/package_submission.py --mirror

package:
	$(PY) scripts/package_submission.py

check:
	$(PY) scripts/package_submission.py --check
