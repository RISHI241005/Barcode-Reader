"""Account, history, catalog and admin APIs for the hosted Barcode Reader."""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from urllib.parse import urlparse

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.web_store import store

router = APIRouter(prefix='/api')
logger = logging.getLogger(__name__)
COOKIE = 'br_session'
SESSION_SECONDS = 1800


class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=72)
    admin_key: str = Field(default='', max_length=200)


class Login(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=10, max_length=72)


class UserUpdate(BaseModel):
    role: str = Field(pattern=r'^(USER|ADMIN)$')
    is_active: bool


def uid():
    return str(uuid.uuid4())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def public_user(user):
    return {key: user[key] for key in ['id', 'username', 'email', 'role', 'is_active', 'created_at']}


def audit(conn, user, action, details=''):
    conn.execute('INSERT INTO br_web_audit VALUES (%s,%s,%s,%s,%s,%s)',
                 (uid(), user['id'], user['username'], action, details, time.time()))


def database_required():
    if not store.configured:
        raise HTTPException(503, 'Account storage is being configured. Scanning is available without signing in.')


def same_origin(request):
    origin = request.headers.get('origin')
    if origin and urlparse(origin).netloc != request.url.netloc:
        raise HTTPException(403, 'This request must come from Barcode Reader')


def optional_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token or not store.configured:
        return None
    with store.connection() as conn:
        user = conn.execute('''SELECT u.*, s.csrf_token, s.created_at AS session_created
            FROM br_web_users u JOIN br_web_sessions s ON u.id=s.user_id
            WHERE s.token_hash=%s AND s.expires_at>%s AND u.is_active=1''',
            (digest(token), time.time())).fetchone()
        if not user:
            return None
        user = dict(user)
        if time.time() - user['session_created'] > 86400:
            conn.execute('DELETE FROM br_web_sessions WHERE token_hash=%s', (digest(token),))
            return None
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            same_origin(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), user['csrf_token']):
                raise HTTPException(403, 'Session verification failed. Refresh the page and try again.')
        conn.execute('UPDATE br_web_sessions SET expires_at=%s WHERE token_hash=%s',
                     (time.time() + SESSION_SECONDS, digest(token)))
        return user


def required_user(request: Request):
    database_required()
    user = optional_user(request)
    if not user:
        raise HTTPException(401, 'Please sign in to access your account')
    return user


def required_admin(user=Depends(required_user)):
    if user['role'] != 'ADMIN':
        raise HTTPException(403, 'Administrator access required')
    return user


def new_session(conn, user, request, response):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = time.time()
    conn.execute('DELETE FROM br_web_sessions WHERE expires_at<%s', (now,))
    conn.execute('INSERT INTO br_web_sessions VALUES (%s,%s,%s,%s,%s)',
                 (digest(token), user['id'], csrf, now + SESSION_SECONDS, now))
    response.set_cookie(COOKIE, token, max_age=86400, httponly=True,
                        secure=bool(os.getenv('VERCEL')) or request.url.scheme == 'https', samesite='lax')
    response.headers['Cache-Control'] = 'no-store'
    return {'user': public_user(user), 'csrf_token': csrf}


@lru_cache(maxsize=1)
def dummy_hash():
    return bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt(rounds=12))


def password_bytes(password):
    data = password.encode('utf-8')
    if len(data) > 72:
        raise HTTPException(400, 'Password must be at most 72 UTF-8 bytes')
    return data


