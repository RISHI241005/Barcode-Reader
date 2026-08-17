"""Utility to generate comprehensive sample barcode and QR code images for testing."""

from pathlib import Path
import io
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance
import barcode
from barcode.writer import ImageWriter
import qrcode


def generate_sample_images(output_dir: Path) -> dict:
    """Generate sample barcode and QR code images including rotations, low-quality, and multi-codes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_files = {}

    # 1. Standard EAN-13
    try:
        ean_cls = barcode.get_barcode_class("ean13")
        ean = ean_cls("890123456789", writer=ImageWriter())
        ean_path = output_dir / "ean13_sample.png"
        ean.save(str(ean_path.with_suffix("")))
        generated_files["ean13"] = ean_path
    except Exception as e:
        print(f"Error generating EAN-13 sample: {e}")

    # 2. Standard Code 128
    try:
        c128_cls = barcode.get_barcode_class("code128")
        c128 = c128_cls("PRODUCT-10234", writer=ImageWriter())
        c128_path = output_dir / "code128_sample.png"
        c128.save(str(c128_path.with_suffix("")))
        generated_files["code128"] = c128_path
    except Exception as e:
        print(f"Error generating Code 128 sample: {e}")

    # 3. Standard QR Code
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data("https://example.com")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_path = output_dir / "qrcode_sample.png"
        qr_img.save(str(qr_path))
        generated_files["qrcode"] = qr_path
    except Exception as e:
        print(f"Error generating QR code sample: {e}")

    # 4. Standard UPC-A
    try:
        upca_cls = barcode.get_barcode_class("upca")
        upca = upca_cls("01234567890", writer=ImageWriter())
        upca_path = output_dir / "upca_sample.png"
        upca.save(str(upca_path.with_suffix("")))
        generated_files["upca"] = upca_path
    except Exception as e:
        print(f"Error generating UPC-A sample: {e}")

    # 5. Standard Code 39
    try:
        c39_cls = barcode.get_barcode_class("code39")
        c39 = c39_cls("ITEM99", writer=ImageWriter(), add_checksum=False)
        c39_path = output_dir / "code39_sample.png"
        c39.save(str(c39_path.with_suffix("")))
        generated_files["code39"] = c39_path
    except Exception as e:
        print(f"Error generating Code 39 sample: {e}")

    # 6. Standard ITF
    try:
        itf_cls = barcode.get_barcode_class("itf")
        itf = itf_cls("123456789012", writer=ImageWriter())
        itf_path = output_dir / "itf_sample.png"
        itf.save(str(itf_path.with_suffix("")))
        generated_files["itf"] = itf_path
    except Exception as e:
        print(f"Error generating ITF sample: {e}")

    # 7. Multiple Barcodes in One Image
    try:
        composite = Image.new("RGB", (1000, 800), color=(255, 255, 255))
        
        ean_cls = barcode.get_barcode_class("ean13")
        ean = ean_cls("890123456789", writer=ImageWriter())
        ean_buf = io.BytesIO()
        ean.write(ean_buf)
        ean_buf.seek(0)
        ean_img = Image.open(ean_buf).convert("RGB")
        composite.paste(ean_img, (50, 50))

        c128_cls = barcode.get_barcode_class("code128")
        c128 = c128_cls("PRODUCT-123", writer=ImageWriter())
        c128_buf = io.BytesIO()
        c128.write(c128_buf)
        c128_buf.seek(0)
        c128_img = Image.open(c128_buf).convert("RGB")
        composite.paste(c128_img, (50, 420))

        qr = qrcode.QRCode(box_size=8, border=3)
        qr.add_data("https://example.com")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        composite.paste(qr_img, (600, 200))

        multi_path = output_dir / "multiple_barcodes_sample.png"
        composite.save(str(multi_path))
        generated_files["multiple"] = multi_path
    except Exception as e:
        print(f"Error generating multiple barcodes sample: {e}")

    # 8. Rotated Barcodes (90°, 180°, 270°)
    try:
        # Rotated 90° EAN-13
        ean_cls = barcode.get_barcode_class("ean13")
        ean = ean_cls("890123456789", writer=ImageWriter())
        ean_buf = io.BytesIO()
        ean.write(ean_buf)
        ean_buf.seek(0)
        ean_img = Image.open(ean_buf).convert("RGB")
        rot90_img = ean_img.rotate(90, expand=True)
        rot90_path = output_dir / "ean13_rotated90.png"
        rot90_img.save(str(rot90_path))
        generated_files["ean13_rotated90"] = rot90_path

        # Rotated 180° Code 128
        c128_cls = barcode.get_barcode_class("code128")
        c128 = c128_cls("ROTATED-180", writer=ImageWriter())
        c128_buf = io.BytesIO()
        c128.write(c128_buf)
        c128_buf.seek(0)
        c128_img = Image.open(c128_buf).convert("RGB")
        rot180_img = c128_img.rotate(180, expand=True)
        rot180_path = output_dir / "code128_rotated180.png"
        rot180_img.save(str(rot180_path))
        generated_files["code128_rotated180"] = rot180_path

        # Rotated 270° QR Code
        qr = qrcode.QRCode(box_size=8, border=4)
        qr.add_data("https://antigravity.dev/part2")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        rot270_img = qr_img.rotate(270, expand=True)
        rot270_path = output_dir / "qrcode_rotated270.png"
        rot270_img.save(str(rot270_path))
        generated_files["qrcode_rotated270"] = rot270_path
    except Exception as e:
        print(f"Error generating rotated samples: {e}")

    # 9. Low Contrast / Difficult Barcode Sample
    try:
        ean_cls = barcode.get_barcode_class("ean13")
        ean = ean_cls("890123456789", writer=ImageWriter())
        ean_buf = io.BytesIO()
        ean.write(ean_buf)
        ean_buf.seek(0)
        base_img = Image.open(ean_buf).convert("RGB")
        
        # Reduce contrast and add slight haze
        enhancer = ImageEnhance.Contrast(base_img)
        low_contrast = enhancer.enhance(0.25)
        bright_enhancer = ImageEnhance.Brightness(low_contrast)
        hazy = bright_enhancer.enhance(1.15)
        
        low_contrast_path = output_dir / "low_contrast_sample.png"
        hazy.save(str(low_contrast_path))
        generated_files["low_contrast"] = low_contrast_path
    except Exception as e:
        print(f"Error generating low contrast sample: {e}")

    # 10. Small Barcode inside large container
    try:
        canvas = Image.new("RGB", (1000, 800), color=(255, 255, 255))
        c128_cls = barcode.get_barcode_class("code128")
        writer = ImageWriter()
        writer.set_options({
            "module_width": 0.22,
            "module_height": 8.0,
            "font_size": 6,
            "text_distance": 2.0,
            "quiet_zone": 3.0,
        })
        c128 = c128_cls("SMALL-77", writer=writer)
        c128_buf = io.BytesIO()
        c128.write(c128_buf)
        c128_buf.seek(0)
        small_code = Image.open(c128_buf).convert("RGB")
        
        canvas.paste(small_code, (350, 300))
        small_path = output_dir / "small_barcode_sample.png"
        canvas.save(str(small_path))
        generated_files["small_barcode"] = small_path
    except Exception as e:
        print(f"Error generating small barcode sample: {e}")

    # 11. No Barcode Sample
    try:
        no_barcode_img = Image.new("RGB", (600, 400), color=(240, 245, 250))
        draw = ImageDraw.Draw(no_barcode_img)
        draw.rectangle([50, 50, 550, 350], fill=(220, 230, 242), outline=(180, 195, 210), width=2)
        draw.ellipse([200, 100, 400, 300], fill=(140, 180, 220), outline=(100, 140, 180), width=2)
        draw.text((150, 310), "Scenic Graphic (No Barcodes)", fill=(80, 100, 120))
        no_barcode_path = output_dir / "no_barcode_sample.png"
        no_barcode_img.save(str(no_barcode_path))
        generated_files["no_barcode"] = no_barcode_path
    except Exception as e:
        print(f"Error generating no-barcode sample: {e}")

    return generated_files


if __name__ == "__main__":
    sample_dir = Path(__file__).resolve().parent.parent / "sample_images"
    results = generate_sample_images(sample_dir)
    print(f"Generated {len(results)} sample images in {sample_dir}")
