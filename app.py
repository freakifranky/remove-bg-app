import io
import requests
from typing import Optional

from PIL import Image
import streamlit as st

# ---------- Optional background remover ----------

try:
    from rembg import remove
    HAS_REMBG = True
    REMBG_ERROR = ""
except Exception as e:
    HAS_REMBG = False
    REMBG_ERROR = repr(e)

# ---------- Streamlit page setup ----------

st.set_page_config(page_title="Image Combiner – Quickcommerce Ready",
                   layout="centered")

st.title("Image Combiner – Quickcommerce Ready")

st.markdown(
    "Upload **two SKU images** (file or URL), "
    "optionally remove background per image, choose layout, "
    "and download a combined 1:1 image ready for quickcommerce."
)

# ---------- INPUTS ----------

col1, col2 = st.columns(2)

with col1:
    st.subheader("Image 1 (Hero)")
    img_file_1 = st.file_uploader(
        "Upload hero image", type=["png", "jpg", "jpeg"], key="img1"
    )
    img_url_1 = st.text_input("Or paste hero image URL")
    remove_bg_1 = False
    if HAS_REMBG:
        remove_bg_1 = st.checkbox("Remove background for hero", value=False)
    else:
        st.caption("Background removal unavailable (rembg not installed).")

with col2:
    st.subheader("Image 2 (Front / Secondary)")
    img_file_2 = st.file_uploader(
        "Upload front image", type=["png", "jpg", "jpeg"], key="img2"
    )
    img_url_2 = st.text_input("Or paste front image URL")
    remove_bg_2 = False
    if HAS_REMBG:
        remove_bg_2 = st.checkbox("Remove background for front pack", value=False)
    else:
        st.caption("Background removal unavailable (rembg not installed).")

st.markdown("---")

layout_mode = st.radio(
    "Layout",
    ["Side-by-side", "Overlay (hero + front)"],
    horizontal=True,
)

# Background mode
bg_mode = st.radio(
    "Background",
    ["White", "Transparent PNG"],
    horizontal=True,
)
if bg_mode == "White":
    bg_rgba = (255, 255, 255, 255)
else:
    bg_rgba = (0, 0, 0, 0)  # fully transparent

# Common controls
quality = st.selectbox(
    "Output size (square, px)",
    [2000, 3000, 4000, 8000, 12000, 16000],
    index=2,
    format_func=lambda x: f"{x} x {x} px",
)

gap_ratio = None
overlay_distance_ratio = None
overlay_drop_ratio = None
overlay_scale_ratio = None

# Side-by-side spacing + padding
st.markdown("### Global spacing")
if layout_mode == "Side-by-side":
    gap_ratio = st.slider(
        "Gap between products (% of canvas width) [side-by-side only]",
        0, 15, 4,
        help="Controls the white gap between the two packs."
    )

outer_padding_ratio = st.slider(
    "Outer padding (left & right, and top & bottom) (% of canvas size)",
    0, 25, 5,   # <-- increased max here
    help="Controls the margin around the packs. 0 = almost full-bleed."
)

# Overlay fine-tuning
if layout_mode == "Overlay (hero + front)":
    st.markdown("### Overlay fine-tuning")
    overlay_distance_ratio = st.slider(
    "Distance between packs (%)",
    -500, 500, 40,   # <-- updated range
    help=(
        "Horizontal position of the **front** pack relative to center.\n"
        "-500 = far left, +500 = far right."
    ),
)

overlay_drop_ratio = st.slider(
    "Front pack drop (%)",
    0, 500, 80,      # <-- updated range
    help=(
        "How far to drop the front pack downward from center.\n"
        "Higher = pushed further down (towards the bottom)."
    ),
)
    )
    overlay_scale_ratio = st.slider(
        "Front pack size vs hero (%)",
        30, 120, 60,
        help="Relative size of front pack vs hero (100% = same visual height).",
    )

st.markdown("---")


# ---------- HELPERS ----------

def load_image_from_file_or_url(file, url) -> Optional[Image.Image]:
    """Priority: file upload > URL > None."""
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


def maybe_remove_bg(img: Image.Image, do_remove: bool) -> Image.Image:
    """Remove background for a single image if requested & rembg available."""
    if HAS_REMBG and do_remove:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        out = remove(data)
        return Image.open(io.BytesIO(out)).convert("RGBA")
    return img


def paste_with_alpha(bg: Image.Image, fg: Image.Image, x: int, y: int):
    if fg.mode == "RGBA":
        bg.paste(fg, (x, y), fg)
    else:
        bg.paste(fg, (x, y))


def combine_side_by_side(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    gap_ratio: float,
    padding_ratio: float,
    bg_color: tuple,
) -> Image.Image:
    """Side-by-side layout, centered in both directions."""
    canvas = Image.new("RGBA", (canvas_size, canvas_size), bg_color)

    gap_px = int(canvas_size * (gap_ratio / 100.0))
    padding_px = int(canvas_size * (padding_ratio / 100.0))

    avail_width = canvas_size - 2 * padding_px - gap_px
    avail_height = canvas_size - 2 * padding_px

    w1, h1 = img1.size
    w2, h2 = img2.size

    scale_by_width = avail_width / float(w1 + w2)
    scale_by_height = min(avail_height / float(h1),
                          avail_height / float(h2))

    scale = min(scale_by_width, scale_by_height)

    new_w1, new_h1 = int(w1 * scale), int(h1 * scale)
    new_w2, new_h2 = int(w2 * scale), int(h2 * scale)

    img1_res = img1.resize((new_w1, new_h1), Image.Resampling.LANCZOS)
    img2_res = img2.resize((new_w2, new_h2), Image.Resampling.LANCZOS)

    total_width = new_w1 + gap_px + new_w2
    start_x = (canvas_size - total_width) // 2

    x1 = start_x
    x2 = start_x + new_w1 + gap_px

    y1 = (canvas_size - new_h1) // 2
    y2 = (canvas_size - new_h2) // 2

    paste_with_alpha(canvas, img1_res, x1, y1)
    paste_with_alpha(canvas, img2_res, x2, y2)

    return canvas