@router.get('/auth/me')
def me(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    user = optional_user(request)
    return {'user': public_user(user) if user else None,
            'csrf_token': user['csrf_token'] if user else None,
            'accounts_available': store.configured}


@router.post('/auth/register')
def register(data: Registration, request: Request, response: Response):
    database_required()
    same_origin(request)
    email = data.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(400, 'Enter a valid email address')
    encoded = password_bytes(data.password)
    user = {'id': uid(), 'username': data.username.lower(), 'email': email,
            'password_hash': bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode(),
            'role': 'USER', 'is_active': 1, 'created_at': time.time()}
    with store.connection() as conn:
        conn.execute("UPDATE br_web_settings SET value=value WHERE name='admin_lock'")
        if conn.execute('SELECT id FROM br_web_users WHERE username=%s OR email=%s',
                        (user['username'], email)).fetchone():
            raise HTTPException(409, 'Username or email is already registered')
        if data.admin_key:
            expected = os.getenv('ADMIN_BOOTSTRAP_HASH', '')
            owner = os.getenv('ADMIN_EMAIL', '').strip().lower()
            if not expected or not owner or email != owner or not hmac.compare_digest(digest(data.admin_key), expected):
                raise HTTPException(403, 'Administrator setup details are incorrect')
            if conn.execute("SELECT id FROM br_web_users WHERE role='ADMIN'").fetchone():
                raise HTTPException(409, 'Administrator setup is already complete')
            if conn.execute("SELECT name FROM br_web_settings WHERE name='admin_bootstrapped'").fetchone():
                raise HTTPException(409, 'Administrator setup is already complete')
            user['role'] = 'ADMIN'
            conn.execute("INSERT INTO br_web_settings VALUES ('admin_bootstrapped', '1')")
        conn.execute('INSERT INTO br_web_users VALUES (%s,%s,%s,%s,%s,%s,%s)', tuple(user.values()))
        audit(conn, user, 'REGISTER', user['role'])
        return new_session(conn, user, request, response)


@router.post('/auth/login')
def login(data: Login, request: Request, response: Response):
    database_required()
    same_origin(request)
    ident = data.identifier.strip().lower()
    key = digest(ident)
    now = time.time()
    with store.connection() as conn:
        attempt = conn.execute('SELECT * FROM br_web_attempts WHERE identifier=%s', (key,)).fetchone()
        if attempt and attempt['blocked_until'] > now:
            raise HTTPException(429, 'Too many failed attempts. Try again in five minutes.')
        row = conn.execute('SELECT * FROM br_web_users WHERE username=%s OR email=%s', (ident, ident)).fetchone()
        user = dict(row) if row else None
        encoded = password_bytes(data.password)
        valid = bcrypt.checkpw(encoded, user['password_hash'].encode() if user else dummy_hash())
        if not user or not valid or not user['is_active']:
            # Atomic update prevents parallel requests from losing failed attempts.
            conn.execute('''INSERT INTO br_web_attempts VALUES (%s,1,0,%s)
                ON CONFLICT(identifier) DO UPDATE SET
                failures=CASE WHEN br_web_attempts.updated_at<%s THEN 1 ELSE br_web_attempts.failures+1 END,
                blocked_until=CASE WHEN br_web_attempts.updated_at>=%s AND br_web_attempts.failures>=4 THEN %s ELSE 0 END,
                updated_at=%s''', (key, now, now-300, now-300, now+300, now))
            if user:
                audit(conn, user, 'LOGIN_FAILED')
            # Raise after the transaction commits to persist the failure.
            result = None
        else:
            conn.execute('DELETE FROM br_web_attempts WHERE identifier=%s', (key,))
            audit(conn, user, 'LOGIN')
            result = new_session(conn, user, request, response)
    if result is None:
        raise HTTPException(401, 'Incorrect username/email or password')
    return result


@router.post('/auth/logout')
def logout(request: Request, response: Response, user=Depends(required_user)):
    with store.connection() as conn:
        conn.execute('DELETE FROM br_web_sessions WHERE token_hash=%s', (digest(request.cookies[COOKIE]),))
        audit(conn, user, 'LOGOUT')
    response.delete_cookie(COOKIE)
    return {'success': True}


@router.post('/auth/password')
def change_password(data: PasswordChange, request: Request, response: Response, user=Depends(required_user)):
    if not bcrypt.checkpw(password_bytes(data.current_password), user['password_hash'].encode()):
        raise HTTPException(400, 'Current password is incorrect')
    password_hash = bcrypt.hashpw(password_bytes(data.new_password), bcrypt.gensalt(rounds=12)).decode()
    with store.connection() as conn:
        conn.execute('UPDATE br_web_users SET password_hash=%s WHERE id=%s', (password_hash, user['id']))
        conn.execute('DELETE FROM br_web_sessions WHERE user_id=%s', (user['id'],))
        audit(conn, user, 'PASSWORD_CHANGED')
        return new_session(conn, user, request, response)


def save_scan_results(user, results, source, image_name, elapsed):
    if not user or not results:
        return
    with store.connection() as conn:
        for result in results:
            conn.execute('INSERT INTO br_web_scans VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (uid(), user['id'], result['barcode_type'], result['data'], source,
                          image_name[:255], result['validation_status'], elapsed, time.time()))


