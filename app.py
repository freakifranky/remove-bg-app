import io
import requests
from typing import Optional

from PIL import Image
import streamlit as st

# --- Optional background removal ---

try:
    from rembg import remove
    HAS_REMBG = True
    REMBG_ERROR = ""
except Exception as e:  # pragma: no cover
    HAS_REMBG = False
    REMBG_ERROR = repr(e)


# --- Streamlit page setup ---

st.set_page_config(page_title="Image Combiner", layout="centered")
st.title("Image Combiner – Quickcommerce Ready")

st.markdown(
    "Upload **two SKU images** (file or URL), optionally remove background per image, "
    "and download a combined 1:1 PNG (white or transparent background)."
)

# --- Inputs: images + per-image background removal ---

col1, col2 = st.columns(2)

with col1:
    st.subheader("Image 1 (hero?)", anchor=False)
    img_file_1 = st.file_uploader(
        "Upload Image 1", type=["png", "jpg", "jpeg"], key="img1"
    )
    img_url_1 = st.text_input("Or paste Image 1 URL")
    if HAS_REMBG:
        remove_bg_1 = st.checkbox(
            "Remove background for Image 1", value=False, key="rm1"
        )
    else:
        remove_bg_1 = False

with col2:
    st.subheader("Image 2 (front?)", anchor=False)
    img_file_2 = st.file_uploader(
        "Upload Image 2", type=["png", "jpg", "jpeg"], key="img2"
    )
    img_url_2 = st.text_input("Or paste Image 2 URL")
    if HAS_REMBG:
        remove_bg_2 = st.checkbox(
            "Remove background for Image 2", value=False, key="rm2"
        )
    else:
        remove_bg_2 = False

if not HAS_REMBG:
    st.info(
        "Per-image background removal is disabled (rembg not available).\n\n"
        f"Import error was: `{REMBG_ERROR}`"
    )

st.markdown("---")

# --- Layout + global options ---

layout_mode = st.radio(
    "Layout",
    ["Side-by-side", "Overlay (hero + front)"],
    index=1,
    horizontal=True,
)

output_size = st.selectbox(
    "Output size (square, px)",
    [800, 1200, 2000, 3000, 4000],
    index=3,
    format_func=lambda x: f"{x} x {x} px",
)

background_mode = st.radio(
    "Background",
    ["Pure white (#FFFFFF)", "Transparent PNG"],
    index=0,
    horizontal=True,
)

st.markdown("### Global spacing")

outer_padding_ratio = st.slider(
    "Outer padding (left & right, and top & bottom) (% of canvas size)",
    0,
    30,
    10,
    help="White/transparent margin around everything.",
)

# Side-by-side only gap slider
if layout_mode == "Side-by-side":
    gap_ratio_side = st.slider(
        "Gap between products (% of canvas width) [side-by-side only]",
        0,
        20,
        5,
        help="Horizontal space between the two packs.",
    )

# Overlay-specific controls
st.markdown("### Overlay fine-tuning")

if layout_mode == "Overlay (hero + front)":
    overlay_distance_ratio = st.slider(
        "Distance between packs (%)",
        -500,
        500,
        40,
        help=(
            "Horizontal position of the **front** pack relative to center.\n"
            "-500 = far left, +500 = far right."
        ),
    )
    overlay_drop_ratio = st.slider(
        "Front pack drop (%)",
        0,
        500,
        80,
        help=(
            "How far to drop the front pack downward from the hero.\n"
            "Higher values push it closer to (or beyond) the bottom edge."
        ),
    )
    overlay_front_scale = st.slider(
        "Front pack size vs hero (%)",
        30,
        120,
        60,
        help="Scale of the front pack height relative to the hero height.",
    )
else:
    # Dummy values (not used)
    overlay_distance_ratio = 0
    overlay_drop_ratio = 0
    overlay_front_scale = 60


# --- Helpers ---

def load_image_from_file_or_url(
    file, url: str
) -> Optional[Image.Image]:
    """Priority: file upload > URL > None."""
    if file is not None:
        try:
            img = Image.open(file).convert("RGBA")
            return img
        except Exception as e:
            st.error(f"Failed to read uploaded file: {e}")
            return None

    if url:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            return img
        except Exception as e:
            st.error(f"Failed to load image from URL: {url}\n{e}")
            return None

    return None


def apply_rembg(img: Image.Image, do_remove: bool) -> Image.Image:
    """Optionally remove background using rembg."""
    if not (HAS_REMBG and do_remove):
        return img

    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        out = remove(data)
        return Image.open(io.BytesIO(out)).convert("RGBA")
    except Exception as e:  # pragma: no cover
        st.warning(f"Background removal failed: {e}")
        return img


def create_canvas(size: int, background: str) -> Image.Image:
    """Create RGBA canvas with white or transparent background."""
    if background == "Transparent PNG":
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    else:
        return Image.new("RGBA", (size, size), (255, 255, 255, 255))


