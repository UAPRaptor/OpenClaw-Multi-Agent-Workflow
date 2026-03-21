"""
OpenClaw Image Generation MCP Server

Provides `generate_image` and `list_models` tools to Claude Code agents
via the Model Context Protocol (stdio transport).

Supports backends:
  - Google Gemini Imagen (default, free tier)
  - OpenAI DALL-E 3 (requires API key)
  - Local SDXL Turbo (requires torch + diffusers)

Usage (standalone):
    python -m openclaw.mcp.image_gen

Configuration:
    API keys are resolved in order:
      1. Environment variables (GEMINI_API_KEY, OPENAI_API_KEY)
      2. Mission Control vault (fetched via http://127.0.0.1:8765/api/vault/get/<name>)

    IMAGE_GEN_BACKEND  — "gemini" (default), "openai", or "local"
    IMAGE_OUTPUT_DIR   — where to save images (default: ./assets)
"""

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# ── Vault-backed key resolution ──────────────────────────────────────────────

def _get_key(env_var: str, vault_name: str | None = None) -> str:
    """Resolve an API key: env var first, then Mission Control vault."""
    val = os.environ.get(env_var, "")
    if val:
        return val
    # Try fetching from the vault (MC must be running + vault unlocked)
    vault_name = vault_name or env_var
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:8765/api/vault/get/{vault_name}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return data.get("value", "")
    except Exception:
        return ""


# ── MCP Protocol helpers ─────────────────────────────────────────────────────

def _send(msg: dict) -> None:
    """Send a JSON-RPC message to stdout."""
    raw = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(raw)}\r\n\r\n{raw}")
    sys.stdout.flush()


def _read() -> dict | None:
    """Read a JSON-RPC message from stdin."""
    # Read headers
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line == "\r\n" or line == "\n":
            break
        if ":" in line:
            key, val = line.split(":", 1)
            headers[key.strip().lower()] = val.strip()

    content_length = int(headers.get("content-length", 0))
    if content_length == 0:
        return None

    body = sys.stdin.read(content_length)
    return json.loads(body)


# ── Image generation backends ────────────────────────────────────────────────

def _generate_gemini(prompt: str, output_path: Path, aspect_ratio: str = "1:1") -> dict:
    """Generate image using Google Gemini's native image generation."""
    api_key = _get_key("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set. Add it as an env var or store it in the Mission Control vault."}

    # Use Gemini's native image generation
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{"text": f"Generate an image: {prompt}"}]
        }],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())

        # Extract image from response
        candidates = data.get("candidates", [])
        if not candidates:
            return {"error": "No response from Gemini", "raw": data}

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                img_data = part["inlineData"]
                mime = img_data.get("mimeType", "image/png")
                ext = ".png" if "png" in mime else ".jpg" if "jpeg" in mime else ".webp"
                img_bytes = base64.b64decode(img_data["data"])

                # Ensure output dir exists
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if output_path.suffix == "":
                    output_path = output_path.with_suffix(ext)

                output_path.write_bytes(img_bytes)
                return {
                    "ok": True,
                    "path": str(output_path),
                    "size_bytes": len(img_bytes),
                    "mime_type": mime,
                    "backend": "gemini",
                }

        # No image in response — might have text explanation
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        return {"error": "No image generated", "text": " ".join(text_parts)}

    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"error": f"Gemini API error {e.code}: {body[:500]}"}
    except Exception as e:
        return {"error": str(e)}


def _generate_imagen(prompt: str, output_path: Path, aspect_ratio: str = "1:1") -> dict:
    """Generate image using Google Imagen 4 via the predict API."""
    api_key = _get_key("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set. Add it as an env var or store it in the Mission Control vault."}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={api_key}"

    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect_ratio,
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())

        predictions = data.get("predictions", [])
        if not predictions:
            return {"error": "No predictions returned", "raw": data}

        img_b64 = predictions[0].get("bytesBase64Encoded", "")
        mime = predictions[0].get("mimeType", "image/png")
        if not img_b64:
            return {"error": "Empty image data"}

        ext = ".png" if "png" in mime else ".jpg"
        img_bytes = base64.b64decode(img_b64)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix == "":
            output_path = output_path.with_suffix(ext)

        output_path.write_bytes(img_bytes)
        return {
            "ok": True,
            "path": str(output_path),
            "size_bytes": len(img_bytes),
            "mime_type": mime,
            "backend": "imagen-4",
        }

    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"error": f"Imagen API error {e.code}: {body[:500]}"}
    except Exception as e:
        return {"error": str(e)}


