# Kimi2API

Kimi2API 是一个基于 Kimi Web 协议封装的 OpenAI 兼容 API 服务。它把 Kimi 的聊天能力转换成常见的 `/v1` 接口，方便 OpenAI SDK、Cherry Studio、LobeChat、NextChat、one-api 风格客户端接入。

当前项目还内置了一个 `/admin` 管理面板，用于管理 Kimi token、管理本服务对外暴露的 API Key、查看最近请求日志。

> 说明：本项目不是 Moonshot 官方 API，也不是完整的 OpenAI API 实现。它只实现当前代码中列出的兼容接口。

## 功能

- OpenAI 兼容接口：Models、Chat Completions、Completions、Responses
- 支持流式和非流式输出
- 支持 Kimi thinking / search 相关模型别名和请求参数
- 支持 `conversation_id` / `session_id` 透传，用于延续会话
- 支持 Kimi token 面板配置、持久化和 refresh token 自动换取 access token
- 内置 API Key 管理、请求统计和最近请求日志
- 内置管理面板登录、CSRF 校验、登录失败限速、签名 Cookie 会话
- 支持 Docker Compose 部署，数据通过 `data/` 持久化

## 接口

公开接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 健康检查 |
| `GET` | `/admin` | 管理面板入口 |

根路径 `/` 不返回服务信息，避免在公网部署时暴露服务指纹和接口枚举。

