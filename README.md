# Kimi2API

基于 Kimi Web 协议的 OpenAI 兼容 API 服务，支持 Docker 一键部署。启动后可直接作为 `base_url` 给 OpenAI SDK、Cherry Studio、LobeChat、NextChat、one-api 等客户端使用。

## 功能特性

### OpenAI 兼容接口

- `GET /v1/models` — 模型列表
- `GET /v1/models/{model}` — 模型详情
- `POST /v1/chat/completions` — Chat Completions（流式/非流式）
- `POST /v1/completions` — Completions（非流式）
- `POST /v1/responses` — Responses API（流式/非流式）
- `GET /healthz` — 健康检查

### 管理控制台

内置 Web 管理面板（`/admin`），支持：

- **服务概览** — 运行时间、Token 状态、请求统计
- **Token 管理** — 状态监控、手动刷新、有效性验证
- **API Key 管理** — 多 Key 创建/吊销，支持独立命名
- **请求日志** — 最近 1000 条请求记录，含模型、状态码、耗时

### 安全机制

- API 接口和面板鉴权独立：API 用 Bearer Token，面板用独立管理员密码
- 登录限速：5 次失败/15 分钟/IP
- 签名 Cookie 会话，支持 HTTPS 安全标记
- 密码比较防时序攻击

## 快速开始

### 环境要求

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)（推荐）或 pip

### 配置

复制 `.env.example` 为 `.env`：

```env
# Kimi Token（必填，支持 JWT 和 Refresh Token）
KIMI_TOKEN=your_token_here

# 对外暴露的 API Key
OPENAI_API_KEY=your_api_key_here

# 管理面板密码（设置后启用面板）
ADMIN_PASSWORD=your_admin_password

# 服务监听
HOST=127.0.0.1
PORT=8000
```

### 启动

```bash
uv sync
uv run python run.py
```

### Docker 部署

```bash
docker compose up -d
```

环境变量通过 `.env` 文件或 `docker-compose.yml` 的 `environment` 配置。

## 使用示例

### OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="your_api_key_here",
    base_url="http://127.0.0.1:8000/v1",
)

resp = client.chat.completions.create(
    model="kimi-k2.5",
    messages=[
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "请介绍一下你自己。"},
    ],
)

print(resp.choices[0].message.content)
```

### curl

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{"model":"kimi-k2.5","messages":[{"role":"user","content":"你好"}]}'
```

### Responses API

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{"model":"kimi-k2.5","input":"请总结一下 Kimi2API 的作用"}'
```

## 支持的模型

通过模型别名自动控制思考和搜索能力：

| 别名格式 | 说明 |
|---------|------|
| `kimi-k2.5` | 默认，不带思考、不带搜索 |
| `kimi-k2.5-thinking` | 开启思考 |
| `kimi-k2.5-search` | 开启搜索 |
| `kimi-k2.5-thinking-search` | 同时开启思考和搜索 |
| `kimi-k2` | k2 基础模型 |
| `kimi-2.6-fast` | Kimi 2.6 Fast |
| `kimi-2.6-thinking` | Kimi 2.6 思考 |
| `kimi-2.6-search` | Kimi 2.6 搜索 |

也支持通过请求字段显式控制：`enable_thinking`、`enable_web_search`。

## Token 说明

支持两种 Token 格式：

- **Refresh Token**（推荐）：以 `cpmt_` 开头，服务自动换取短期 access token 并定时刷新
- **JWT Access Token**：以 `eyJ` 开头，有效期较短，过期后需重新获取

获取方式：浏览器登录 [kimi.com](https://kimi.com)，从开发者工具的 Cookie 或网络请求中提取。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `KIMI_TOKEN` | 是 | — | Kimi 认证 Token |
| `OPENAI_API_KEY` | 否 | 空 | API 鉴权 Key，建议通过管理面板创建 |
| `ADMIN_PASSWORD` | 否 | — | 管理面板密码，设置后启用 |
| `HOST` | 否 | `127.0.0.1` | 监听地址 |
| `PORT` | 否 | `8000` | 监听端口 |
| `MODEL` | 否 | `kimi-k2.5` | 默认模型 |
| `TIMEOUT` | 否 | `120` | 请求超时（秒） |
| `SESSION_SECRET` | 否 | 随机 | Cookie 签名密钥，不设则重启失效 |
| `SECURE_COOKIES` | 否 | `true` | HTTPS 环境设 true |
| `DATA_DIR` | 否 | `data` | 数据持久化目录 |

## 项目结构

```
app/
├── main.py                 # FastAPI 应用工厂 + 启动入口
├── config.py               # 集中配置管理
├── api/                    # OpenAI 兼容 API
│   ├── routes.py           # /v1/* 路由
│   └── deps.py             # 依赖注入 + 工具函数
├── core/                   # 核心业务
│   ├── auth.py             # 管理员鉴权
│   ├── keys.py             # API Key 存储
│   ├── logs.py             # 请求日志
│   └── token_manager.py    # Token 自动刷新
├── kimi/                   # Kimi 客户端
│   ├── protocol.py         # Connect/gRPC 协议 + 数据模型
│   └── client.py           # HTTP 客户端
└── dashboard/              # 管理面板
    ├── routes.py           # /admin/* 路由
    └── templates/          # Jinja2 模板
```

## 注意事项

- 基于 Kimi Web 协议的非官方实现，官方协议变更后可能需要同步修复
- `usage` 无法从 Kimi 流中准确统计，暂返回 `0`
- 未实现的 OpenAI 端点返回 `501 unsupported_endpoint`
