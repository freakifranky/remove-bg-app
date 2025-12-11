import io
import requests
from typing import Tuple

from PIL import Image
import streamlit as st

# ----------------- CONFIG & DEFAULTS -----------------

# Overlay defaults (ratios)
DEFAULT_GAP_RATIO = 0.05                 # 5% side-by-side gap
DEFAULT_PADDING_RATIO = 0.05             # 5% padding
DEFAULT_OVERLAY_OFFSET_RATIO = 0.25      # horizontal separation for overlay
DEFAULT_HERO_SCALE_FACTOR = 0.80         # front pack size vs hero
DEFAULT_SECONDARY_VERT_OFFSET_RATIO = 0.40  # front pack drop vs padding

# Try to import rembg (optional background removal)
try:
    from rembg import remove
    HAS_REMBG = True
    REMBG_ERROR = ""
except Exception as e:
    HAS_REMBG = False
    REMBG_ERROR = repr(e)


# ----------------- PAGE SETUP -----------------

st.set_page_config(page_title="Image Combiner", layout="centered")
st.title("Image Combiner – Quickcommerce Ready")

st.markdown(
    "Upload **two product images** (file or URL), choose layout, "
    "optionally remove backgrounds, and download a 1:1 PNG ready for quickcommerce."
)

# ----------------- INPUTS -----------------

col1, col2 = st.columns(2)

with col1:
    st.subheader("Image 1")
    img_file_1 = st.file_uploader("Upload Image 1", type=["png", "jpg", "jpeg"], key="img1")
    img_url_1 = st.text_input("Or paste Image 1 URL")

with col2:
    st.subheader("Image 2")
    img_file_2 = st.file_uploader("Upload Image 2", type=["png", "jpg", "jpeg"], key="img2")
    img_url_2 = st.text_input("Or paste Image 2 URL")

st.markdown("---")

# Background removal switches (per image)
if HAS_REMBG:
    st.markdown("**Background removal (per image)**")
    col_rb1, col_rb2 = st.columns(2)
    with col_rb1:
        remove_bg_1 = st.checkbox("Remove background for Image 1", value=False)
    with col_rb2:
        remove_bg_2 = st.checkbox("Remove background for Image 2", value=False)
else:
    remove_bg_1 = remove_bg_2 = False
    st.info(
        "Background removal disabled (rembg not available).\n\n"
        f"_Import error: {REMBG_ERROR}_"
    )

# Output size
quality = st.selectbox(
    "Output size (square, px)",
    [1000, 1500, 2000, 3000, 4000],
    index=2,
    format_func=lambda x: f"{x} × {x} px",
)

# Background mode
bg_mode = st.radio(
    "Background",
    ["White (#FFFFFF)", "Transparent PNG"],
    horizontal=True,
)

# Layout mode
layout_mode = st.selectbox(
    "Layout mode",
    ["Side-by-side", "Overlay (hero + secondary)"],
)

# Side-by-side tuning
gap_ratio = (
    st.slider(
        "Gap between products (% of canvas width) [side-by-side only]",
        1,
        15,
        int(DEFAULT_GAP_RATIO * 100),
    )
    / 100.0
)

outer_padding_ratio = (
    st.slider(
        "Outer padding (left & right, and top & bottom) (% of canvas size)",
        2,
        10,
        int(DEFAULT_PADDING_RATIO * 100),
        help="Controls white / transparent margin around the products.",
    )
    / 100.0
)

# Overlay fine-tuning (only when overlay mode is selected)
overlay_offset_ratio = DEFAULT_OVERLAY_OFFSET_RATIO
hero_scale_factor = DEFAULT_HERO_SCALE_FACTOR
secondary_vert_offset_ratio = DEFAULT_SECONDARY_VERT_OFFSET_RATIO

if layout_mode.startswith("Overlay"):
    st.markdown("**Overlay fine-tuning**")

    col_o1, col_o2 = st.columns(2)

    with col_o1:
        overlay_offset_ratio = (
            st.slider(
                "Distance between packs (%)",
                5,
                40,
                int(DEFAULT_OVERLAY_OFFSET_RATIO * 100),
                help="Higher = packs move further left/right from each other.",
            )
            / 100.0
        )

        hero_scale_factor = (
            st.slider(
                "Front pack size vs hero (%)",
                40,
                110,
                int(DEFAULT_HERO_SCALE_FACTOR * 100),
                help="100% = same height as hero, lower = smaller front pack.",
            )
            / 100.0
        )

    with col_o2:
        secondary_vert_offset_ratio = (
            st.slider(
                "Front pack drop (%)",
                0,
                150,
                int(DEFAULT_SECONDARY_VERT_OFFSET_RATIO * 100),
                help="Higher = front pack sits lower on the canvas.",
            )
            / 100.0
        )

st.markdown("---")


# ----------------- HELPERS -----------------

def load_image_from_file_or_url(file, url) -> Image.Image | None:
    """Priority: file upload > URL > None. Convert to RGBA."""
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
    if HAS_REMBG and do_remove:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        out = remove(data)
        return Image.open(io.BytesIO(out)).convert("RGBA")
    return img


def make_canvas(size: int, bg_mode: str) -> Tuple[Image.Image, str]:
    """Create canvas and return (image, mode)."""
    if bg_mode == "Transparent PNG":
        return Image.new("RGBA", (size, size), (0, 0, 0, 0)), "RGBA"
    else:
        return Image.new("RGB", (size, size), (255, 255, 255)), "RGB"


