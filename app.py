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

quality = st.selectbox(
    "Output size (square, px)",
    [512, 768, 1024, 1500, 2000, 3000, 4000, 8000, 16000],
    index=6,  # default 4000 x 4000
    format_func=lambda x: f"{x} x {x} px",
)

gap_ratio = st.slider(
    "Gap between products (% of canvas width)",
    1,
    10,
    3,
    help="Smaller value = items closer together",
)

outer_padding_ratio = st.slider(
    "Outer padding (left & right, and top & bottom) (% of canvas size)",
    2,
    10,
    4,
    help="Controls margin around the products",
)

product_height_ratio = st.slider(
    "Product height (% of inner area)",
    40,
    90,
    65,
    help="How tall the products appear relative to the tile. Try ~60–70% for category tiles.",
)

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


def combine_images_smart(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    gap_ratio: int,
    outer_padding_ratio: int,
    product_height_ratio: int,
    bg_mode: str,
) -> Image.Image:
    """
    Place two images side-by-side on a square canvas:
    - Both images share the same final height (balanced look)
    - Centered horizontally & vertically inside the canvas
    - Background can be white or transparent
    """
    if bg_mode.startswith("White"):
        # White background (RGB)
        canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    else:
        # Transparent background (RGBA)
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))

    gap_px = int(canvas_size * (gap_ratio / 100.0))
    padding_px = int(canvas_size * (outer_padding_ratio / 100.0))

    # Available width & height inside padding
    avail_width = canvas_size - 2 * padding_px - gap_px
    avail_height = canvas_size - 2 * padding_px

    # Target product height as a fraction of available height
    target_height = int(avail_height * (product_height_ratio / 100.0))

    # Original sizes
    w1, h1 = img1.size
    w2, h2 = img2.size

    # First, scale each image to the same target height
    scale1 = target_height / float(h1)
    scale2 = target_height / float(h2)

    w1_t = w1 * scale1
    w2_t = w2 * scale2

    total_width_t = w1_t + gap_px + w2_t

    # If widths overflow, scale everything down proportionally
    if total_width_t > avail_width:
        width_scale = avail_width / float(total_width_t)
    else:
        width_scale = 1.0

    final_h = int(target_height * width_scale)
    final_w1 = int(w1 * scale1 * width_scale)
    final_w2 = int(w2 * scale2 * width_scale)

    img1_res = img1.resize((final_w1, final_h), Image.Resampling.LANCZOS)
    img2_res = img2.resize((final_w2, final_h), Image.Resampling.LANCZOS)

    # Horizontal positions: center the pair
    total_width_final = final_w1 + gap_px + final_w2
    start_x = (canvas_size - total_width_final) // 2
    x1 = start_x
    x2 = start_x + final_w1 + gap_px

    # Vertical positions: perfect global vertical centering
    y_center = (canvas_size - final_h) // 2
    y1 = y_center
    y2 = y_center

    def paste_with_alpha(bg, fg, x, y):
        if fg.mode == "RGBA" and bg.mode == "RGBA":
            bg.paste(fg, (x, y), fg)  # preserve transparency
        elif fg.mode == "RGBA" and bg.mode == "RGB":
            # composite over white for RGB canvas
            tmp = Image.new("RGB", fg.size, (255, 255, 255))
            tmp.paste(fg, mask=fg.split()[-1])
            bg.paste(tmp, (x, y))
        else:
            bg.paste(fg, (x, y))

    paste_with_alpha(canvas, img1_res, x1, y1)
    paste_with_alpha(canvas, img2_res, x2, y2)

    return canvas


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

            result = combine_images_smart(
                img1_proc,
                img2_proc,
                quality,
                gap_ratio,
                outer_padding_ratio,
                product_height_ratio,
                bg_mode,
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