def combine_side_by_side(
    img1: Image.Image,
    img2: Image.Image,
    canvas_size: int,
    padding_ratio: float,
    gap_ratio: float,
    background: str,
) -> Image.Image:
    """Side-by-side layout with smart scaling."""
    canvas = create_canvas(canvas_size, background)

    padding_px = int(canvas_size * (padding_ratio / 100.0))
    gap_px = int(canvas_size * (gap_ratio / 100.0))

    avail_width = canvas_size - 2 * padding_px - gap_px
    avail_height = canvas_size - 2 * padding_px

    w1, h1 = img1.size
    w2, h2 = img2.size

    scale_by_width = avail_width / float(w1 + w2)
    scale_by_height = min(avail_height / float(h1), avail_height / float(h2))
    scale = min(scale_by_width, scale_by_height)

    new_w1, new_h1 = int(w1 * scale), int(h1 * scale)
    new_w2, new_h2 = int(w2 * scale), int(h2 * scale)

    img1_resized = img1.resize((new_w1, new_h1), Image.Resampling.LANCZOS)
    img2_resized = img2.resize((new_w2, new_h2), Image.Resampling.LANCZOS)

    total_width = new_w1 + gap_px + new_w2
    start_x = (canvas_size - total_width) // 2

    x1 = start_x
    x2 = start_x + new_w1 + gap_px
    y1 = (canvas_size - new_h1) // 2
    y2 = (canvas_size - new_h2) // 2

    def paste_with_alpha(bg: Image.Image, fg: Image.Image, xy):
        if fg.mode == "RGBA":
            bg.paste(fg, xy, fg)
        else:
            bg.paste(fg, xy)

    paste_with_alpha(canvas, img1_resized, (x1, y1))
    paste_with_alpha(canvas, img2_resized, (x2, y2))

    return canvas


def combine_overlay(
    hero: Image.Image,
    front: Image.Image,
    canvas_size: int,
    padding_ratio: float,
    distance_ratio: float,
    drop_ratio: float,
    front_scale_pct: float,
    background: str,
) -> Image.Image:
    """Overlay layout: hero in back, front pack in front."""
    canvas = create_canvas(canvas_size, background)

    padding_px = int(canvas_size * (padding_ratio / 100.0))

    # --- Scale hero to fit inside padded square ---
    avail = canvas_size - 2 * padding_px
    w_h, h_h = hero.size
    hero_scale = min(avail / w_h, avail / h_h)
    hero_w = int(w_h * hero_scale)
    hero_h = int(h_h * hero_scale)
    hero_resized = hero.resize((hero_w, hero_h), Image.Resampling.LANCZOS)

    hero_x = (canvas_size - hero_w) // 2
    hero_y = (canvas_size - hero_h) // 2

    # --- Scale front relative to hero height ---
    w_f, h_f = front.size
    target_front_h = max(int(hero_h * (front_scale_pct / 100.0)), 1)
    front_scale = target_front_h / float(h_f)
    front_w = int(w_f * front_scale)
    front_h = target_front_h
    front_resized = front.resize((front_w, front_h), Image.Resampling.LANCZOS)

    # --- Position front pack ---
    hero_center_x = hero_x + hero_w // 2
    hero_bottom_y = hero_y + hero_h

    # Horizontal offset: ratio of canvas size (can be very large)
    dx = int(canvas_size * (distance_ratio / 100.0))
    front_center_x = hero_center_x + dx

    # Vertical drop: measured from hero bottom downward
    dy = int(canvas_size * (drop_ratio / 100.0))
    front_center_y = hero_bottom_y - front_h // 2 + dy

    front_x = int(front_center_x - front_w / 2)
    front_y = int(front_center_y - front_h / 2)

    def paste_with_alpha(bg: Image.Image, fg: Image.Image, xy):
        if fg.mode == "RGBA":
            bg.paste(fg, xy, fg)
        else:
            bg.paste(fg, xy)

    # Draw hero then front
    paste_with_alpha(canvas, hero_resized, (hero_x, hero_y))
    paste_with_alpha(canvas, front_resized, (front_x, front_y))

    return canvas


# --- Main action ---

if st.button("✨ Generate Combined Image", type="primary"):
    img1 = load_image_from_file_or_url(img_file_1, img_url_1)
    img2 = load_image_from_file_or_url(img_file_2, img_url_2)

    if img1 is None or img2 is None:
        st.error("Please provide **both** images (via upload or URL).")
    else:
        with st.spinner("Processing images..."):
            img1_proc = apply_rembg(img1, remove_bg_1)
            img2_proc = apply_rembg(img2, remove_bg_2)

            if layout_mode == "Side-by-side":
                result = combine_side_by_side(
                    img1_proc,
                    img2_proc,
                    output_size,
                    outer_padding_ratio,
                    gap_ratio_side,
                    background_mode,
                )
            else:
                # Interpret img1 as hero, img2 as front for overlay
                result = combine_overlay(
                    hero=img1_proc,
                    front=img2_proc,
                    canvas_size=output_size,
                    padding_ratio=outer_padding_ratio,
                    distance_ratio=overlay_distance_ratio,
                    drop_ratio=overlay_drop_ratio,
                    front_scale_pct=overlay_front_scale,
                    background=background_mode,
                )

        st.success("Done! Preview below 👇")
        st.image(result, caption="Combined SKU Image", use_column_width=True)

        # Always export PNG (supports transparency)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        buf.seek(0)

        st.download_button(
            label=f"⬇️ Download PNG ({output_size} x {output_size})",
            data=buf,
            file_name=f"combined_sku_{output_size}px.png",
            mime="image/png",
        )

st.markdown("---")
st.markdown("<p style='text-align:center; font-size: 12px;'>Vibe-coded by @frnkygabriel</p>", unsafe_allow_html=True)
