"""
GenBridge Auth Utilities
JWT-based authentication with role-based access control
"""
import jwt
import os
import json
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g
from db import query

SECRET_KEY     = os.environ.get("SECRET_KEY", "genbridge-dev-secret-change-in-production-2025")
TOKEN_EXPIRY_H = int(os.environ.get("TOKEN_EXPIRY_H", "24"))


def generate_token(user_id: int, role: str, name: str, email: str) -> str:
    payload = {
        "sub":   user_id,
        "role":  role,
        "name":  name,
        "email": email,
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_H),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])


def require_auth(roles=None):
    """Decorator: validate JWT and optionally restrict by role."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing or invalid Authorization header"}), 401
            token = auth_header.split(" ", 1)[1]
            try:
                payload = decode_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError as e:
                return jsonify({"error": f"Invalid token: {e}"}), 401

            if roles and payload.get("role") not in roles:
                return jsonify({"error": f"Access denied. Required role: {roles}"}), 403

            # Attach user info to Flask g
            g.user_id = payload["sub"]
            g.role    = payload["role"]
            g.name    = payload["name"]
            g.email   = payload["email"]
            return fn(*args, **kwargs)
        return wrapper
    return decorator
