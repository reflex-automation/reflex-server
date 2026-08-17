#  Copyright 2024 Red Hat, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""Module providing all event stream authentication types."""

import base64
import hmac
import logging
from abc import ABC, abstractmethod
from binascii import unhexlify
from dataclasses import dataclass
from typing import Optional

import jwt
import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt import PyJWKClient, decode as jwt_decode
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed

from aap_eda.core.enums import SignatureEncodingType
from aap_eda.core.utils.credentials import validate_x509_subject_match

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 30

# python-ecdsa's pure-Python signature verification is not constant-time
# (CVE-2024-23342 / GHSA-wj6h-64fc-37mp, Minerva timing attack on P-256;
# upstream python-ecdsa has no fix planned). Use cryptography's
# constant-time ECDSA verify instead for signatures on this
# attacker-controlled path.
_ECDSA_HASH_ALGORITHMS = {
    "md5": hashes.MD5,
    "sha1": hashes.SHA1,
    "sha224": hashes.SHA224,
    "sha256": hashes.SHA256,
    "sha384": hashes.SHA384,
    "sha512": hashes.SHA512,
    "sha512_224": hashes.SHA512_224,
    "sha512_256": hashes.SHA512_256,
    "sha3_224": hashes.SHA3_224,
    "sha3_256": hashes.SHA3_256,
    "sha3_384": hashes.SHA3_384,
    "sha3_512": hashes.SHA3_512,
}


class EventStreamAuthentication(ABC):
    """Base class for EventStream Authentication."""

    @abstractmethod
    def authenticate(self, body: Optional[bytes]):
        """Implement the authenticate maethod with body."""


@dataclass
class HMACAuthentication(EventStreamAuthentication):
    """HMAC Parameters."""

    signature: str
    hash_algorithm: str
    secret: str
    signature_prefix: str = ""
    signature_encoding: str = SignatureEncodingType.BASE64

    def authenticate(self, body: bytes):
        """Validate HMAC."""
        hash_object = hmac.new(
            self.secret,
            msg=body,
            digestmod=self.hash_algorithm or "sha256",
        )

        if self.signature_encoding == SignatureEncodingType.HEX:
            expected_signature = (
                self.signature_prefix + hash_object.hexdigest()
            )
        elif self.signature_encoding == SignatureEncodingType.BASE64:
            expected_signature = (
                self.signature_prefix
                + base64.b64encode(hash_object.digest()).decode()
            )
        else:
            message = (
                f"Invalid signature encoding {self.signature_encoding}. "
                "Should be either base64 or hex"
            )
            logger.warning(message)
            raise AuthenticationFailed(message)

        if not hmac.compare_digest(expected_signature, self.signature):
            message = "Signature mismatch, check your payload and secret"
            logger.warning(message)
            raise AuthenticationFailed(message)


@dataclass
class TokenAuthentication(EventStreamAuthentication):
    """Token Authentication."""

    token: str
    value: str

    def authenticate(self, _body=None):
        """Handle Token authentication."""
        if self.token != _token_sans_bearer(self.value):
            message = "Token mismatch, check your token"
            logger.warning(message)
            raise AuthenticationFailed(message)


@dataclass
class MTLSAuthentication(EventStreamAuthentication):
    """mTLS Authentication."""

    subject: str
    value: str

    def authenticate(self, _body=None):
        """Handle mTLS authentication."""
        if self.subject and not self.validate_subject(
            self.subject, self.value
        ):
            # Log details internally but don't leak in response
            logger.warning(
                f"Subject validation failed: {self.value} "
                f"does not match {self.subject}"
            )
            raise AuthenticationFailed("Authentication failed")

    def validate_subject(self, expected: str, actual: str) -> bool:
        """Validate that actual subject matches expected subject pattern.

        Uses shared X.509 standard-compliant DN parsing for attribute-level
        matching. Supports wildcards and is order-independent per X.509
        standards.

        Args:
            expected: Official subject pattern (may contain * wildcards)
            actual: Input subject from user

        Returns:
            bool: True if actual matches expected pattern, False otherwise
        """
        return validate_x509_subject_match(expected, actual)


