"""Safe Matugen dry-run command construction and palette parsing."""

import json
import re


_COLOR_KEYS = (
    "primary", "secondary", "tertiary", "surface", "background",
    "on_surface", "outline", "error",
)
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")


def build_preview_command(image_path, configured_args, executable="matugen"):
    """Preserve configured Matugen options but force JSON + no-side-effect mode."""
    args = list(configured_args)
    normalized = []
    index = 0
    while index < len(args):
        item = args[index]
        if item == "--json":
            index += 2 if index + 1 < len(args) else 1
            continue
        if item.startswith("--json=") or item in {"--dry-run", "--quiet"}:
            index += 1
            continue
        normalized.append(item)
        index += 1
    return [
        executable, "image", image_path, *normalized,
        "--json", "hex", "--dry-run", "--quiet",
    ]


def parse_preview_output(output):
    """Parse Matugen's --json hex output, tolerating its trailing 'ok' marker."""
    if not isinstance(output, str):
        raise ValueError("Matugen preview output must be text")
    content = output.strip()
    if not content.endswith("}"):
        content = re.sub(r"\s*ok\s*$", "", content).strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"Matugen returned invalid JSON: {error}") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("colors"), dict):
        raise ValueError("Matugen output does not contain a color palette")

    result = {}
    for mode in ("dark", "light"):
        entries = []
        for key in _COLOR_KEYS:
            variants = payload["colors"].get(key)
            if not isinstance(variants, dict):
                continue
            value = variants.get(mode)
            if isinstance(value, dict):
                value = value.get("color")
            if isinstance(value, str) and _HEX_COLOR.fullmatch(value):
                entries.append((key, value))
        if entries:
            result[mode] = entries
    if not result:
        raise ValueError("Matugen output contains no usable preview colors")
    return result
