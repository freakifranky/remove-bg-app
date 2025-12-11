import io
import requests
from PIL import Image
import streamlit as st

# ---------- REMBG IMPORT (OPTIONAL) ----------

try:
    from rembg import remove
    HAS_REMBG = True
    REMBG_ERROR = ""
except Exception as e:
    HAS_REMBG = False
    REMBG_ERROR = repr(e)

# ---------- PAGE CONFIG ----------

st.set_page_config(page_title="SKU Image Combiner", layout="centered")
st.title("SKU Image Combiner – Quickcommerce Ready")

st.markdown(
    "Upload **two SKU images** (file or URL), optionally remove background, "
    "and download a combined 1:1 image (PNG, white or transparent background)."
)

# ---------- INPUTS ----------

col1, col2 = st.columns(2)

with col1:
    img_file_1 = st.file_uploader(
        "Upload Image 1", type=["png", "jpg", "jpeg"], key="img1"
    )
    img_url_1 = st.text_input("Or paste Image 1 URL")

with col2:
    img_file_2 = st.file_uploader(
        "Upload Image 2", type=["png", "jpg", "jpeg"], key="img2"
    )
    img_url_2 = st.text_input("Or paste Image 2 URL")

st.markdown("---")

if HAS_REMBG:
    remove_bg = st.checkbox(
        "Remove background using AI (can be imperfect on noisy images)",
        value=False,
    )
else:
    remove_bg = False
    st.info(
        "Background removal disabled (rembg not available).\n"
        f"Import error: {REMBG_ERROR}\n"
        "On your own machine, install with: `python3 -m pip install \"rembg[cpu]\"`."
    )

bg_mode = st.radio(
    "Background",
    ["White (recommended for category tiles)", "Transparent PNG"],
    index=0,
)

layout_mode = st.radio(
    "Layout",
    ["Side by side", "Overlay (stacked)"],
    index=0,
)

quality = st.selectbox(
    "Output size (square, px)",
    [512, 768, 1024, 1500, 2000, 3000, 4000, 8000, 16000],
    index=6,  # default 4000 x 4000
    format_func=lambda x: f"{x} x {x} px",
)

gap_ratio = st.slider(
    "Gap between products (% of canvas width) [side-by-side only]",
    1,
    15,
    5,
    help="Smaller value = items closer together (only used in side-by-side layout).",
)

outer_padding_ratio = st.slider(
    "Outer padding (left & right, and top & bottom) (% of canvas size)",
    2,
    12,
    5,
    help="Controls margin around the products",
)

# For overlay, we use a fixed relative offset
OVERLAY_OFFSET_RATIO = 0.16  # ~16% of inner width


# ---------- HELPERS ----------

def load_image_from_file_or_url(file, url):
    """Load image either from uploaded file or URL. File has priority."""
    if file is not None:
        return Image.open(file).convert("RGBA")

    if url:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGBA")
        except Exception as e:
            st.error(f"Failed to load image from URL: {url}\n{e}")
            return None

    return None


def maybe_remove_bg(img: Image.Image) -> Image.Image:
    """Run rembg background removal if available and enabled."""
    if HAS_REMBG and remove_bg:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()          # bytes
        out = remove(data)             # bytes with alpha
        return Image.open(io.BytesIO(out)).convert("RGBA")
    return img


def paste_with_alpha(bg: Image.Image, fg: Image.Image, x: int, y: int):
    """Safely paste RGBA over RGB/RGBA canvas."""
    if fg.mode == "RGBA" and bg.mode == "RGBA":
        bg.paste(fg, (x, y), fg)  # preserve transparency
    elif fg.mode == "RGBA" and bg.mode == "RGB":
        # composite over white for RGB canvas
        tmp = Image.new("RGB", fg.size, (255, 255, 255))
        tmp.paste(fg, mask=fg.split()[-1])
        bg.paste(tmp, (x, y))
    else:
        bg.paste(fg, (x, y))


