# Football Quant Prediction — Makefile

.PHONY: help up down build logs shell-backend shell-db clean reset test lint migrate

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## 启动所有服务
	docker compose up -d

down: ## 停止所有服务
	docker compose down

restart: down up ## 重启所有服务

build: ## 重新构建镜像
	docker compose build --no-cache

logs: ## 查看所有日志
	docker compose logs -f

logs-backend: ## 查看后端日志
	docker compose logs -f backend

logs-worker: ## 查看 Celery worker 日志
	docker compose logs -f worker

logs-frontend: ## 查看前端日志
	docker compose logs -f frontend

shell-backend: ## 进入后端容器
	docker compose exec backend /bin/bash

db-migrate: ## 运行数据库迁移
	docker compose exec backend alembic upgrade head

migrate: db-migrate ## db-migrate 的别名

test: ## 运行 Python 单元测试
	python -m pytest tests

db-reset: ## 重置数据库（危险！）
	docker compose down -v postgres
	docker compose up -d postgres
	@sleep 3
	$(MAKE) db-migrate

bootstrap: ## 导入基础数据（英超）
	docker compose exec backend python -m data.etl.bootstrap --league epl

train: ## 训练初始模型
	docker compose exec backend python -m engine.ml.train_football

backtest: ## 运行回测
	docker compose exec backend python -m engine.evaluate.backtest

lint: ## 代码检查
	docker compose exec backend ruff check .
	cd frontend && npx eslint .

format: ## 代码格式化
	docker-compose exec backend ruff format .
	cd frontend && npx prettier --write .

setup-dev: ## 初始化本地开发环境
	cp -n .env.example .env 2>/dev/null || true
	cd frontend && pnpm install
	pip install -r backend/requirements.txt
	@echo "✅ 开发环境初始化完成，请编辑 .env 填入 API Key"
