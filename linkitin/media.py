from linkitin.endpoints import MEDIA_UPLOAD_METADATA
from linkitin.exceptions import MediaError, RateLimitError
from linkitin.session import Session


async def upload_image(session: Session, image_data: bytes, filename: str) -> str:
    """Upload an image for use in a LinkedIn post.

    This is a two-step process:
    1. Register the upload with voyagerMediaUploadMetadata to get an upload URL.
    2. PUT the binary image data to the upload URL.

    Args:
        session: An authenticated Session.
        image_data: Raw image bytes.
        filename: Filename for the image (e.g., "photo.png").

    Returns:
        The media URN for use in create_post_with_media.

    Raises:
        MediaError: If the upload fails.
        RateLimitError: If rate limited by LinkedIn.
    """
    # Step 1: Register the upload to get metadata and upload URL.
    register_payload = {
        "mediaUploadType": "IMAGE_SHARING",
        "fileSize": len(image_data),
        "filename": filename,
    }

    response = await session.post(
        MEDIA_UPLOAD_METADATA + "?action=upload", json_data=register_payload,
    )

    if response.status_code == 429:
        raise RateLimitError("rate limited by LinkedIn - try again later")
    if response.status_code == 403:
        raise MediaError("forbidden - cookies may be expired, re-login required")
    if response.status_code not in (200, 201):
        raise MediaError(
            f"failed to register image upload: HTTP {response.status_code} - {response.text}"
        )

    data = response.json()

    # Normalized JSON wraps the payload under a "data" key.
    inner = data.get("data") if isinstance(data.get("data"), dict) else None

    # Extract the upload URL and media URN from the response.
    upload_url = _extract_upload_url(inner or data)
    media_urn = _extract_media_urn(inner or data)

    if not upload_url:
        raise MediaError("upload registration succeeded but no upload URL returned")
    if not media_urn:
        raise MediaError("upload registration succeeded but no media URN returned")

    # Step 2: PUT the binary image data to the upload URL.
    content_type = _guess_content_type(filename)
    upload_headers = {
        "Content-Type": content_type,
    }

    upload_response = await session.put(upload_url, content=image_data, headers=upload_headers)

    if upload_response.status_code == 429:
        raise RateLimitError("rate limited during image upload - try again later")
    if upload_response.status_code not in (200, 201):
        raise MediaError(
            f"failed to upload image data: HTTP {upload_response.status_code} - {upload_response.text}"
        )

    return media_urn


def _extract_upload_url(data: dict) -> str:
    """Extract the upload URL from the media registration response."""
    # Try standard path.
    value = data.get("value", data)

    upload_mechanism = value.get("uploadMechanism", {})
    if isinstance(upload_mechanism, dict):
        # Try MediaUploadHttpRequest path.
        http_request = upload_mechanism.get(
            "com.linkedin.voyager.common.MediaUploadHttpRequest", {}
        )
        if isinstance(http_request, dict):
            url = http_request.get("uploadUrl", "")
            if url:
                return url

        # Try single upload path.
        single = upload_mechanism.get("singleUpload", {})
        if isinstance(single, dict):
            url = single.get("uploadUrl", "")
            if url:
                return url

    # Direct uploadUrl field.
    url = value.get("uploadUrl", "")
    if url:
        return url

    # singleUploadUrl (used by voyagerMediaUploadMetadata?action=upload).
    url = value.get("singleUploadUrl", "")
    if url:
        return url

    return ""


def _extract_media_urn(data: dict) -> str:
    """Extract the media URN from the media registration response."""
    value = data.get("value", data)

    # Try urn field directly.
    urn = value.get("urn", "")
    if urn:
        return urn

    # Try mediaUrn field.
    urn = value.get("mediaUrn", "")
    if urn:
        return urn

    # Try media artifact URN.
    urn = value.get("mediaArtifact", "")
    if urn:
        return urn

    return ""


def _guess_content_type(filename: str) -> str:
    """Guess the content type from the filename extension."""
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"