def combine_side_by_side(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    gap_ratio: int,
    outer_padding_ratio: int,
    bg_mode: str,
) -> Image.Image:
    """Maximally scale & center two images side by side."""
    if bg_mode.startswith("White"):
        canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    else:
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))

    gap_px = int(canvas_size * (gap_ratio / 100.0))
    padding_px = int(canvas_size * (outer_padding_ratio / 100.0))

    avail_width = canvas_size - 2 * padding_px - gap_px
    avail_height = canvas_size - 2 * padding_px

    w1, h1 = img1.size
    w2, h2 = img2.size

    # Maximal uniform scale that fits both heights and combined width
    s_height = min(avail_height / float(h1), avail_height / float(h2))
    s_width = (avail_width) / float(w1 + w2) if (w1 + w2) > 0 else s_height
    s = min(s_height, s_width)

    new_w1, new_h1 = int(w1 * s), int(h1 * s)
    new_w2, new_h2 = int(w2 * s), int(h2 * s)

    img1_res = img1.resize((new_w1, new_h1), Image.Resampling.LANCZOS)
    img2_res = img2.resize((new_w2, new_h2), Image.Resampling.LANCZOS)

    total_width = new_w1 + gap_px + new_w2
    # Horizontal centering
    x1 = (canvas_size - total_width) // 2
    x2 = x1 + new_w1 + gap_px

    # Vertically: treat the pair as one box of height = max(h1,h2), center that box
    final_h = max(new_h1, new_h2)
    top_y = (canvas_size - final_h) // 2
    bottom_y = top_y + final_h

    y1 = bottom_y - new_h1
    y2 = bottom_y - new_h2

    paste_with_alpha(canvas, img1_res, x1, y1)
    paste_with_alpha(canvas, img2_res, x2, y2)

    return canvas


def combine_overlay(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    outer_padding_ratio: int,
    bg_mode: str,
) -> Image.Image:
    """Maximally scale & center two images with slight overlap (img2 in front)."""
    if bg_mode.startswith("White"):
        canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    else:
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))

    padding_px = int(canvas_size * (outer_padding_ratio / 100.0))
    inner_width = canvas_size - 2 * padding_px
    inner_height = canvas_size - 2 * padding_px

    w1, h1 = img1.size
    w2, h2 = img2.size

    # We'll offset horizontally by a fraction of the inner width
    offset_px = int(inner_width * OVERLAY_OFFSET_RATIO)

    # Max scale so that:
    # - tallest image fits in height
    # - widest image + offset still fits in width
    max_h = max(h1, h2)
    max_w = max(w1, w2)

    s_height = inner_height / float(max_h)
    s_width = (inner_width - offset_px) / float(max_w) if max_w > 0 else s_height
    s = min(s_height, s_width)

    new_w1, new_h1 = int(w1 * s), int(h1 * s)
    new_w2, new_h2 = int(w2 * s), int(h2 * s)

    img1_res = img1.resize((new_w1, new_h1), Image.Resampling.LANCZOS)
    img2_res = img2.resize((new_w2, new_h2), Image.Resampling.LANCZOS)

    # Center point of canvas
    cx = canvas_size // 2
    cy = canvas_size // 2

    # Positions: img1 slightly left/back, img2 slightly right/front
    x1 = cx - new_w1 // 2 - offset_px // 2
    x2 = cx - new_w2 // 2 + offset_px // 2

    y1 = cy - new_h1 // 2
    y2 = cy - new_h2 // 2

    # Draw back then front
    paste_with_alpha(canvas, img1_res, x1, y1)
    paste_with_alpha(canvas, img2_res, x2, y2)

    return canvas


def combine_images(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    gap_ratio: int,
    outer_padding_ratio: int,
    bg_mode: str,
    layout_mode: str,
) -> Image.Image:
    """Dispatch to appropriate layout logic."""
    if layout_mode.startswith("Side"):
        return combine_side_by_side(
            img1, img2, canvas_size, gap_ratio, outer_padding_ratio, bg_mode
        )
    else:
        return combine_overlay(
            img1, img2, canvas_size, outer_padding_ratio, bg_mode
        )


# ---------- MAIN ACTION ----------

st.markdown("---")

if st.button("✨ Generate Combined Image", type="primary"):
    img1 = load_image_from_file_or_url(img_file_1, img_url_1)
    img2 = load_image_from_file_or_url(img_file_2, img_url_2)

    if img1 is None or img2 is None:
        st.error("Please provide both images (via upload or URL).")
    else:
        with st.spinner("Processing images..."):
            img1_proc = maybe_remove_bg(img1)
            img2_proc = maybe_remove_bg(img2)

            result = combine_images(
                img1_proc,
                img2_proc,
                quality,
                gap_ratio,
                outer_padding_ratio,
                bg_mode,
                layout_mode,
            )

        st.success("Done! Preview below 👇")
        st.image(result, caption="Combined SKU Image", use_column_width=True)

        buf = io.BytesIO()
        # Always PNG (supports transparency if used)
        result.save(buf, format="PNG")
        buf.seek(0)

        st.download_button(
            label=f"⬇️ Download PNG ({quality} x {quality})",
            data=buf,
            file_name=f"combined_sku_{quality}px.png",
            mime="image/png",
        )