OpenAI 兼容接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/v1/models` | 模型列表 |
| `GET` | `/v1/models/{model_id}` | 模型详情 |
| `POST` | `/v1/chat/completions` | Chat Completions |
| `POST` | `/v1/completions` | Legacy Completions |
| `POST` | `/v1/responses` | Responses API |

`/v1/*` 接口始终要求有效 API Key。可以通过 `OPENAI_API_KEY` 预置一个默认 Key，也可以登录管理面板创建 Key；如果系统里没有任何 Key，所有 OpenAI 兼容接口都会返回 `401`，避免误部署成公开可用服务。

```http
Authorization: Bearer your_api_key_here
```

## 快速开始

### 1. 准备环境

推荐使用 Python 3.12 和 [uv](https://github.com/astral-sh/uv)。`pyproject.toml` 声明最低 Python 版本为 3.8。

```bash
uv sync
cp .env.example .env
```

编辑 `.env`，至少填写：

```env
ADMIN_PASSWORD=your_admin_password
```

`KIMI_TOKEN` 可以在 `.env` 中预置，也可以启动后登录 `/admin` 在 Token 管理中保存。

本地 HTTP 访问管理面板时建议加上：

```env
SECURE_COOKIES=false
```

如果希望服务启动后立刻可以调用 `/v1/*` 接口，也需要设置：

```env
OPENAI_API_KEY=your_api_key_here
```

不填写 `OPENAI_API_KEY` 时，`/v1/*` 接口会先返回 `401`；启动后登录 `/admin` 创建 API Key，再用新 Key 调用接口。

### 2. 启动服务

```bash
uv run python run.py
```

默认监听：

```text
http://127.0.0.1:8000
```

管理面板：

```text
http://127.0.0.1:8000/admin
```

### 3. Docker Compose 部署

```bash
cp .env.example .env
# 编辑 .env 后启动
docker compose up -d
```

## 配置项

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KIMI_TOKEN` | 否 | 空 | Kimi 认证 token，支持 refresh token 和 JWT access token；为空时可在管理面板保存 |
| `KIMI_API_BASE` | 否 | `https://www.kimi.com` | Kimi Web 服务地址 |
| `TIMEOUT` | 否 | `120` | 请求超时时间，单位秒 |
| `MODEL` | 否 | `kimi-k2.5` | 默认模型；`.env.example` 中示例为 `kimi-k2.6` |
| `OPENAI_API_KEY` | 否 | 空 | 本服务对外暴露的默认 API Key；为空时需先在管理面板创建 Key，否则 `/v1/*` 全部拒绝访问 |
| `ADMIN_PASSWORD` | 是 | 空 | 管理面板密码；为空时管理面板不可用 |
| `SESSION_SECRET` | 否 | 自动生成 | 管理面板 Cookie 签名密钥；为空时写入 `data/.session_secret` |
| `SECURE_COOKIES` | 否 | `true` | Cookie 是否带 `Secure` 标记；本地 HTTP 调试设为 `false` |
| `HOST` | 否 | `127.0.0.1` | 监听地址 |
| `PORT` | 否 | `8000` | 监听端口 |
| `RELOAD` | 否 | `false` | 是否启用 uvicorn 热重载 |
| `DATA_DIR` | 否 | `data` | 本地数据目录 |

## Kimi Token

`KIMI_TOKEN` 支持两类值，也可以在管理面板的 Token 管理中保存：

- Refresh token：推荐使用，服务会在需要时调用刷新接口换取 access token。
- JWT access token：短期有效，过期后需要重新获取或改用 refresh token。

可以在浏览器登录 Kimi 后，从 Cookie 或网络请求中提取对应 token。管理面板保存的 token 会写入 `data/kimi_token.json`，重启后优先使用该文件中的值。

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
        {"role": "user", "content": "请用一句话介绍 Kimi2API。"},
    ],
)

print(resp.choices[0].message.content)
```

### Chat Completions

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{
    "model": "kimi-k2.5",
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'
```

### 流式输出

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{
    "model": "kimi-k2.5-thinking",
    "stream": true,
    "messages": [
      {"role": "user", "content": "解释一下快速排序"}
    ]
  }'
```

### Responses API

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key_here" \
  -d '{
    "model": "kimi-k2.5-search",
    "input": "今天有什么值得关注的 AI 新闻？"
  }'
```

### 延续会话

请求体中可以传入 `conversation_id`、`conversationId`、`session_id` 或 `sessionId`：

```json
{
  "model": "kimi-k2.5",
  "conversation_id": "your-conversation-id",
  "messages": [
    {"role": "user", "content": "继续上一个话题"}
  ]
}
```

## 模型和功能开关

当前 `/v1/models` 会返回以下模型别名：

- `kimi-k2.5`
- `kimi-k2.5-thinking`
- `kimi-k2.5-search`
- `kimi-k2.5-thinking-search`
- `kimi-2.6-fast`
- `kimi-2.6-thinking`
- `kimi-2.6-search`
- `kimi-2.6-thinking-search`
- `kimi-k2`
- `kimi-k2-thinking`
- `kimi-k2-search`
- `kimi-k2-thinking-search`
- `kimi-thinking`
- `kimi-search`
- `kimi-thinking-search`

也可以通过请求字段显式开启能力：

```json
{
  "enable_thinking": true,
  "enable_web_search": true
}
```

兼容字段：

- thinking：`enable_thinking`、`reasoning`
- search：`enable_web_search`、`web_search`、`search`

## 管理面板

访问 `/admin` 后使用 `ADMIN_PASSWORD` 登录。面板包含：

- 服务概览：运行时间、token 状态、Key 数量、请求统计
- Token 管理：新增或替换 token、查看 token 类型、过期时间、手动刷新、验证 token
- API Key 管理：创建、查看、删除本服务对外暴露的 Key
- 请求日志：查看最近 200 条 `/v1/*` 请求记录

API Key 存储在：

```text
data/api_keys.json
```

管理面板保存的 Kimi token 存储在：

```text
data/kimi_token.json
```

会话签名密钥默认存储在：

```text
data/.session_secret
```

## 项目结构

```text
app/
  api/                 # OpenAI 兼容 API 路由和转换逻辑
  core/                # 鉴权、Key 存储、请求日志、token 管理
  dashboard/           # /admin 管理面板
  kimi/                # Kimi Web 协议客户端
  static/              # 前端静态资源
  config.py            # 环境变量配置
  main.py              # FastAPI 应用入口
run.py                 # 本地启动入口
Dockerfile             # 容器镜像构建
docker-compose.yml     # Compose 部署配置
```

## 开发

```bash
uv sync
uv run python -m compileall app run.py
uv run python run.py
```

常用检查：

```bash
git status --short
git diff --check
```

## 安全提醒

- 生产环境请设置强 `ADMIN_PASSWORD` 和稳定的 `SESSION_SECRET`。
- 公开部署时建议使用 HTTPS，并保持 `SECURE_COOKIES=true`。
- 如果已经暴露过真实 Kimi token 或 API Key，请立即轮换。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。

## 致谢

感谢原项目 [XxxXTeam/kimi2api](https://github.com/XxxXTeam/kimi2api) 的基础实现和思路，本项目在此基础上继续二次开发。
