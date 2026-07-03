# Football Quant Prediction

足球量化预测系统原型，包含历史数据采集、特征工程、五步法预测引擎、FastAPI 后端、Celery 任务、Next.js 前端和 Docker Compose 本地环境。

## 当前状态

这个仓库目前更接近「研究原型 + 产品骨架」：

- 根目录脚本可用于数据抓取、每日预测、回测和报告生成。
- `engine/` 已实现主要量化规则、机构共识、指数验证、市场定价、仓位管理等模块。
- `backend/` 已搭好 FastAPI、SQLAlchemy、Alembic、Celery 结构，但多数业务接口仍是占位实现。
- `frontend/` 已搭好 Next.js 页面和导航，但主要业务页面仍是占位界面。
- 生产级闭环还缺少完整测试、真实接口实现、模型训练流水线和数据质量监控。

## 目录结构

```text
backend/        FastAPI API、ORM、任务队列和数据库迁移
data/           数据采集、ETL、训练集构建和数据源客户端
engine/         量化预测引擎和五步法决策管道
frontend/       Next.js 前端应用
model/          传统 Elo/球队评级训练脚本
models_store/   本地模型文件目录，不提交模型产物
reports/        自动生成报告目录，不纳入版本控制
docker/         Dockerfile 和 Nginx 配置
```

## 快速开始

1. 复制环境变量：

```bash
cp .env.example .env
```

2. 编辑 `.env`，填入需要的数据源和通知密钥。

3. 使用 Docker 启动全栈环境：

```bash
docker-compose up -d
```

4. 运行数据库迁移：

```bash
docker-compose exec backend alembic upgrade head
```

5. 访问服务：

- 后端健康检查：http://localhost:8000/health
- 后端文档：http://localhost:8000/docs
- 前端：http://localhost:3000

## 常用命令

```bash
make up              # 启动服务
make down            # 停止服务
make logs-backend    # 查看后端日志
make db-migrate      # 执行数据库迁移
make lint            # 后端 Ruff + 前端 ESLint
make format          # 后端 Ruff format + 前端 Prettier
```

本地不使用 Docker 时，后端代码默认假设 `backend/` 是 Python 工作目录，或需要显式设置 `PYTHONPATH`。

## Telegram Bot

机器人入口是 `bot.py`，使用 API-Football 查询赛程和胜平负赔率。找不到 API-Football fixture 时会直接返回未找到比赛，不再回退到其他数据源。

常用命令：

- `/分析 法国 vs 瑞典`：支持中文国家队名、常见女足写法和部分常用俱乐部别名。
- `vps瓦萨vs图尔库国际`：不带命令、不带空格也会按单场比赛分析。
- `/今日`：展示今日赛事并用 API-Football 胜平负赔率参与分析。
- `/热门`：筛选最近几天热门赛事，优先展示有 API-Football 胜平负赔率的数据。

需要的环境变量：

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
API_FOOTBALL_KEYS=
API_FOOTBALL_HOST=v3.football.api-sports.io
```

本地启动：

```bash
python -u bot.py
```

## Railway 部署

仓库包含 `railway.json` 和 `Procfile`，Railway 会以后台 worker 方式运行 Telegram 长轮询机器人，不需要暴露 HTTP 端口。

部署步骤：

1. 在 Railway 新建项目，选择 `Deploy from GitHub repo`。
2. 选择 `unique555/football-quant-prediction`。
3. 在 service 的 `Variables` 中添加 `.env` 里的密钥，至少包括：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `API_FOOTBALL_KEYS`
   - `API_FOOTBALL_HOST=v3.football.api-sports.io`
4. 部署后查看 Logs，看到 `机器人启动... Offset ... 等待消息...` 即表示运行中。

## 代码规范

Python 使用 Ruff 统一导入、基础静态检查和格式化；前端使用 ESLint + Prettier。

```bash
uvx ruff check .
uvx ruff format .
cd frontend && npm install && npm run lint
```

## 后续重点

- 把根目录脚本逐步迁移为包内 CLI，移除硬编码 `/workspace/football-quant-prediction` 路径。
- 为 `engine/` 的核心决策模块增加单元测试和回归测试。
- 将 FastAPI 占位接口接入真实 service，并统一请求/响应 schema。
- 为数据源接入、赔率异常、模型漂移和回测收益增加监控。
- 建立训练集版本、模型版本、特征版本和回测结果之间的可追溯关系。
