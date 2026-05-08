import json


def sse(event: str, data: dict) -> bytes:
    text = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    return text.encode("utf-8")