@router.get('/history')
def history(q: str = '', scope: str = 'personal', limit: int = 200, offset: int = 0, user=Depends(required_user)):
    if scope not in ('personal', 'system'):
        raise HTTPException(400, 'Invalid history scope')
    if scope == 'system' and user['role'] != 'ADMIN':
        raise HTTPException(403, 'Administrator access required')
    clauses, params = [], []
    if scope != 'system':
        clauses.append('s.user_id=%s')
        params.append(user['id'])
    if q:
        clauses.append('(LOWER(s.barcode_data) LIKE %s OR LOWER(s.barcode_type) LIKE %s)')
        params.extend(['%' + q[:255].lower() + '%'] * 2)
    where = 'WHERE ' + ' AND '.join(clauses) if clauses else ''
    with store.connection() as conn:
        total = conn.execute(f'SELECT COUNT(*) AS n FROM br_web_scans s {where}', tuple(params)).fetchone()['n']
        rows = conn.execute(f'''SELECT s.*, u.username FROM br_web_scans s JOIN br_web_users u ON s.user_id=u.id
            {where} ORDER BY s.created_at DESC, s.id DESC LIMIT %s OFFSET %s''',
            tuple(params + [max(1, min(limit, 500)), max(0, offset)])).fetchall()
    return {'scans': [dict(row) for row in rows], 'total': total}


@router.delete('/history/{scan_id}')
def delete_scan(scan_id: str, user=Depends(required_user)):
    with store.connection() as conn:
        row = conn.execute('SELECT * FROM br_web_scans WHERE id=%s', (scan_id,)).fetchone()
        if not row or (row['user_id'] != user['id'] and user['role'] != 'ADMIN'):
            raise HTTPException(404, 'Scan not found')
        conn.execute('DELETE FROM br_web_scans WHERE id=%s', (scan_id,))
        audit(conn, user, 'DELETE_SCAN', scan_id)
    return {'success': True}


@router.get('/analytics')
def analytics(scope: str = 'personal', user=Depends(required_user)):
    if scope not in ('personal', 'system'):
        raise HTTPException(400, 'Invalid analytics scope')
    if scope == 'system' and user['role'] != 'ADMIN':
        raise HTTPException(403, 'Administrator access required')
    where = 'WHERE user_id=%s' if scope == 'personal' else ''
    params = (user['id'],) if where else ()
    with store.connection() as conn:
        totals = dict(conn.execute(f'''SELECT COUNT(*) AS total, COUNT(DISTINCT barcode_data) AS unique_codes,
            COALESCE(SUM(CASE WHEN created_at>=%s THEN 1 ELSE 0 END),0) AS today,
            COALESCE(AVG(processing_time_ms),0) AS average_ms FROM br_web_scans {where}''',
            (time.time() - (time.time() % 86400),) + params).fetchone())
        formats = [dict(row) for row in conn.execute(f'''SELECT barcode_type, COUNT(*) AS count FROM br_web_scans
            {where} GROUP BY barcode_type ORDER BY count DESC''', params).fetchall()]
        recent = [dict(row) for row in conn.execute(f'''SELECT created_at FROM br_web_scans
            {where} ORDER BY created_at DESC LIMIT 10000''', params).fetchall()]
    return {**totals, 'formats': formats, 'activity': [row['created_at'] for row in recent]}


@router.get('/admin/users')
def users(user=Depends(required_admin)):
    with store.connection() as conn:
        rows = conn.execute('SELECT * FROM br_web_users ORDER BY created_at DESC LIMIT 500').fetchall()
    return {'users': [public_user(row) for row in rows]}


