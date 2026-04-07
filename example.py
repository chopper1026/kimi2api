import asyncio
import os

import httpx
from dotenv import load_dotenv


async def main():
    load_dotenv()
    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8000")
    api_key = os.getenv("OPENAI_API_KEY", "sk-kimi2api")

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120.0,
    ) as client:
        models = await client.get("/v1/models")
        print("Models:", models.json())

        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "kimi-k2.5",
                "messages": [
                    {"role": "system", "content": "你是一个有帮助的AI助手。"},
                    {"role": "user", "content": "你好，请用一句话介绍你自己。"},
                ],
            },
        )
        print("\nChat completion:")
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())
