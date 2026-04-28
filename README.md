# Kimi2API

一个基于 Kimi Web 协议实现的 OpenAI 兼容 API 服务，默认启动后可直接作为 `base_url` 给 OpenAI SDK、Cherry Studio、LobeChat、NextChat、one-api 风格客户端使用。

当前已实现的核心兼容接口：

- `GET /v1/models`
- `GET /v1/models/{model}`
- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/responses`
- `GET /healthz`

同时保留底层 Python 客户端能力：

- `await client.validate_token()`
- `await client.get_subscription()`
- `await client.get_research_usage()`
- `await client.chat.completions.create(...)`

## 安装

```bash
uv sync
```

或：

```bash
pip install -e .
```

## 配置

复制 `.env.example` 为 `.env`，至少配置：

```env
KIMI_TOKEN=your_kimi_jwt_token_here
OPENAI_API_KEY=sk-kimi2api
HOST=127.0.0.1
PORT=8000
```

说明：

- `KIMI_TOKEN` 是访问 Kimi 的真实 token
- `OPENAI_API_KEY` 是你暴露给 OpenAI 客户端使用的服务端鉴权 key
- 若未设置 `OPENAI_API_KEY`，服务端将不校验外部 Bearer Token
- `MODEL` 可选，默认基础模型为 `kimi-k2.5`

## 启动服务

```bash
uv run .\main.py
```

启动后默认地址：

```text
http://127.0.0.1:8000
```

## OpenAI SDK 用法

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-kimi2api",
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

## 模型别名

- `kimi-k2.5` / `kimi-k2`：默认不带思考、不带搜索
- `kimi-2.6-fast`：兼容 Kimi 2.6 Fast
- `kimi-2.6-thinking`：兼容 Kimi 2.6 思考
- `kimi-2.6-search`：兼容 Kimi 2.6 搜索
- `kimi-2.6-thinking-search` / `kimi-2.6-search-thinking`：同时开启思考和搜索
- `kimi-k2.5-thinking` / `kimi-k2-thinking`：开启思考
- `kimi-k2.5-search` / `kimi-k2-search`：开启搜索
- `kimi-k2.5-thinking-search` / `kimi-k2.5-search-thinking`：同时开启思考和搜索
- `kimi-k2-thinking-search` / `kimi-k2-search-thinking`：同时开启思考和搜索
- `kimi-thinking` / `kimi-search`：兼容旧别名，默认落到 `kimi-k2.5`
- `kimi-thinking-search` / `kimi-search-thinking`：兼容旧组合别名，默认落到 `kimi-k2.5`
- 也支持继续通过请求字段显式控制：`enable_thinking`、`reasoning`、`enable_web_search`、`web_search`、`search`

## curl 示例

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-kimi2api" \
  -d "{\"model\":\"kimi-k2.5\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}"
```

## Responses API 示例

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-kimi2api" \
  -d "{\"model\":\"kimi-k2.5\",\"input\":\"请总结一下 Kimi2API 的作用\"}"
```

## 设计说明

- KISS：服务端只做 OpenAI 协议兼容和 Kimi 协议转换，不做无关的中间层堆叠
- YAGNI：未提前实现 Kimi 不支持的图片、音频、嵌入真实能力，只对未支持端点返回标准错误
- DRY：统一了错误格式、请求特性提取、Responses/Chat 转换和 SSE 输出逻辑
- SOLID：客户端负责 Kimi 通信，服务端负责 OpenAI 兼容协议，两层职责分离

## 注意事项

- 这是基于 Kimi Web 协议的非官方实现，官方协议变更后可能需要同步修复
- 当前 `usage` 无法从 Kimi 流中准确统计，暂返回 `0`
- 未实现的 OpenAI 端点会返回 `501 unsupported_endpoint`