@dataclass
class BasicAuthentication(EventStreamAuthentication):
    """Basic Authentication."""

    password: str
    username: str
    authorization: str

    def authenticate(self, _body=None):
        """Handle Basic authentication."""
        auth_str = self.authorization
        if self.authorization.startswith("Basic"):
            auth_str = self.authorization.split("Basic ")[1]

        user_pass = f"{self.username}:{self.password}"
        b64_value = base64.b64encode(user_pass.encode()).decode()
        if auth_str != b64_value:
            message = "Credential mismatch"
            logger.warning(message)
            raise AuthenticationFailed(message)


@dataclass
class Oauth2JwtAuthentication(EventStreamAuthentication):
    """OAuth2 JWT Authentication."""

    jwks_url: str
    audience: str
    access_token: str

    def authenticate(self, _body=None):
        """Handle OAuth2 JWT authentication."""
        if not jwt.algorithms.has_crypto:
            message = (
                "No crypto support for JWT, "
                "please install the cryptography dependency"
            )
            logger.error(message)
            raise AuthenticationFailed(message)

        try:
            token = _token_sans_bearer(self.access_token)
            jwks_client = PyJWKClient(
                self.jwks_url, cache_jwk_set=True, lifespan=360
            )
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": False,
            }

            if bool(self.audience):
                options["verify_aud"] = True

            signing_key = jwks_client.get_signing_key_from_jwt(token)
            jwt_decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                options=options,
            )
        except jwt.exceptions.PyJWTError as err:
            message = f"JWT error: {err}"
            logger.warning(message)
            raise AuthenticationFailed(message) from err


@dataclass
class Oauth2Authentication(EventStreamAuthentication):
    """OAuth2 Authentication."""

    introspection_url: str
    token: str
    client_id: str
    client_secret: str

    def authenticate(self, _body=None):
        """Handle OAuth2 authentication."""
        data = {
            "token": _token_sans_bearer(self.token),
            "token_type_hint": "access_token",
        }
        auth = (self.client_id, self.client_secret)
        # For keycloak this data is not in JSON format
        # instead of www-url-encoded
        response = requests.post(
            self.introspection_url,
            data=data,
            auth=auth,
            timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code != status.HTTP_200_OK:
            message = (
                f"Introspection Error {response.status_code} {response.text}"
            )
            logger.warning(message)
            raise AuthenticationFailed(message)

        response_data = response.json()
        if not response_data.get("active", False):
            message = "User is not active"
            logger.warning(message)
            raise AuthenticationFailed(message)


@dataclass
class EcdsaAuthentication(EventStreamAuthentication):
    """ECDSA Authentication."""

    public_key: str
    signature: str
    content_prefix: str
    hash_algorithm: str
    signature_encoding: str = SignatureEncodingType.BASE64

    def authenticate(self, body):
        """Handle ECDSA authentication."""
        logger.debug("Public Key %s", self.public_key)
        logger.debug("Signature %s", self.signature)
        logger.debug("Content Prefix %s", self.content_prefix)
        public_key = load_pem_public_key(self.public_key.encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            error = "Public key is not an EC key"
            logger.warning(error)
            raise AuthenticationFailed(error)

        if self.signature_encoding == SignatureEncodingType.HEX:
            decoded_signature = unhexlify(self.signature)
        elif self.signature_encoding == SignatureEncodingType.BASE64:
            decoded_signature = base64.b64decode(self.signature)
        else:
            message = (
                f"Invalid format {self.signature_encoding} "
                "should be either base64 or hex"
            )
            logger.warning(message)
            raise AuthenticationFailed(message)

        message_bytes = bytearray()
        if self.content_prefix:
            message_bytes.extend(self.content_prefix.encode())

        message_bytes.extend(body)

        hash_algorithm = _ECDSA_HASH_ALGORITHMS.get(
            self.hash_algorithm.lower()
        )
        if hash_algorithm is None:
            error = f"Unsupported ECDSA hash algorithm {self.hash_algorithm}"
            logger.warning(error)
            raise AuthenticationFailed(error)

        try:
            public_key.verify(
                decoded_signature,
                bytes(message_bytes),
                ec.ECDSA(hash_algorithm()),
            )
        except InvalidSignature as exc:
            error = "ECDSA signature does not match"
            logger.warning(error)
            raise AuthenticationFailed(error) from exc


def _token_sans_bearer(token: str) -> str:
    if token.startswith("Bearer"):
        return token.split("Bearer ")[1]
    return token
