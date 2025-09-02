"""Tests for authentication functionality."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from request_manager.main import app, get_current_user


class TestWebApiKeyAuthentication:
    """Test cases for web API key authentication."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)

    def test_verify_web_api_key_valid(self):
        """Test valid web API key verification."""
        # Mock the environment
        with patch.dict(
            os.environ,
            {
                "API_KEYS_ENABLED": "true",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com", "web-admin": "admin@company.com"}',
            },
        ):
            # Reload the module to pick up new environment variables
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = request_manager.main.verify_web_api_key("web-test-user")
            assert result == "test@company.com"

    def test_verify_web_api_key_invalid(self):
        """Test invalid web API key verification."""
        with patch.dict(
            os.environ,
            {
                "API_KEYS_ENABLED": "true",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com"}',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = request_manager.main.verify_web_api_key("invalid-key")
            assert result is None

    def test_verify_web_api_key_disabled(self):
        """Test web API key verification when disabled."""
        with patch.dict(
            os.environ,
            {
                "API_KEYS_ENABLED": "false",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com"}',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = request_manager.main.verify_web_api_key("web-test-user")
            assert result is None

    def test_verify_web_api_key_empty(self):
        """Test web API key verification with empty key."""
        with patch.dict(
            os.environ,
            {
                "API_KEYS_ENABLED": "true",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com"}',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = request_manager.main.verify_web_api_key("")
            assert result is None

    def test_verify_web_api_key_none(self):
        """Test web API key verification with None key."""
        with patch.dict(
            os.environ,
            {
                "API_KEYS_ENABLED": "true",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com"}',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = request_manager.main.verify_web_api_key(None)
            assert result is None


class TestJWTValidation:
    """Test cases for JWT token validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_validate_jwt_token_disabled(self):
        """Test JWT validation when disabled."""
        with patch.dict(os.environ, {"JWT_ENABLED": "false", "JWT_ISSUERS": "[]"}):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = await request_manager.main.validate_jwt_token("any-token")
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_empty(self):
        """Test JWT validation with empty token."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = await request_manager.main.validate_jwt_token("")
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_none(self):
        """Test JWT validation with None token."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = await request_manager.main.validate_jwt_token(None)
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_invalid_format(self):
        """Test JWT validation with invalid token format."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            result = await request_manager.main.validate_jwt_token("invalid-token")
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_no_matching_issuer(self):
        """Test JWT validation with no matching issuer."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            # Mock a token with different algorithm
            with patch("request_manager.main.jwt.get_unverified_header") as mock_header:
                mock_header.return_value = {"alg": "HS256"}

                result = await request_manager.main.validate_jwt_token("test-token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_issuer_mismatch(self):
        """Test JWT validation with issuer mismatch."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
                "JWT_VERIFY_ISSUER": "true",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            # Mock a token with matching algorithm but wrong issuer
            with patch(
                "request_manager.main.jwt.get_unverified_header"
            ) as mock_header, patch("request_manager.main.jwt.decode") as mock_decode:
                mock_header.return_value = {"alg": "RS256"}
                mock_decode.return_value = {
                    "iss": "https://wrong.com",
                    "sub": "user123",
                }

                result = await request_manager.main.validate_jwt_token("test-token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_audience_mismatch(self):
        """Test JWT validation with audience mismatch."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "audience": "test-api", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
                "JWT_VERIFY_AUDIENCE": "true",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            # Mock a token with wrong audience
            with patch(
                "request_manager.main.jwt.get_unverified_header"
            ) as mock_header, patch("request_manager.main.jwt.decode") as mock_decode:
                mock_header.return_value = {"alg": "RS256"}
                mock_decode.return_value = {
                    "iss": "https://test.com",
                    "aud": "wrong-api",
                    "sub": "user123",
                }

                result = await request_manager.main.validate_jwt_token("test-token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_no_user_id(self):
        """Test JWT validation with no user ID in token."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            # Mock a token with no user ID
            with patch(
                "request_manager.main.jwt.get_unverified_header"
            ) as mock_header, patch("request_manager.main.jwt.decode") as mock_decode:
                mock_header.return_value = {"alg": "RS256"}
                mock_decode.return_value = {"iss": "https://test.com"}

                result = await request_manager.main.validate_jwt_token("test-token")
                assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_success(self):
        """Test successful JWT validation."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            # Mock a valid token
            with patch(
                "request_manager.main.jwt.get_unverified_header"
            ) as mock_header, patch("request_manager.main.jwt.decode") as mock_decode:
                mock_header.return_value = {"alg": "RS256"}
                mock_decode.return_value = {
                    "iss": "https://test.com",
                    "sub": "user123",
                    "email": "user@test.com",
                    "groups": ["admin", "user"],
                }

                result = await request_manager.main.validate_jwt_token("test-token")
                assert result is not None
                assert result["user_id"] == "user123"
                assert result["email"] == "user@test.com"
                assert result["groups"] == ["admin", "user"]
                assert result["token"] == "test-token"
                assert result["issuer"] == "https://test.com"


class TestGetCurrentUser:
    """Test cases for get_current_user function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    async def test_get_current_user_no_authorization(self):
        """Test get_current_user with no authorization header."""
        request = MagicMock()
        request.headers = {}

        result = await get_current_user(request, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_empty_credentials(self):
        """Test get_current_user with empty credentials."""
        request = MagicMock()
        request.headers = {}
        authorization = MagicMock()
        authorization.credentials = ""

        result = await get_current_user(request, authorization)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_jwt_success(self):
        """Test get_current_user with successful JWT authentication."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "true",
                "JWT_ISSUERS": '[{"issuer": "https://test.com", "algorithms": ["RS256"]}]',
                "JWT_VERIFY_SIGNATURE": "false",
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            request = MagicMock()
            request.headers = {}
            authorization = MagicMock()
            authorization.credentials = "jwt-token"

            # Mock successful JWT validation
            with patch("request_manager.main.validate_jwt_token") as mock_validate:
                mock_validate.return_value = {
                    "user_id": "user123",
                    "email": "user@test.com",
                    "groups": ["admin"],
                    "token": "jwt-token",
                }

                result = await get_current_user(request, authorization)
                assert result is not None
                assert result["user_id"] == "user123"
                assert result["email"] == "user@test.com"

    @pytest.mark.asyncio
    async def test_get_current_user_api_key_success(self):
        """Test get_current_user with successful API key authentication."""
        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "false",
                "API_KEYS_ENABLED": "true",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com"}',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            request = MagicMock()
            request.headers = {}
            authorization = MagicMock()
            authorization.credentials = "web-test-user"

            result = await get_current_user(request, authorization)
            assert result is not None
            assert result["user_id"] == "web-test-user"
            assert result["email"] == "test@company.com"
            assert result["auth_method"] == "api_key"

    @pytest.mark.asyncio
    async def test_get_current_user_service_mesh_headers(self):
        """Test get_current_user with service mesh headers."""
        with patch.dict(
            os.environ, {"JWT_ENABLED": "false", "API_KEYS_ENABLED": "false"}
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            request = MagicMock()
            request.headers = {
                "x-user-id": "service-mesh-user",
                "x-user-email": "user@service-mesh.com",
                "x-user-groups": "admin,user",
            }
            authorization = MagicMock()
            authorization.credentials = "service-mesh-token"

            result = await get_current_user(request, authorization)
            assert result is not None
            assert result["user_id"] == "service-mesh-user"
            assert result["email"] == "user@service-mesh.com"
            assert result["groups"] == ["admin", "user"]
            assert result["auth_method"] == "service_mesh"

    @pytest.mark.asyncio
    async def test_get_current_user_no_valid_auth(self):
        """Test get_current_user with no valid authentication method."""
        with patch.dict(
            os.environ, {"JWT_ENABLED": "false", "API_KEYS_ENABLED": "false"}
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            request = MagicMock()
            request.headers = {}
            authorization = MagicMock()
            authorization.credentials = "invalid-token"

            result = await get_current_user(request, authorization)
            assert result is None


class TestWebEndpointAuthentication:
    """Test cases for web endpoint authentication."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)

    def test_web_endpoint_no_authorization(self):
        """Test web endpoint with no authorization header."""
        response = self.client.post(
            "/api/v1/requests/web",
            json={
                "user_id": "test-user",
                "content": "Hello, I need help",
                "client_ip": "192.168.1.1",
            },
        )
        assert response.status_code == 401

    def test_web_endpoint_invalid_authorization(self):
        """Test web endpoint with invalid authorization."""
        response = self.client.post(
            "/api/v1/requests/web",
            headers={"Authorization": "Bearer invalid-token"},
            json={
                "user_id": "test-user",
                "content": "Hello, I need help",
                "client_ip": "192.168.1.1",
            },
        )
        assert response.status_code == 401

    def test_web_endpoint_user_id_mismatch(self):
        """Test web endpoint with user ID mismatch."""
        with patch.dict(
            os.environ,
            {
                "API_KEYS_ENABLED": "true",
                "WEB_API_KEYS": '{"web-test-user": "test@company.com"}',
            },
        ):
            import importlib

            import request_manager.main

            importlib.reload(request_manager.main)

            response = self.client.post(
                "/api/v1/requests/web",
                headers={"Authorization": "Bearer web-test-user"},
                json={
                    "user_id": "different-user",  # Different from API key
                    "content": "Hello, I need help",
                    "client_ip": "192.168.1.1",
                },
            )
            assert response.status_code == 403


class TestCLIEndpointAuthentication:
    """Test cases for CLI endpoint authentication."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)

    def test_cli_endpoint_no_authorization(self):
        """Test CLI endpoint with no authorization header."""
        response = self.client.post(
            "/api/v1/requests/cli",
            json={
                "user_id": "test-user",
                "content": "Hello, I need help",
                "cli_session_id": "cli-123",
            },
        )
        assert response.status_code == 401
