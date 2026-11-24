"""Private document attachments."""
from pathlib import PurePosixPath
import unicodedata

from backend.app.services.workspace import DomainError

FILE_LIMIT = 10 * 1024 * 1024
SPACE_LIMIT = 250 * 1024 * 1024
SIGNATURES = {
    ".pdf": ("application/pdf", (b"%PDF-",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", (b"RIFF",)),
}


def attachment_type(name, content, image):
    normalized = unicodedata.normalize("NFC", name).strip()
    if (not normalized or "/" in normalized or "\\" in normalized
            or any(unicodedata.category(char).startswith("C") for char in normalized)):
        raise DomainError(422, "Nom de fichier invalide.")
    if len(content) > FILE_LIMIT:
        raise DomainError(413, "Ce fichier dépasse la limite de 10 Mio.")
    extension = PurePosixPath(normalized).suffix.lower()
    media_type, prefixes = SIGNATURES.get(extension, ("", ()))
    if (not content.startswith(prefixes) or (image and not media_type.startswith("image/"))
            or (extension == ".webp" and content[8:12] != b"WEBP")):
        raise DomainError(415, "Format de fichier non pris en charge.")
    return normalized, media_type