@router.patch('/admin/users/{user_id}')
def update_user(user_id: str, data: UserUpdate, user=Depends(required_admin)):
    with store.connection() as conn:
        conn.execute("UPDATE br_web_settings SET value=value WHERE name='admin_lock'")
        target = conn.execute('SELECT * FROM br_web_users WHERE id=%s', (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, 'User not found')
        if target['role'] == 'ADMIN' and target['is_active'] and (data.role != 'ADMIN' or not data.is_active):
            count = conn.execute("SELECT COUNT(*) AS n FROM br_web_users WHERE role='ADMIN' AND is_active=1").fetchone()['n']
            if count <= 1:
                raise HTTPException(409, 'At least one active administrator must remain')
        conn.execute('UPDATE br_web_users SET role=%s,is_active=%s WHERE id=%s', (data.role, int(data.is_active), user_id))
        # Role and activation changes invalidate existing sessions immediately.
        conn.execute('DELETE FROM br_web_sessions WHERE user_id=%s', (user_id,))
        audit(conn, user, 'UPDATE_USER', f"{target['username']}: {data.role}, active={data.is_active}")
    return {'success': True}


@router.get('/admin/audit')
def audit_logs(user=Depends(required_admin)):
    with store.connection() as conn:
        rows = conn.execute('SELECT * FROM br_web_audit ORDER BY created_at DESC LIMIT 300').fetchall()
    return {'events': [dict(row) for row in rows]}


@router.get('/products/{barcode}')
def product(barcode: str):
    if not re.fullmatch(r'[0-9]{8,14}', barcode):
        raise HTTPException(400, 'Food product lookup needs an 8–14 digit barcode')
    cached = None
    if store.configured:
        with store.connection() as conn:
            cached = conn.execute('SELECT * FROM br_web_products WHERE barcode=%s', (barcode,)).fetchone()
        if cached and cached['updated_at'] > time.time() - 86400:
            return {**json.loads(cached['payload']), 'cached': True}
    fields = 'product_name,product_name_en,brands,categories,quantity,ingredients_text,ingredients_text_en,allergens,image_front_url'
    req = URLRequest(f'https://world.openfoodfacts.org/api/v2/product/{barcode}.json?fields={fields}',
                     headers={'User-Agent': 'BarcodeReader/1.0 (https://barcode-reader-bay.vercel.app)'})
    try:
        with urlopen(req, timeout=8) as response:
            payload = json.loads(response.read(1024 * 1024))
        if not payload.get('status') or not payload.get('product'):
            raise HTTPException(404, 'This product is not listed in Open Food Facts')
        item = payload['product']
        result = {'barcode': barcode, 'name': item.get('product_name') or item.get('product_name_en') or 'Unnamed product',
                  'brand': item.get('brands', ''), 'category': item.get('categories', ''), 'quantity': item.get('quantity', ''),
                  'ingredients': item.get('ingredients_text_en') or item.get('ingredients_text', ''),
                  'allergens': item.get('allergens', ''), 'image_url': item.get('image_front_url', ''),
                  'source': 'Open Food Facts', 'source_url': f'https://world.openfoodfacts.org/product/{barcode}'}
        if store.configured:
            with store.connection() as conn:
                conn.execute('''INSERT INTO br_web_products VALUES (%s,%s,%s)
                    ON CONFLICT(barcode) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at''',
                    (barcode, json.dumps(result), time.time()))
        return {**result, 'cached': False}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        if cached:
            return {**json.loads(cached['payload']), 'cached': True}
        logger.warning('Product service unavailable: %s', type(exc).__name__)
        raise HTTPException(503, 'Product lookup is temporarily unavailable. Please try again.') from exc


@router.get('/products')
def catalog(q: str = '', user=Depends(required_user)):
    with store.connection() as conn:
        rows = conn.execute('SELECT * FROM br_web_products ORDER BY updated_at DESC LIMIT 200').fetchall()
    products = [json.loads(row['payload']) for row in rows]
    return {'products': [p for p in products if q.lower() in (p['barcode'] + ' ' + p['name'] + ' ' + p['brand']).lower()]}


@router.delete('/products/{barcode}')
def delete_product(barcode: str, user=Depends(required_admin)):
    with store.connection() as conn:
        conn.execute('DELETE FROM br_web_products WHERE barcode=%s', (barcode,))
        audit(conn, user, 'DELETE_PRODUCT', barcode)
    return {'success': True}
