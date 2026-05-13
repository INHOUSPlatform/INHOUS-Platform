import hashlib
import secrets
import jwt
import datetime
import os
from functools import wraps
from flask import request, jsonify, g
from database import get_db

SECRET_KEY = os.environ.get('INHOUS_SECRET', 'inhous-dev-secret-change-in-production-2026')
TOKEN_EXPIRY_HOURS = 8

def hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 310000)
    return f"{salt}:{key.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, key_hex = stored.split(':', 1)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 310000)
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception:
        return False

def generate_token(user_id: int, role: str, email: str) -> str:
    payload = {
        'user_id': user_id,
        'role': role,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=['HS256'])

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required'}), 401
        token = auth_header[7:]
        try:
            payload = decode_token(token)
            g.user_id = payload['user_id']
            g.role = payload['role']
            g.email = payload['email']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired — please log in again'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            if g.role not in roles:
                return jsonify({'error': 'Access denied'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_property_access(f):
    """Check user has access to the property_id in the URL"""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        property_id = kwargs.get('property_id') or request.view_args.get('property_id')
        if not property_id:
            return f(*args, **kwargs)
        if g.role == 'broker':
            return f(*args, **kwargs)
        db = get_db()
        access = db.execute(
            'SELECT id FROM property_access WHERE property_id=? AND user_id=?',
            (property_id, g.user_id)
        ).fetchone()
        db.close()
        if not access:
            return jsonify({'error': 'Access denied to this property'}), 403
        return f(*args, **kwargs)
    return decorated

def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)