def paste_with_alpha(bg: Image.Image, fg: Image.Image, x: int, y: int) -> None:
    """Paste fg onto bg using alpha channel if available."""
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
    bg_mode: str,
) -> Image.Image:
    canvas, _ = make_canvas(canvas_size, bg_mode)

    gap_px = int(canvas_size * gap_ratio)
    padding_px = int(canvas_size * padding_ratio)

    avail_width = canvas_size - 2 * padding_px - gap_px
    avail_height = canvas_size - 2 * padding_px

    w1, h1 = img1.size
    w2, h2 = img2.size

    scale_by_width = avail_width / float(w1 + w2)
    scale_by_height = min(avail_height / float(h1), avail_height / float(h2))
    scale = min(scale_by_width, scale_by_height)

    new_w1, new_h1 = int(w1 * scale), int(h1 * scale)
    new_w2, new_h2 = int(w2 * scale), int(h2 * scale)

    img1_res = img1.resize((new_w1, new_h1), Image.Resampling.LANCZOS)
    img2_res = img2.resize((new_w2, new_h2), Image.Resampling.LANCZOS)

    total_width = new_w1 + gap_px + new_w2
    start_x = (canvas_size - total_width) // 2

    x1 = start_x
    x2 = start_x + new_w1 + gap_px

    # Vertically center both
    y1 = (canvas_size - new_h1) // 2
    y2 = (canvas_size - new_h2) // 2

    paste_with_alpha(canvas, img1_res, x1, y1)
    paste_with_alpha(canvas, img2_res, x2, y2)

    return canvas


def combine_overlay_hero(
    hero_img: Image.Image,
    front_img: Image.Image,
    canvas_size: int,
    padding_ratio: float,
    overlay_offset_ratio: float,
    secondary_vert_offset_ratio: float,
    hero_scale_factor: float,
    bg_mode: str,
) -> Image.Image:
    canvas, _ = make_canvas(canvas_size, bg_mode)

    padding_px = int(canvas_size * padding_ratio)

    # --- Scale hero to fit canvas with padding ---
    h_w, h_h = hero_img.size
    max_hero_w = canvas_size - 2 * padding_px
    max_hero_h = canvas_size - 2 * padding_px

    hero_scale = min(max_hero_w / float(h_w), max_hero_h / float(h_h))
    hero_w, hero_h = int(h_w * hero_scale), int(h_h * hero_scale)

    hero_res = hero_img.resize((hero_w, hero_h), Image.Resampling.LANCZOS)

    hero_bottom = canvas_size - padding_px
    hero_y = hero_bottom - hero_h
    hero_x = (canvas_size - hero_w) // 2

    paste_with_alpha(canvas, hero_res, hero_x, hero_y)

    # --- Scale & position front pack ---
    f_w, f_h = front_img.size
    target_front_h = int(hero_h * hero_scale_factor)
    front_scale = target_front_h / float(f_h)
    front_w, front_h = int(f_w * front_scale), int(f_h * front_scale)

    front_res = front_img.resize((front_w, front_h), Image.Resampling.LANCZOS)

    # Horizontal: relative to hero center
    hero_center_x = hero_x + hero_w // 2
    offset_px = int((hero_w / 2.0) * overlay_offset_ratio)

    # Put front to the right of hero center by default
    front_x = hero_center_x - front_w // 2 + offset_px
    # Clamp inside canvas with small margin
    front_x = max(padding_px, min(canvas_size - padding_px - front_w, front_x))

    # Vertical: baseline = hero_bottom, then drop further
    baseline = hero_bottom
    extra_down = int(padding_px * secondary_vert_offset_ratio * 2.0)
    front_bottom = min(canvas_size - padding_px // 10, baseline + extra_down)
    front_y = front_bottom - front_h

    paste_with_alpha(canvas, front_res, front_x, front_y)

    return canvas


# ----------------- MAIN ACTION -----------------

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
                combined = combine_side_by_side(
                    img1_proc,
                    img2_proc,
                    quality,
                    gap_ratio,
                    outer_padding_ratio,
                    bg_mode,
                )
            else:
                # Treat Image 1 as hero (back), Image 2 as front by default
                combined = combine_overlay_hero(
                    hero_img=img1_proc,
                    front_img=img2_proc,
                    canvas_size=quality,
                    padding_ratio=outer_padding_ratio,
                    overlay_offset_ratio=overlay_offset_ratio,
                    secondary_vert_offset_ratio=secondary_vert_offset_ratio,
                    hero_scale_factor=hero_scale_factor,
                    bg_mode=bg_mode,
                )

        st.success("Done! Preview below 👇")
        st.image(combined, caption="Combined Image", use_column_width=True)

        buf = io.BytesIO()
        # Always save as PNG so transparency is preserved if used
        combined.save(buf, format="PNG")
        buf.seek(0)

        st.download_button(
            label=f"⬇️ Download PNG ({quality} × {quality})",
            data=buf,
            file_name=f"combined_image_{quality}px.png",
            mime="image/png",
        )

# ----------------- FOOTER -----------------

st.markdown(
    "<div style='margin-top:3rem; text-align:center; font-size:0.8rem; "
    "opacity:0.6;'>Vibe-coded by @frnkygabriel</div>",
    unsafe_allow_html=True,
)