def combine_overlay(
    img_hero: Image.Image,
    img_front: Image.Image,
    canvas_size: int,
    padding_ratio: float,
    distance_ratio: float,
    drop_ratio: float,
    scale_ratio: float,
    bg_color: tuple,
) -> Image.Image:
    """
    Overlay layout:
    - Hero pack centered and scaled to fit within padding.
    - Front pack scaled vs hero height and positioned using sliders:
        * distance_ratio: horizontal shift from center (-300..300).
        * drop_ratio: how far to drop from vertical center (0..300).
    """
    canvas = Image.new("RGBA", (canvas_size, canvas_size), bg_color)

    padding_px = int(canvas_size * (padding_ratio / 100.0))

    # --- Scale hero to fit nicely in padded area ---
    avail_width = canvas_size - 2 * padding_px
    avail_height = canvas_size - 2 * padding_px

    hw, hh = img_hero.size
    hero_scale = min(avail_width / float(hw), avail_height / float(hh))

    hero_w, hero_h = int(hw * hero_scale), int(hh * hero_scale)
    hero_res = img_hero.resize((hero_w, hero_h), Image.Resampling.LANCZOS)

    hero_x = (canvas_size - hero_w) // 2
    hero_y = (canvas_size - hero_h) // 2

    paste_with_alpha(canvas, hero_res, hero_x, hero_y)

    # --- Scale front relative to hero height ---
    fw, fh = img_front.size
    target_front_h = int(hero_h * (scale_ratio / 100.0))
    front_scale = target_front_h / float(fh)
    front_w, front_h = int(fw * front_scale), target_front_h

    front_res = img_front.resize((front_w, front_h), Image.Resampling.LANCZOS)

    # --- Horizontal position: distance_ratio moves center left/right ---
    center_x = canvas_size // 2

    max_shift = (canvas_size - front_w) // 2
    offset_px = int((distance_ratio / 100.0) * max_shift * 2)  # extra reach
    front_center_x = center_x + offset_px

    # Clamp so it never gets cropped
    front_center_x = max(front_w // 2, min(canvas_size - front_w // 2, front_center_x))
    front_x = front_center_x - front_w // 2

    # --- Vertical position: drop from center downwards ---
    center_y = canvas_size // 2
    max_drop = canvas_size - padding_px - front_h - center_y
    max_drop = max(0, max_drop)
    drop_px = int((drop_ratio / 100.0) * max_drop * 2)  # extra reach

    front_y = center_y + drop_px
    front_y = min(canvas_size - padding_px - front_h, front_y)

    paste_with_alpha(canvas, front_res, front_x, front_y)

    return canvas


# ---------- MAIN ACTION ----------

if st.button("✨ Generate Combined Image", type="primary"):
    img1 = load_image_from_file_or_url(img_file_1, img_url_1)
    img2 = load_image_from_file_or_url(img_file_2, img_url_2)

    if img1 is None or img2 is None:
        st.error("Please provide both images (via upload or URL).")
    else:
        with st.spinner("Processing images..."):
            img1_proc = maybe_remove_bg(img1, remove_bg_1)
            img2_proc = maybe_remove_bg(img2, remove_bg_2)

            if layout_mode == "Side-by-side":
                result = combine_side_by_side(
                    img1_proc,
                    img2_proc,
                    quality,
                    gap_ratio,
                    outer_padding_ratio,
                    bg_rgba,
                )
            else:
                result = combine_overlay(
                    img1_proc,
                    img2_proc,
                    quality,
                    outer_padding_ratio,
                    overlay_distance_ratio,
                    overlay_drop_ratio,
                    overlay_scale_ratio,
                    bg_rgba,
                )

        st.success("Done! Preview below 👇")
        st.image(result, caption="Combined SKU Image", use_column_width=True)

        # ---------- Prepare for download ----------
        if bg_mode == "White":
            # Flatten RGBA onto white for clean white background
            out_img = Image.new("RGB", result.size, (255, 255, 255))
            out_img.paste(result, mask=result.split()[-1])  # use alpha channel
        else:
            # Keep transparency
            out_img = result

        buf = io.BytesIO()
        out_img.save(buf, format="PNG")
        buf.seek(0)

        st.download_button(
            label=f"⬇️ Download PNG ({quality} x {quality})",
            data=buf,
            file_name=f"combined_sku_{quality}px.png",
            mime="image/png",
        )

st.markdown("---")
st.markdown(
    "<p style='text-align:center; font-size: 12px; opacity: 0.7;'>"
    "Vibe-coded by @frnkygabriel"
    "</p>",
    unsafe_allow_html=True,
)
