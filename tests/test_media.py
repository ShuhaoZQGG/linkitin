"""Tests for linkitin.media."""
import pytest

from linkitin.media import (
    _extract_media_urn,
    _extract_upload_url,
    _guess_content_type,
    upload_image,
)
from linkitin.exceptions import MediaError, RateLimitError
from tests.conftest import make_response


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestGuessContentType:
    def test_png(self):
        assert _guess_content_type("photo.png") == "image/png"

    def test_png_uppercase(self):
        assert _guess_content_type("PHOTO.PNG") == "image/png"

    def test_jpg(self):
        assert _guess_content_type("photo.jpg") == "image/jpeg"

    def test_jpeg(self):
        assert _guess_content_type("photo.jpeg") == "image/jpeg"

    def test_gif(self):
        assert _guess_content_type("anim.gif") == "image/gif"

    def test_webp(self):
        assert _guess_content_type("photo.webp") == "image/webp"

    def test_unknown(self):
        assert _guess_content_type("file.bin") == "application/octet-stream"


class TestExtractUploadUrl:
    def test_http_request_path(self):
        data = {
            "value": {
                "uploadMechanism": {
                    "com.linkedin.voyager.common.MediaUploadHttpRequest": {
                        "uploadUrl": "https://upload.example.com/1"
                    }
                }
            }
        }
        assert _extract_upload_url(data) == "https://upload.example.com/1"

    def test_single_upload_path(self):
        data = {
            "value": {
                "uploadMechanism": {
                    "singleUpload": {"uploadUrl": "https://upload.example.com/2"}
                }
            }
        }
        assert _extract_upload_url(data) == "https://upload.example.com/2"

    def test_direct_upload_url(self):
        data = {"value": {"uploadUrl": "https://upload.example.com/3"}}
        assert _extract_upload_url(data) == "https://upload.example.com/3"

    def test_single_upload_url(self):
        data = {"value": {"singleUploadUrl": "https://upload.example.com/4"}}
        assert _extract_upload_url(data) == "https://upload.example.com/4"

    def test_empty(self):
        assert _extract_upload_url({}) == ""
        assert _extract_upload_url({"value": {}}) == ""


class TestExtractMediaUrn:
    def test_urn_field(self):
        data = {"value": {"urn": "urn:li:digitalmediaAsset:C5600"}}
        assert _extract_media_urn(data) == "urn:li:digitalmediaAsset:C5600"

    def test_media_urn_field(self):
        data = {"value": {"mediaUrn": "urn:li:digitalmediaAsset:C5601"}}
        assert _extract_media_urn(data) == "urn:li:digitalmediaAsset:C5601"

    def test_media_artifact(self):
        data = {"value": {"mediaArtifact": "urn:li:digitalmediaAsset:C5602"}}
        assert _extract_media_urn(data) == "urn:li:digitalmediaAsset:C5602"

    def test_empty(self):
        assert _extract_media_urn({}) == ""
        assert _extract_media_urn({"value": {}}) == ""


# ---------------------------------------------------------------------------
# upload_image
# ---------------------------------------------------------------------------

class TestUploadImage:
    async def test_success(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={
                "value": {
                    "uploadUrl": "https://upload.example.com/upload",
                    "urn": "urn:li:digitalmediaAsset:C5600",
                    "uploadMechanism": {},
                    "singleUploadUrl": "https://upload.example.com/upload",
                }
            },
        )
        mock_session.put.return_value = make_response(status_code=201)

        urn = await upload_image(mock_session, b"fake png data", "photo.png")
        assert urn == "urn:li:digitalmediaAsset:C5600"

        # Verify PUT was called with correct content type
        put_call = mock_session.put.call_args
        assert put_call[1]["headers"]["Content-Type"] == "image/png"

    async def test_register_429(self, mock_session):
        mock_session.post.return_value = make_response(status_code=429)
        with pytest.raises(RateLimitError):
            await upload_image(mock_session, b"data", "img.png")

    async def test_register_403(self, mock_session):
        mock_session.post.return_value = make_response(status_code=403)
        with pytest.raises(MediaError, match="forbidden"):
            await upload_image(mock_session, b"data", "img.png")

    async def test_register_500(self, mock_session):
        mock_session.post.return_value = make_response(status_code=500, text="fail")
        with pytest.raises(MediaError, match="HTTP 500"):
            await upload_image(mock_session, b"data", "img.png")

    async def test_no_upload_url(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200, json_data={"value": {"urn": "urn:li:x:1"}}
        )
        with pytest.raises(MediaError, match="no upload URL"):
            await upload_image(mock_session, b"data", "img.png")

    async def test_no_media_urn(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={"value": {"singleUploadUrl": "https://x.com/up"}},
        )
        with pytest.raises(MediaError, match="no media URN"):
            await upload_image(mock_session, b"data", "img.png")

    async def test_upload_429(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={
                "value": {
                    "singleUploadUrl": "https://up.com/1",
                    "urn": "urn:li:x:1",
                }
            },
        )
        mock_session.put.return_value = make_response(status_code=429)
        with pytest.raises(RateLimitError):
            await upload_image(mock_session, b"data", "img.png")

    async def test_upload_500(self, mock_session):
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={
                "value": {
                    "singleUploadUrl": "https://up.com/1",
                    "urn": "urn:li:x:1",
                }
            },
        )
        mock_session.put.return_value = make_response(status_code=500, text="error")
        with pytest.raises(MediaError, match="failed to upload"):
            await upload_image(mock_session, b"data", "img.png")

    async def test_normalized_json_wrapper(self, mock_session):
        """Test that the 'data' wrapper is unwrapped correctly."""
        mock_session.post.return_value = make_response(
            status_code=200,
            json_data={
                "data": {
                    "value": {
                        "singleUploadUrl": "https://up.com/n",
                        "urn": "urn:li:digitalmediaAsset:N1",
                    }
                }
            },
        )
        mock_session.put.return_value = make_response(status_code=201)
        urn = await upload_image(mock_session, b"data", "img.jpg")
        assert urn == "urn:li:digitalmediaAsset:N1"
