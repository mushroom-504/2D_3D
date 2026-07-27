import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from config_loader import get_section


MAX_INPUT_BYTES = 10 * 1024 * 1024


def _api_config():
    config = get_section("craftsman_api")
    key_env = str(config.get("api_key_env", "CRAFTSMAN_API_KEY"))
    api_key = os.environ.get(key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"CraftsMan API key is missing. Set {key_env} in the project .env file."
        )
    return config, api_key


def _request_json(url, api_key, payload=None, timeout=300):
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"CraftsMan API returned HTTP {exc.code}: {body[:1000]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to CraftsMan API: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"CraftsMan API returned invalid JSON: {body[:1000]}") from exc


def check_health(timeout=30):
    config, api_key = _api_config()
    url = str(config.get("health_url", "")).strip()
    if not url:
        raise RuntimeError("craftsman_api.health_url is missing in config.json.")
    return _request_json(url, api_key, timeout=timeout)


def generate(input_path, output_path, timeout=300):
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.is_file():
        raise RuntimeError(f"Input image not found: {input_path}")
    size = input_path.stat().st_size
    if size <= 0 or size > MAX_INPUT_BYTES:
        raise RuntimeError(
            f"Input image size must be between 1 byte and 10 MB: {size:,} bytes"
        )

    config, api_key = _api_config()
    url = str(config.get("generate_url", "")).strip()
    if not url:
        raise RuntimeError("craftsman_api.generate_url is missing in config.json.")
    image_base64 = base64.b64encode(input_path.read_bytes()).decode("ascii")
    payload = {
        "image_base64": image_base64,
        "steps": int(config.get("steps", 50)),
        "seed": int(config.get("seed", 0)),
        "guidance_scale": float(config.get("guidance_scale", 5.0)),
        "octree_depth": int(config.get("octree_depth", 7)),
        "remove_background": bool(config.get("remove_background", True)),
        "foreground_ratio": float(config.get("foreground_ratio", 1.0)),
    }
    result = _request_json(url, api_key, payload=payload, timeout=timeout)
    if not result.get("success"):
        raise RuntimeError(f"CraftsMan API generation failed: {result}")
    encoded_obj = result.get("obj_base64")
    if not encoded_obj:
        raise RuntimeError("CraftsMan API response does not contain obj_base64.")
    try:
        obj_data = base64.b64decode(encoded_obj, validate=True)
    except Exception as exc:
        raise RuntimeError("CraftsMan API returned invalid OBJ Base64 data.") from exc
    if len(obj_data) < 100:
        raise RuntimeError("CraftsMan API returned an empty or incomplete OBJ.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(obj_data)
    metadata = {
        "remote_task_id": result.get("task_id"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "format": result.get("format", "obj"),
        "output": str(output_path),
    }
    output_path.with_suffix(".api.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def main():
    parser = argparse.ArgumentParser(description="CraftsMan remote API bridge")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    metadata = generate(args.input, args.output, timeout=args.timeout)
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
