import os
import json
from typing import Dict
from anyio import open_file

async def read_json(file_path: str) -> Dict[str, str]:
    if not os.path.exists(file_path):
        return {}
    try:
        async with await open_file(file_path, mode="r", encoding="utf-8") as file:
            content = await file.read()
            return json.loads(content) if content else {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


async def write_json(file_path: str, data: dict):
    try:
        async with await open_file(file_path, mode="w", encoding="utf-8") as file:
            await file.write(json.dumps(data, indent=4, ensure_ascii=False))
    except IOError as e:
        print(f"Error writing JSON file: {e}")