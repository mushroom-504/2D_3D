import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from config_loader import get_section


MAX_INPUT_BYTES = 10 * 1024 * 1024
VIEW_ORDER = ("front", "back", "left", "right", "top", "bottom")


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


def _encode_image(path, view):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f"CraftsMan {view} image not found: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_INPUT_BYTES:
        raise RuntimeError(
            f"CraftsMan {view} image size must be between 1 byte and 10 MB: "
            f"{size:,} bytes"
        )
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _multiview_was_used(result, supplied_views):
    if len(supplied_views) <= 1:
        return True
    if result.get("multiview_used") is True:
        return True
    accepted = result.get("accepted_views") or result.get("used_views") or []
    if isinstance(accepted, dict):
        accepted = [view for view, used in accepted.items() if used]
    return set(supplied_views).issubset(set(accepted))


def generate(image_paths, output_path, prompt="", timeout=300):
    image_paths = {
        view: Path(path)
        for view, path in (image_paths or {}).items()
        if view in VIEW_ORDER and path
    }
    input_path = image_paths.get("front")
    output_path = Path(output_path)
    if not input_path:
        raise RuntimeError("CraftsMan requires a front image.")

    config, api_key = _api_config()
    url = str(config.get("generate_url", "")).strip()
    if not url:
        raise RuntimeError("craftsman_api.generate_url is missing in config.json.")
    encoded_views = {
        view: _encode_image(image_paths[view], view)
        for view in VIEW_ORDER
        if view in image_paths
    }
    supplied_views = list(encoded_views)
    payload = {
        "image_base64": encoded_views["front"],
        "steps": int(config.get("steps", 50)),
        "seed": int(config.get("seed", 0)),
        "guidance_scale": float(config.get("guidance_scale", 5.0)),
        "octree_depth": int(config.get("octree_depth", 7)),
        "remove_background": bool(config.get("remove_background", True)),
        "foreground_ratio": float(config.get("foreground_ratio", 1.0)),
    }
    if len(encoded_views) > 1:
        payload["images_base64"] = encoded_views
        payload["view_order"] = supplied_views
    if str(prompt or "").strip():
        payload["prompt"] = str(prompt).strip()

    result = _request_json(url, api_key, payload=payload, timeout=timeout)
    if not result.get("success"):
        raise RuntimeError(f"CraftsMan API generation failed: {result}")
    multiview_confirmed = _multiview_was_used(result, supplied_views)
    multiview_warning = ""
    if len(supplied_views) > 1 and not multiview_confirmed:
        multiview_warning = (
            "远程服务返回了模型，但没有通过 multiview_used 或 "
            "accepted_views/used_views 确认实际使用了全部参考视图。"
        )
        if bool(config.get("require_multiview_confirmation", False)):
            raise RuntimeError(
                multiview_warning
                + " 当前已启用严格多视图确认，请升级服务端响应或在 "
                "config.json 中关闭 require_multiview_confirmation。"
            )
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
        "generation_mode": "multi_view" if len(supplied_views) > 1 else "single_view",
        "supplied_views": supplied_views,
        "accepted_views": result.get("accepted_views") or result.get("used_views"),
        "multiview_used": (
            result.get("multiview_used")
            if len(supplied_views) > 1
            else True
        ),
        "multiview_confirmed": multiview_confirmed,
        "multiview_warning": multiview_warning,
        "prompt_used": bool(str(prompt or "").strip()),
    }
    output_path.with_suffix(".api.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def main():
    parser = argparse.ArgumentParser(description="CraftsMan remote API bridge")
    parser.add_argument("--input", help="Deprecated alias for --front")
    parser.add_argument("--front")
    for view in VIEW_ORDER[1:]:
        parser.add_argument(f"--{view}")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    front = args.front or args.input
    if not front:
        parser.error("--front is required")
    image_paths = {
        view: getattr(args, view)
        for view in VIEW_ORDER
        if getattr(args, view, None)
    }
    image_paths["front"] = front
    metadata = generate(
        image_paths,
        args.output,
        prompt=args.prompt,
        timeout=args.timeout,
    )
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
