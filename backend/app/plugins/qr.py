"""QR Code generation plugin using qrcode and PIL."""
import io
import qrcode
from app.core.config import settings


def generate_machine_qr_bytes(qr_token: str) -> bytes:
    """Generate PNG bytes of machine QR code linking to /m/{qr_token}."""
    url = f"{settings.FRONTEND_URL}/m/{qr_token}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
