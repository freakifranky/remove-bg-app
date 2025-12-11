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
    "and download a combined 1:1 image on pure white."
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
        "Remove background (works even if background is white)",
        value=False,
    )
else:
    remove_bg = False
    st.info(
        "Background removal disabled (rembg not available).\n"
        f"Import error: {REMBG_ERROR}\n"
        "On your own machine, install with: `python3 -m pip install \"rembg[cpu]\"`."
    )

quality = st.selectbox(
    "Output size (square, px)",
    [2000, 3000, 4000, 8000, 16000],
    index=2,
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
    help="Controls white margin around the products",
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
        data = buf.getvalue()  # bytes
        out = remove(data)     # bytes with alpha
        return Image.open(io.BytesIO(out)).convert("RGBA")
    return img


def combine_images_smart(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    gap_ratio: int,
    outer_padding_ratio: int,
) -> Image.Image:
    """
    Scale both images with a single factor so that:
    - Combined width + gap fits horizontally
    - Heights fit within top/bottom padding
    Result: minimal wasted white space.
    """
    # Create white square canvas
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))

    gap_px = int(canvas_size * (gap_ratio / 100.0))
    padding_px = int(canvas_size * (outer_padding_ratio / 100.0))

    # Available width & height inside padding
    avail_width = canvas_size - 2 * padding_px - gap_px
    avail_height = canvas_size - 2 * padding_px

    # Original sizes
    w1, h1 = img1.size
    w2, h2 = img2.size

    # Scale factor limited by width AND height
    scale_by_width = avail_width / float(w1 + w2)
    scale_by_height = min(avail_height / float(h1), avail_height / float(h2))
    scale = min(scale_by_width, scale_by_height)

    new_w1, new_h1 = int(w1 * scale), int(h1 * scale)
    new_w2, new_h2 = int(w2 * scale), int(h2 * scale)

    img1_res = img1.resize((new_w1, new_h1), Image.Resampling.LANCZOS)
    img2_res = img2.resize((new_w2, new_h2), Image.Resampling.LANCZOS)

    # Center both horizontally with the specified gap
    total_width = new_w1 + gap_px + new_w2
    start_x = (canvas_size - total_width) // 2
    x1 = start_x
    x2 = start_x + new_w1 + gap_px

    # Vertically center each image
    y1 = (canvas_size - new_h1) // 2
    y2 = (canvas_size - new_h2) // 2

    def paste_with_alpha(bg, fg, x, y):
        if fg.mode == "RGBA":
            bg.paste(fg, (x, y), fg)  # keep transparency
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
            )

        st.success("Done! Preview below 👇")
        st.image(result, caption="Combined SKU Image", use_column_width=True)

        buf = io.BytesIO()
        result.save(buf, format="PNG")
        buf.seek(0)

        st.download_button(
            label=f"⬇️ Download PNG ({quality} x {quality})",
            data=buf,
            file_name=f"combined_sku_{quality}px.png",
            mime="image/png",
        )
