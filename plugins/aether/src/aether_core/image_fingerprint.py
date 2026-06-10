from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised indirectly when Pillow is unavailable
    from PIL import Image, ImageFilter, ImageStat
    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False

try:  # pragma: no cover - optional import
    import open_clip  # type: ignore
    _OPENCLIP_AVAILABLE = True
except Exception:  # pragma: no cover
    open_clip = None  # type: ignore[assignment]
    _OPENCLIP_AVAILABLE = False


DEFAULT_MAX_EDGE = 384
DEFAULT_SAMPLE_PIXELS = 32_768
DEFAULT_HISTOGRAM_BINS = 32


def is_pillow_available() -> bool:
    return _PIL_AVAILABLE


def is_openclip_available() -> bool:
    return _OPENCLIP_AVAILABLE


def _load_image(path):
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow is not installed; image fingerprinting is unavailable.")
    with Image.open(path) as handle:
        handle.load()
        return handle


def _downsample_rgb(image, max_edge: int = DEFAULT_MAX_EDGE):
    width, height = image.size
    if max(width, height) <= max_edge:
        return image
    scale = max_edge / float(max(width, height))
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(new_size, Image.BILINEAR)


def _hex_from_rgb(rgb):
    r, g, b = (max(0, min(255, int(channel))) for channel in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _color_distance(left, right):
    dr = left[0] - right[0]
    dg = left[1] - right[1]
    db = left[2] - right[2]
    return math.sqrt(dr * dr + dg * dg + db * db)


def extract_palette(image, *, max_colors: int = 6, accent_count: int = 3):
    """Extract a deterministic hex palette from ``image``.

    Returns a dict ready to merge into a ``color_palette`` profile.
    """

    if not _PIL_AVAILABLE:
        return {}
    rgb = image.convert("RGB")
    quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors() or []
    counts.sort(key=lambda item: item[0], reverse=True)
    total = sum(count for count, _ in counts) or 1

    dominant_entries = []
    for count, index in counts:
        start = index * 3
        rgb_tuple = (palette[start], palette[start + 1], palette[start + 2])
        ratio = count / total
        if ratio < 0.005 and len(dominant_entries) >= 3:
            continue
        dominant_entries.append((_hex_from_rgb(rgb_tuple), round(ratio, 4), rgb_tuple))
        if len(dominant_entries) >= max_colors:
            break

    dominant_hex = [entry[0] for entry in dominant_entries]
    dominant_colors = [f"{entry[0]} ({entry[1] * 100:.1f}%)" for entry in dominant_entries]
    accent_entries = []
    if accent_count > 0 and dominant_entries:
        stats = ImageStat.Stat(rgb)
        mean_r, mean_g, mean_b = stats.mean[:3]
        for count, index in counts:
            start = index * 3
            rgb_tuple = (palette[start], palette[start + 1], palette[start + 2])
            if _color_distance(rgb_tuple, (mean_r, mean_g, mean_b)) < 64:
                continue
            accent_entries.append((_hex_from_rgb(rgb_tuple), rgb_tuple))
            if len(accent_entries) >= accent_count:
                break
    accent_hex = [entry[0] for entry in accent_entries]

    sat_samples = []
    for _, _, rgb_tuple in dominant_entries:
        max_c = max(rgb_tuple)
        min_c = min(rgb_tuple)
        sat_samples.append((max_c - min_c) / max_c if max_c else 0.0)
    saturation = round(sum(sat_samples) / len(sat_samples), 4) if sat_samples else 0.0

    warm_score = sum(1 for _, _, (r, g, b) in dominant_entries if r > b)
    cool_score = sum(1 for _, _, (r, g, b) in dominant_entries if b > r)
    neutral_score = len(dominant_entries) - warm_score - cool_score
    if warm_score > cool_score and warm_score > neutral_score:
        temperature = "warm"
    elif cool_score > warm_score and cool_score > neutral_score:
        temperature = "cool"
    else:
        temperature = "neutral"

    return {
        "dominant_colors": dominant_colors,
        "accent_colors": [_hex_from_rgb(rgb) for rgb in [entry[1] for entry in accent_entries]],
        "dominant_hex": dominant_hex,
        "accent_hex": accent_hex,
        "saturation": saturation,
        "temperature": temperature,
    }


def extract_geometry(image):
    """Compute coarse composition statistics from luminance."""

    if not _PIL_AVAILABLE:
        return {}
    gray = image.convert("L")
    width, height = gray.size
    aspect = round(width / height, 4) if height else 1.0
    cell_w = max(1, width // 8)
    cell_h = max(1, height // 8)
    downscale = (cell_w * 8, cell_h * 8)
    grid = gray.resize(downscale, Image.BILINEAR)
    pixels = grid.load()
    best_score = -1.0
    subject_cell = (4, 4)
    cell_box = None
    for cy in range(8):
        for cx in range(8):
            mid_count = 0
            for y in range(cy * cell_h, (cy + 1) * cell_h):
                for x in range(cx * cell_w, (cx + 1) * cell_w):
                    value = pixels[x, y]
                    if 40 <= value <= 220:
                        mid_count += 1
            cell_pixels = cell_w * cell_h
            ratio = mid_count / cell_pixels
            if ratio > best_score:
                best_score = ratio
                subject_cell = (cx, cy)
                cell_box = (cx * cell_w, cy * cell_h, cell_w, cell_h)
    background_ratio = round(1.0 - best_score, 4)
    if cell_box is not None:
        x, y, w, h = cell_box
        bbox = [
            round(x / width, 4),
            round(y / height, 4),
            round((x + w) / width, 4),
            round((y + h) / height, 4),
        ]
    else:
        bbox = [0.0, 0.0, 1.0, 1.0]
    return {
        "width": width,
        "height": height,
        "aspect_ratio": aspect,
        "subject_bbox": bbox,
        "subject_cell": [subject_cell[0], subject_cell[1]],
        "background_ratio": background_ratio,
    }


def _iter_grayscale_values(image):
    """Yield grayscale pixel values, preferring Pillow 10+ API."""
    gray = image.convert("L")
    width, height = gray.size
    if hasattr(gray, "get_flattened_data"):
        data = gray.get_flattened_data()
        if width * height <= len(data):
            return list(data)
        step = max(1, int(math.sqrt((width * height) / len(data))))
        return list(data)[::step]
    return list(gray.getdata())


def _grayscale_pixels(image, max_pixels: int = DEFAULT_SAMPLE_PIXELS):
    gray = image.convert("L")
    width, height = gray.size
    if width * height <= max_pixels:
        return _iter_grayscale_values(image)
    step = max(1, int(math.sqrt((width * height) / max_pixels)))
    sampled = []
    pixels = gray.load()
    for y in range(0, height, step):
        for x in range(0, width, step):
            sampled.append(pixels[x, y])
    return sampled


def extract_stats(image):
    """Compute line / texture / lighting statistics for an image."""

    if not _PIL_AVAILABLE:
        return {}
    pixels = _grayscale_pixels(image)
    if not pixels:
        return {}
    n = len(pixels)
    mean = sum(pixels) / n
    variance = sum((value - mean) ** 2 for value in pixels) / n
    std = math.sqrt(variance)
    sorted_pixels = sorted(pixels)
    p5 = sorted_pixels[max(0, int(n * 0.05))]
    p95 = sorted_pixels[min(n - 1, int(n * 0.95))]
    histogram = [0] * DEFAULT_HISTOGRAM_BINS
    for value in pixels:
        bin_index = min(DEFAULT_HISTOGRAM_BINS - 1, value * DEFAULT_HISTOGRAM_BINS // 256)
        histogram[bin_index] += 1
    low_energy = sum(histogram[0:DEFAULT_HISTOGRAM_BINS // 3])
    mid_energy = sum(histogram[DEFAULT_HISTOGRAM_BINS // 3:2 * DEFAULT_HISTOGRAM_BINS // 3])
    high_energy = sum(histogram[2 * DEFAULT_HISTOGRAM_BINS // 3:])
    total_energy = low_energy + mid_energy + high_energy or 1

    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    if hasattr(edges, "get_flattened_data"):
        edge_pixels = list(edges.get_flattened_data())
    else:
        edge_pixels = list(edges.getdata())
    edge_intensity = sum(1 for value in edge_pixels if value > 32) / len(edge_pixels)

    stats_vector = [
        round(mean / 255.0, 4),
        round(std / 128.0, 4),
        round((p5 / 255.0), 4),
        round((p95 / 255.0), 4),
        round(low_energy / total_energy, 4),
        round(mid_energy / total_energy, 4),
        round(high_energy / total_energy, 4),
        round(edge_intensity, 4),
    ]

    return {
        "stats_vector": stats_vector,
        "exposure": round(mean / 255.0, 4),
        "dynamic_range": round((p95 - p5) / 255.0, 4),
        "edge_density": round(edge_intensity, 4),
        "low_frequency_ratio": round(low_energy / total_energy, 4),
        "mid_frequency_ratio": round(mid_energy / total_energy, 4),
        "high_frequency_ratio": round(high_energy / total_energy, 4),
    }


_CLIP_MODEL = None
_CLIP_PREPROCESS = None
_CLIP_TOKENIZER = None
_CLIP_DEVICE = None
_CLIP_LOAD_FAILED = False


def _ensure_clip() -> bool:
    global _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_TOKENIZER, _CLIP_DEVICE, _CLIP_LOAD_FAILED
    if not _OPENCLIP_AVAILABLE:
        return False
    if _CLIP_MODEL is not None:
        return True
    if _CLIP_LOAD_FAILED:
        return False
    try:
        import torch  # type: ignore
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()
        _CLIP_MODEL = model
        _CLIP_PREPROCESS = preprocess
        _CLIP_TOKENIZER = tokenizer
        _CLIP_DEVICE = device
        return True
    except Exception:
        _CLIP_LOAD_FAILED = True
        return False


def extract_clip(image):
    if not _PIL_AVAILABLE:
        return None
    if not _ensure_clip():
        return None
    import torch  # type: ignore

    tensor = _CLIP_PREPROCESS(image).unsqueeze(0).to(_CLIP_DEVICE)
    with torch.no_grad():
        features = _CLIP_MODEL.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)
    return [round(float(value), 6) for value in features[0].tolist()]


def compute_fingerprint(
    path,
    *,
    include_clip: bool = True,
    max_edge: int = DEFAULT_MAX_EDGE,
):
    """Compute the full image fingerprint for an asset.

    Best-effort: any Pillow or image-load failure returns ``{}`` so the
    caller can persist a ``null`` fingerprint without crashing ingest.
    """

    if not _PIL_AVAILABLE:
        return {}
    try:
        image = _load_image(path)
    except Exception:
        return {}
    if image.mode not in {"RGB", "RGBA", "L"}:
        try:
            image = image.convert("RGB")
        except Exception:
            return {}
    small = _downsample_rgb(image, max_edge=max_edge)
    fingerprint = {
        "schema_version": 1,
        "palette": extract_palette(small),
        "geometry": extract_geometry(small),
        "stats": extract_stats(small),
    }
    fingerprint["clip"] = extract_clip(small) if include_clip else None
    return fingerprint


def fingerprint_summary(fingerprint):
    """Render a fingerprint as a compact canonical text snippet."""

    if not fingerprint:
        return ""
    parts = []
    palette = fingerprint.get("palette") or {}
    if palette.get("dominant_hex"):
        parts.append("palette hex: " + ", ".join(palette["dominant_hex"]))
    if palette.get("accent_hex"):
        parts.append("accent hex: " + ", ".join(palette["accent_hex"]))
    if palette.get("temperature"):
        parts.append(f"temperature: {palette['temperature']}")
    if "saturation" in palette:
        parts.append(f"saturation: {palette['saturation']:.2f}")
    geometry = fingerprint.get("geometry") or {}
    if "aspect_ratio" in geometry:
        parts.append(f"aspect: {geometry['aspect_ratio']}")
    if geometry.get("subject_bbox"):
        parts.append(
            "subject bbox: " + "/".join(str(round(v, 2)) for v in geometry["subject_bbox"])
        )
    if "background_ratio" in geometry:
        parts.append(f"background ratio: {geometry['background_ratio']:.2f}")
    stats = fingerprint.get("stats") or {}
    for key in ("exposure", "dynamic_range", "edge_density"):
        if key in stats:
            parts.append(f"{key}: {stats[key]:.2f}")
    if stats.get("low_frequency_ratio") is not None:
        parts.append(
            "frequency: "
            f"low={stats.get('low_frequency_ratio', 0):.2f} "
            f"mid={stats.get('mid_frequency_ratio', 0):.2f} "
            f"high={stats.get('high_frequency_ratio', 0):.2f}"
        )
    return "; ".join(parts)


def palette_to_profile(fingerprint):
    palette = (fingerprint or {}).get("palette") or {}
    profile = {}
    if palette.get("dominant_colors"):
        profile["dominant_colors"] = palette["dominant_colors"]
    if palette.get("accent_colors"):
        profile["accent_colors"] = palette["accent_colors"]
    if "saturation" in palette:
        profile["saturation"] = palette["saturation"]
    if palette.get("temperature"):
        profile["temperature"] = palette["temperature"]
    if palette.get("dominant_hex"):
        profile["dominant_hex"] = palette["dominant_hex"]
    if palette.get("accent_hex"):
        profile["accent_hex"] = palette["accent_hex"]
    return profile


def cosine_similarity_vector(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def visual_signal_score(left, right):
    """Return a 0-1 score combining palette, stats, and CLIP cosine.

    Missing components are renormalized so a partial fingerprint does not
    silently score zero.
    """

    if not left or not right:
        return 0.0
    left_palette = (left.get("palette") or {}).get("dominant_hex") or []
    right_palette = (right.get("palette") or {}).get("dominant_hex") or []
    palette_score = 0.0
    if left_palette and right_palette:
        def _to_vec(hexes):
            vec = []
            for value in hexes:
                r = int(value[1:3], 16) / 255.0
                g = int(value[3:5], 16) / 255.0
                b = int(value[5:7], 16) / 255.0
                vec.extend([r, g, b])
            return vec
        palette_score = cosine_similarity_vector(_to_vec(left_palette), _to_vec(right_palette))
    stats_score = cosine_similarity_vector(
        (left.get("stats") or {}).get("stats_vector"),
        (right.get("stats") or {}).get("stats_vector"),
    )
    clip_score = cosine_similarity_vector(left.get("clip"), right.get("clip"))
    weighted = 0.5 * palette_score + 0.3 * stats_score + 0.2 * clip_score
    return round(max(0.0, min(1.0, weighted)), 4)


def fingerprint_path_for(asset_path):
    p = Path(asset_path)
    return str(p.with_suffix(p.suffix + ".fingerprint.json"))


def load_cached_fingerprint(asset_path):
    sidecar = Path(fingerprint_path_for(asset_path))
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cached_fingerprint(asset_path, fingerprint):
    sidecar = Path(fingerprint_path_for(asset_path))
    sidecar.write_text(json.dumps(fingerprint), encoding="utf-8")
    return str(sidecar)