def _generate_local(
    prompt: str,
    output_path: Path,
    model_id: str = "sdxl-turbo",
    width: int = 512,
    height: int = 512,
    style: str | None = None,
    output_format: str = "png",
) -> dict:
    """Generate image using a local Stable Diffusion model (requires diffusers + torch).

    Args:
        width/height: Output dimensions. SDXL Turbo works best with multiples of 64,
                      min 256, max 1024. Common presets: 512x512 (icon), 1024x1024 (logo),
                      1024x576 (banner 16:9), 576x1024 (portrait), 768x512 (card).
        style: Optional style prefix prepended to the prompt (e.g. "pixel art",
               "flat vector", "watercolor", "minimalist line art").
        output_format: "png" (default, lossless) or "jpg" (smaller file).
    """
    models_dir = Path.home() / ".openclaw" / "models" / model_id
    if not models_dir.exists() or not any(models_dir.iterdir()):
        return {"error": f"Model '{model_id}' not installed. Download it via Mission Control."}

    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError:
        return {"error": "Local generation requires 'torch' and 'diffusers'. Install with: pip install torch diffusers transformers accelerate"}

    # Clamp dimensions to safe range, round to nearest 64
    width = max(256, min(1024, width))
    height = max(256, min(1024, height))
    width = (width // 64) * 64
    height = (height // 64) * 64

    # Apply style prefix
    full_prompt = f"{style} style, {prompt}" if style else prompt

    try:
        # Select device
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

        dtype = torch.float16 if device != "cpu" else torch.float32

        pipe = AutoPipelineForText2Image.from_pretrained(
            str(models_dir),
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
        )
        pipe = pipe.to(device)

        # SDXL Turbo uses 1-4 steps, no guidance
        num_steps = 4 if "turbo" in model_id else 20
        guidance = 0.0 if "turbo" in model_id else 7.5

        image = pipe(
            prompt=full_prompt,
            num_inference_steps=num_steps,
            guidance_scale=guidance,
            width=width,
            height=height,
        ).images[0]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        ext = ".jpg" if output_format.lower() in ("jpg", "jpeg") else ".png"
        if output_path.suffix == "":
            output_path = output_path.with_suffix(ext)

        if ext == ".jpg":
            image.save(str(output_path), format="JPEG", quality=90)
        else:
            image.save(str(output_path), format="PNG")

        size_bytes = output_path.stat().st_size

        return {
            "ok": True,
            "path": str(output_path),
            "size_bytes": size_bytes,
            "width": width,
            "height": height,
            "style": style,
            "backend": f"local-{model_id}",
            "device": device,
        }

    except Exception as e:
        return {"error": f"Local generation failed: {str(e)}"}


def _generate_openai(prompt: str, output_path: Path, size: str = "1024x1024") -> dict:
    """Generate image using OpenAI DALL-E 3."""
    api_key = _get_key("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set. Add it as an env var or store it in the Mission Control vault."}

    url = "https://api.openai.com/v1/images/generations"
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "response_format": "b64_json",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())

        images = data.get("data", [])
        if not images:
            return {"error": "No images returned"}

        img_bytes = base64.b64decode(images[0]["b64_json"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix == "":
            output_path = output_path.with_suffix(".png")

        output_path.write_bytes(img_bytes)
        return {
            "ok": True,
            "path": str(output_path),
            "size_bytes": len(img_bytes),
            "revised_prompt": images[0].get("revised_prompt", ""),
            "backend": "dall-e-3",
        }

    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return {"error": f"OpenAI API error {e.code}: {body[:500]}"}
    except Exception as e:
        return {"error": str(e)}


# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "generate_image",
        "description": (
            "Generate an image from a text prompt using AI. "
            "Saves the image to disk and returns the file path. "
            "Use detailed prompts for best results: include style, colors, and subject. "
            "For local backend, specify exact width/height (multiples of 64, 256-1024). "
            "Common sizes: 512x512 (icon/avatar), 1024x1024 (logo), 1024x576 (banner), 768x512 (card)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed text description of the image to generate",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (without extension). Saved to the assets/ directory.",
                },
                "backend": {
                    "type": "string",
                    "enum": ["gemini", "imagen", "openai", "local"],
                    "description": "Which image generation backend to use. Default: local (SDXL Turbo). Cloud options: gemini, imagen, openai.",
                },
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels (local backend). Must be 256-1024, multiple of 64. Default: 512.",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels (local backend). Must be 256-1024, multiple of 64. Default: 512.",
                },
                "style": {
                    "type": "string",
                    "description": "Art style to apply. Examples: 'flat vector', 'pixel art', 'watercolor', 'minimalist line art', 'photorealistic', '3d render', 'comic book'. Prepended to the prompt.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["png", "jpg"],
                    "description": "Output format. png (lossless, default) or jpg (smaller file). Default: png.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio for cloud backends (e.g. '1:1', '16:9', '4:3'). Default: '1:1'. Ignored by local backend (use width/height instead).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "list_image_backends",
        "description": "List available image generation backends and their status.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ── MCP Server main loop ────────────────────────────────────────────────────

def handle_request(msg: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "openclaw-image-gen",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        return None  # No response needed

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if tool_name == "generate_image":
            prompt = args.get("prompt", "")
            filename = args.get("filename", f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            backend = args.get("backend", os.environ.get("IMAGE_GEN_BACKEND", "local"))
            aspect_ratio = args.get("aspect_ratio", "1:1")
            width = args.get("width", 512)
            height = args.get("height", 512)
            style = args.get("style")
            output_format = args.get("output_format", "png")

            output_dir = Path(os.environ.get("IMAGE_OUTPUT_DIR", "./assets"))
            output_path = output_dir / filename

            if backend == "openai":
                result = _generate_openai(prompt, output_path)
            elif backend == "imagen":
                result = _generate_imagen(prompt, output_path, aspect_ratio)
            elif backend == "local":
                result = _generate_local(
                    prompt, output_path,
                    width=width, height=height,
                    style=style, output_format=output_format,
                )
            else:
                result = _generate_gemini(prompt, output_path, aspect_ratio)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                },
            }

        if tool_name == "list_image_backends":
            backends = []
            if _get_key("GEMINI_API_KEY"):
                backends.append({"name": "gemini", "status": "configured", "models": ["gemini-2.0-flash-exp"]})
                backends.append({"name": "imagen", "status": "configured", "models": ["imagen-4.0-generate-001"]})
            else:
                backends.append({"name": "gemini", "status": "not configured (set GEMINI_API_KEY or add to vault)"})
                backends.append({"name": "imagen", "status": "not configured (set GEMINI_API_KEY or add to vault)"})
            if _get_key("OPENAI_API_KEY"):
                backends.append({"name": "openai", "status": "configured", "models": ["dall-e-3"]})
            else:
                backends.append({"name": "openai", "status": "not configured (set OPENAI_API_KEY or add to vault)"})

            # Check local models
            models_dir = Path.home() / ".openclaw" / "models"
            local_models = []
            for mid in ["sdxl-turbo", "sd-1.5", "sd-3.5-medium"]:
                mpath = models_dir / mid
                if mpath.exists() and any(mpath.iterdir()):
                    local_models.append(mid)
            if local_models:
                backends.append({"name": "local", "status": "configured", "models": local_models})
            else:
                backends.append({"name": "local", "status": "no models installed (use Mission Control to download)"})

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(backends, indent=2)}],
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    # Unknown method
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }
    return None


def main():
    """Run the MCP server over stdio."""
    while True:
        msg = _read()
        if msg is None:
            break
        response = handle_request(msg)
        if response is not None:
            _send(response)


if __name__ == "__main__":
    main()
