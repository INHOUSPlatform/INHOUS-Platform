from flask import Flask, request, jsonify, g, send_from_directory, send_file
import os, json, datetime, secrets
from database import get_db, init_db, audit
from auth import (hash_password, verify_password, generate_token,
                  require_auth, require_role, require_property_access,
                  generate_invite_token)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

# ── CORS (manual, no flask-cors needed) ──────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    return response

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ── INTERNATIONALISATION HELPERS ──────────────────────────────────────────────
CURRENCY_SYMBOLS = {'GBP': '£', 'EUR': '€', 'USD': '$', 'CHF': 'CHF ', 'AED': 'AED '}
COUNTRY_CURRENCY = {
    'United Kingdom': 'GBP', 'Ireland': 'EUR', 'Portugal': 'EUR', 'Spain': 'EUR',
    'France': 'EUR', 'Switzerland': 'CHF', 'United Arab Emirates': 'AED',
    'United States': 'USD', 'Italy': 'EUR', 'Greece': 'EUR', 'Monaco': 'EUR',
    'Luxembourg': 'EUR', 'Belgium': 'EUR', 'Netherlands': 'EUR', 'Germany': 'EUR',
    'Austria': 'EUR',
}

def fmt_money(amount, currency='GBP'):
    """Currency-aware money formatting for notifications/audit text."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return str(amount)
    return f"{CURRENCY_SYMBOLS.get(currency or 'GBP', '')}{amount:,}"

def normalize_postcode(country, postcode):
    """Trim + upper-case a postcode. Permissive: every country's format is accepted
    (UK postcodes, Irish Eircodes, EU postal codes, US ZIPs, etc.) — never blocks."""
    return (postcode or '').strip().upper()

def to_int_or_none(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None

def notify(db, user_id, property_id, type_, title, message='', action_url=''):
    db.execute(
        'INSERT INTO notifications (user_id,property_id,type,title,message,action_url) VALUES (?,?,?,?,?,?)',
        (user_id, property_id, type_, title, message, action_url)
    )

# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email=? AND is_active=1', (email,)).fetchone()
    if not user or not verify_password(password, user['password_hash']):
        db.close()
        return jsonify({'error': 'Invalid email or password'}), 401
    db.execute('UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?', (user['id'],))
    audit(db, None, user['id'], 'login')
    db.commit()
    db.close()
    token = generate_token(user['id'], user['role'], user['email'])
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'agency_name': user['agency_name'],
        }
    })

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    db = get_db()
    user = db.execute('SELECT id,email,full_name,role,agency_name,phone,created_at,last_login FROM users WHERE id=?', (g.user_id,)).fetchone()
    db.close()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(row_to_dict(user))

@app.route('/api/auth/register-invite', methods=['POST'])
def register_via_invite():
    """Accept an invite token and create account"""
    data = request.get_json()
    token = data.get('token')
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    if not token or not password or not full_name:
        return jsonify({'error': 'Token, name and password required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    db = get_db()
    invite = db.execute(
        'SELECT * FROM invites WHERE token=? AND used_at IS NULL AND expires_at > CURRENT_TIMESTAMP',
        (token,)
    ).fetchone()
    if not invite:
        db.close()
        return jsonify({'error': 'Invite link is invalid or has expired'}), 400
    existing = db.execute('SELECT id FROM users WHERE email=?', (invite['email'],)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'An account with this email already exists'}), 400
    c = db.execute(
        'INSERT INTO users (email,password_hash,full_name,role,agency_name,phone) VALUES (?,?,?,?,?,?)',
        (invite['email'], hash_password(password), full_name, invite['role'],
         invite['agency_name'], phone)
    )
    user_id = c.lastrowid
    if invite['property_id']:
        db.execute(
            'INSERT OR IGNORE INTO property_access (property_id,user_id,role,accepted_at,invited_by) VALUES (?,?,?,CURRENT_TIMESTAMP,?)',
            (invite['property_id'], user_id, invite['role'], invite['invited_by'])
        )
    db.execute('UPDATE invites SET used_at=CURRENT_TIMESTAMP WHERE id=?', (invite['id'],))
    audit(db, invite['property_id'], user_id, 'account_created_via_invite')
    db.commit()
    db.close()
    token_jwt = generate_token(user_id, invite['role'], invite['email'])
    return jsonify({'token': token_jwt, 'user': {'id': user_id, 'email': invite['email'], 'full_name': full_name, 'role': invite['role']}})

# ══════════════════════════════════════════════════════════════════════════════
# PROPERTIES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties', methods=['GET'])
@require_auth
def get_properties():
    db = get_db()
    if g.role == 'broker':
        props = db.execute(
            'SELECT p.*, u.full_name as broker_name FROM properties p LEFT JOIN users u ON p.broker_id=u.id ORDER BY p.created_at DESC'
        ).fetchall()
    else:
        props = db.execute('''
            SELECT p.*, u.full_name as broker_name 
            FROM properties p
            LEFT JOIN users u ON p.broker_id=u.id
            JOIN property_access pa ON pa.property_id=p.id AND pa.user_id=?
            ORDER BY p.created_at DESC
        ''', (g.user_id,)).fetchall()
    db.close()
    return jsonify(rows_to_list(props))

@app.route('/api/properties', methods=['POST'])
@require_role('broker')
def create_property():
    data = request.get_json()
    required = ['address_line1', 'city', 'postcode']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'{f} is required'}), 400
    country = data.get('country') or 'United Kingdom'
    currency = data.get('currency') or COUNTRY_CURRENCY.get(country, 'GBP')
    postcode = normalize_postcode(country, data.get('postcode'))
    guide_price = to_int_or_none(data.get('guide_price'))
    db = get_db()
    c = db.execute('''INSERT INTO properties
        (address_line1,address_line2,city,state_region,postcode,country,currency,tenure,guide_price,
         bedrooms,floor_area_sqft,year_built,epc_rating,epc_cert_number,
         epc_valid_until,sale_mode,broker_id,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        data.get('address_line1'), data.get('address_line2'),
        data.get('city'), data.get('state_region'), postcode,
        country, currency,
        data.get('tenure'), guide_price,
        data.get('bedrooms'), data.get('floor_area_sqft'),
        data.get('year_built'), data.get('epc_rating'),
        data.get('epc_cert_number'), data.get('epc_valid_until'),
        data.get('sale_mode', 'managed'), g.user_id,
        data.get('notes')
    ))
    prop_id = c.lastrowid
    # Log launch price
    if guide_price:
        db.execute('INSERT INTO price_log (property_id,price,event_type,logged_by) VALUES (?,?,?,?)',
                   (prop_id, guide_price, 'launch', g.user_id))
    # Create photography booking record
    db.execute('INSERT INTO photography_bookings (property_id,booking_type) VALUES (?,?)',
               (prop_id, 'photography'))
    db.execute('INSERT INTO photography_bookings (property_id,booking_type) VALUES (?,?)',
               (prop_id, 'floorplan'))
    # Set default availability (Mon-Fri instant, Sat-Sun blocked)
    for dow, mode in [(0,'instant'),(1,'instant'),(2,'instant'),(3,'instant'),(4,'instant'),(5,'blocked'),(6,'blocked')]:
        db.execute('INSERT OR IGNORE INTO viewing_availability (property_id,day_of_week,mode) VALUES (?,?,?)',
                   (prop_id, dow, mode))
    audit(db, prop_id, g.user_id, 'property_created', 'property', prop_id)
    db.commit()
    db.close()
    return jsonify({'id': prop_id, 'message': 'Property created successfully'}), 201

@app.route('/api/properties/<int:property_id>', methods=['GET'])
@require_auth
@require_property_access
def get_property(property_id):
    db = get_db()
    prop = db.execute(
        'SELECT p.*, u.full_name as broker_name, u.phone as broker_phone, u.email as broker_email FROM properties p LEFT JOIN users u ON p.broker_id=u.id WHERE p.id=?',
        (property_id,)
    ).fetchone()
    if not prop:
        db.close()
        return jsonify({'error': 'Property not found'}), 404
    result = row_to_dict(prop)
    # Add price log
    result['price_log'] = rows_to_list(db.execute(
        'SELECT pl.*, u.full_name as logged_by_name FROM price_log pl LEFT JOIN users u ON pl.logged_by=u.id WHERE pl.property_id=? ORDER BY pl.created_at DESC',
        (property_id,)
    ).fetchall())
    db.close()
    return jsonify(result)

@app.route('/api/properties/<int:property_id>', methods=['PATCH'])
@require_role('broker')
def update_property(property_id):
    data = request.get_json()
    db = get_db()
    prop = db.execute('SELECT * FROM properties WHERE id=?', (property_id,)).fetchone()
    if not prop:
        db.close()
        return jsonify({'error': 'Property not found'}), 404
    allowed = ['address_line1','address_line2','city','state_region','postcode','country','currency',
               'tenure','guide_price','bedrooms','floor_area_sqft','year_built','epc_rating',
               'epc_cert_number','epc_valid_until','sale_mode','status','notes']
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        db.close()
        return jsonify({'error': 'No valid fields to update'}), 400
    if 'postcode' in updates:
        updates['postcode'] = normalize_postcode(updates.get('country') or prop['country'], updates['postcode'])
    # Log price change (guard against NULL/string guide_price)
    if 'guide_price' in updates:
        new_gp = to_int_or_none(updates['guide_price'])
        updates['guide_price'] = new_gp
        old_gp = prop['guide_price']
        if new_gp is not None and new_gp != old_gp:
            event = 'increase' if old_gp is None else ('reduction' if new_gp < old_gp else 'increase')
            db.execute('INSERT INTO price_log (property_id,price,event_type,notes,logged_by) VALUES (?,?,?,?,?)',
                       (property_id, new_gp, event, data.get('price_notes'), g.user_id))
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE properties SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?',
               list(updates.values()) + [property_id])
    audit(db, property_id, g.user_id, 'property_updated', 'property', property_id, json.dumps(updates))
    db.commit()
    db.close()
    return jsonify({'message': 'Property updated'})

# ══════════════════════════════════════════════════════════════════════════════
# INVITES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/invite', methods=['POST'])
@require_role('broker')
def send_invite(property_id):
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()
    role = data.get('role')
    valid_roles = ['vendor','agent','vendor_solicitor','buyer_solicitor','buyer','family_office']
    if not email or role not in valid_roles:
        return jsonify({'error': 'Email and valid role required'}), 400
    db = get_db()
    token = generate_invite_token()
    expires = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat()
    db.execute('''INSERT INTO invites (property_id,email,role,token,invited_by,agency_name,message,expires_at)
                  VALUES (?,?,?,?,?,?,?,?)''',
               (property_id, email, role, token, g.user_id,
                data.get('agency_name'), data.get('message'), expires))
    audit(db, property_id, g.user_id, 'invite_sent', 'invite', None, f'{role}:{email}')
    db.commit()
    db.close()
    invite_url = f"http://localhost:5001/invite/{token}"
    return jsonify({'message': f'Invite sent to {email}', 'token': token, 'invite_url': invite_url})

@app.route('/api/invite/<token>', methods=['GET'])
def get_invite(token):
    db = get_db()
    invite = db.execute(
        'SELECT i.*, p.address_line1, p.city, p.postcode FROM invites i LEFT JOIN properties p ON i.property_id=p.id WHERE i.token=? AND i.used_at IS NULL AND i.expires_at > CURRENT_TIMESTAMP',
        (token,)
    ).fetchone()
    db.close()
    if not invite:
        return jsonify({'error': 'Invite is invalid or has expired'}), 404
    return jsonify({
        'email': invite['email'],
        'role': invite['role'],
        'agency_name': invite['agency_name'],
        'property_address': f"{invite['address_line1']}, {invite['city']} {invite['postcode']}" if invite['address_line1'] else None,
        'message': invite['message'],
    })

# ══════════════════════════════════════════════════════════════════════════════
# PHOTOGRAPHY BOOKINGS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/photography', methods=['GET'])
@require_auth
@require_property_access
def get_photography(property_id):
    db = get_db()
    bookings = db.execute(
        'SELECT * FROM photography_bookings WHERE property_id=? ORDER BY booking_type',
        (property_id,)
    ).fetchall()
    db.close()
    return jsonify(rows_to_list(bookings))

@app.route('/api/properties/<int:property_id>/photography/<int:booking_id>', methods=['PATCH'])
@require_auth
@require_property_access
def update_photography(property_id, booking_id):
    data = request.get_json()
    db = get_db()
    booking = db.execute('SELECT * FROM photography_bookings WHERE id=? AND property_id=?', (booking_id, property_id)).fetchone()
    if not booking:
        db.close()
        return jsonify({'error': 'Booking not found'}), 404
    allowed = ['preferred_date','preferred_time','photographer_firm','photographer_contact',
               'photographer_email','vendor_notes','broker_brief','shoot_date','shoot_time','status']
    updates = {k: v for k, v in data.items() if k in allowed}
    if 'preferred_date' in updates and booking['status'] == 'pending':
        updates['status'] = 'date_selected'
    if not updates:
        db.close()
        return jsonify({'error': 'Nothing to update'}), 400
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE photography_bookings SET {set_clause} WHERE id=?', list(updates.values()) + [booking_id])
    if updates.get('status') == 'date_selected':
        db.execute('UPDATE properties SET status=? WHERE id=? AND status=?',
                   ('photography_booked', property_id, 'onboarding'))
    audit(db, property_id, g.user_id, 'photography_updated', 'photography_booking', booking_id)
    db.commit()
    db.close()
    return jsonify({'message': 'Photography booking updated'})

# ══════════════════════════════════════════════════════════════════════════════
# VIEWING SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/availability', methods=['GET'])
@require_auth
@require_property_access
def get_availability(property_id):
    db = get_db()
    dow_avail = rows_to_list(db.execute(
        'SELECT * FROM viewing_availability WHERE property_id=? AND day_of_week IS NOT NULL ORDER BY day_of_week',
        (property_id,)
    ).fetchall())
    date_overrides = rows_to_list(db.execute(
        'SELECT * FROM viewing_availability WHERE property_id=? AND specific_date IS NOT NULL ORDER BY specific_date',
        (property_id,)
    ).fetchall())
    # Get settings from first availability record
    settings = db.execute('SELECT viewing_duration_mins,buffer_mins,max_per_day,earliest_start,latest_start,min_notice_hours FROM viewing_availability WHERE property_id=? LIMIT 1', (property_id,)).fetchone()
    db.close()
    return jsonify({
        'by_day_of_week': dow_avail,
        'date_overrides': date_overrides,
        'settings': row_to_dict(settings) or {
            'viewing_duration_mins': 45, 'buffer_mins': 60,
            'max_per_day': 4, 'earliest_start': '09:00',
            'latest_start': '16:00', 'min_notice_hours': 4
        }
    })

@app.route('/api/properties/<int:property_id>/availability', methods=['PATCH'])
@require_auth
@require_property_access
def update_availability(property_id):
    data = request.get_json()
    db = get_db()
    # Update day-of-week modes
    if 'days' in data:
        for day_update in data['days']:
            dow = day_update.get('day_of_week')
            mode = day_update.get('mode')
            if dow is not None and mode in ('instant','confirm','blocked'):
                db.execute('''INSERT INTO viewing_availability (property_id,day_of_week,mode)
                              VALUES (?,?,?) ON CONFLICT(property_id,day_of_week)
                              DO UPDATE SET mode=excluded.mode''', (property_id, dow, mode))
    # Update settings
    settings_fields = ['viewing_duration_mins','buffer_mins','max_per_day','earliest_start','latest_start','min_notice_hours']
    settings_update = {k: v for k, v in data.items() if k in settings_fields}
    if settings_update:
        for dow in range(7):
            for k, v in settings_update.items():
                db.execute(f'UPDATE viewing_availability SET {k}=? WHERE property_id=? AND day_of_week=?', (v, property_id, dow))
    # Date overrides
    if 'date_override' in data:
        override = data['date_override']
        db.execute('''INSERT INTO viewing_availability (property_id,specific_date,mode)
                      VALUES (?,?,?) ON CONFLICT(property_id,specific_date)
                      DO UPDATE SET mode=excluded.mode''',
                   (property_id, override['date'], override['mode']))
    audit(db, property_id, g.user_id, 'availability_updated', 'availability', None)
    db.commit()
    db.close()
    return jsonify({'message': 'Availability updated'})

@app.route('/api/properties/<int:property_id>/available-slots', methods=['GET'])
@require_auth
@require_property_access
def get_available_slots(property_id):
    """Return available slots for a given date"""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'date parameter required (YYYY-MM-DD)'}), 400
    try:
        target_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    db = get_db()
    avail = db.execute(
        'SELECT * FROM viewing_availability WHERE property_id=? AND specific_date=?',
        (property_id, date_str)
    ).fetchone()
    if not avail:
        avail = db.execute(
            'SELECT * FROM viewing_availability WHERE property_id=? AND day_of_week=?',
            (property_id, target_date.weekday())
        ).fetchone()
    if not avail or avail['mode'] == 'blocked':
        db.close()
        return jsonify({'slots': [], 'mode': 'blocked'})

    duration = avail['viewing_duration_mins'] or 45
    buffer = avail['buffer_mins'] or 60
    max_per_day = avail['max_per_day'] or 4
    earliest = avail['earliest_start'] or '09:00'
    latest = avail['latest_start'] or '16:00'
    min_notice = avail['min_notice_hours'] or 4
    mode = avail['mode']

    # Get existing bookings for this date
    bookings = db.execute(
        "SELECT requested_time, slot_end_time FROM viewing_requests WHERE property_id=? AND requested_date=? AND status NOT IN ('declined','cancelled_agent','cancelled_vendor')",
        (property_id, date_str)
    ).fetchall()
    db.close()

    # Build list of blocked time ranges
    blocked_ranges = []
    for b in bookings:
        start = _time_to_mins(b['requested_time'])
        # Block: from start through viewing + buffer
        blocked_ranges.append((start, start + duration + buffer))

    # Generate candidate slots
    slots = []
    current = _time_to_mins(earliest)
    end_limit = _time_to_mins(latest)
    now_mins = _time_to_mins(datetime.datetime.utcnow().strftime('%H:%M')) + (min_notice * 60) if date_str == str(datetime.date.today()) else 0

    while current <= end_limit and len([s for s in slots if s['available']]) < max_per_day:
        available = True
        if current < now_mins and date_str == str(datetime.date.today()):
            available = False
        for (block_start, block_end) in blocked_ranges:
            if current >= block_start and current < block_end:
                available = False
                break
            if current < block_start and current + duration > block_start:
                available = False
                break
        slot_time = _mins_to_time(current)
        end_time = _mins_to_time(current + duration)
        is_booked = any(b['requested_time'] == slot_time for b in bookings)
        slots.append({
            'time': slot_time,
            'end_time': end_time,
            'available': available and not is_booked,
            'booked': is_booked,
            'mode': mode if (available and not is_booked) else ('booked' if is_booked else 'unavailable')
        })
        current += 30  # 30-min increments

    return jsonify({'slots': slots, 'mode': mode, 'settings': {
        'duration_mins': duration, 'buffer_mins': buffer
    }})

def _time_to_mins(t):
    if not t:
        return 0
    t = str(t)[:5]
    h, m = t.split(':')
    return int(h) * 60 + int(m)

def _mins_to_time(m):
    return f"{m // 60:02d}:{m % 60:02d}"

@app.route('/api/properties/<int:property_id>/viewings', methods=['GET'])
@require_auth
@require_property_access
def get_viewings(property_id):
    db = get_db()
    if g.role in ('broker', 'vendor'):
        # Broker and vendor see all viewings — vendor sees agency name only (not negotiator name)
        viewings = rows_to_list(db.execute('''
            SELECT vr.id, vr.property_id, vr.requested_date, vr.requested_time,
                   vr.slot_end_time, vr.booking_mode, vr.status, vr.buyer_reference,
                   vr.created_at, vr.confirmed_at, vr.feedback_sent_at, vr.feedback_submitted_at,
                   vr.agency_name,
                   CASE WHEN ? = 'broker' THEN vr.negotiator_name ELSE NULL END as negotiator_name,
                   CASE WHEN ? = 'broker' THEN vr.negotiator_email ELSE NULL END as negotiator_email
            FROM viewing_requests vr
            WHERE vr.property_id=?
            ORDER BY vr.requested_date DESC, vr.requested_time
        ''', (g.role, g.role, property_id)).fetchall())
    else:
        # Agent sees own bookings only
        viewings = rows_to_list(db.execute('''
            SELECT * FROM viewing_requests
            WHERE property_id=? AND requested_by=?
            ORDER BY requested_date DESC, requested_time
        ''', (property_id, g.user_id)).fetchall())
    db.close()
    return jsonify(viewings)

@app.route('/api/properties/<int:property_id>/viewings', methods=['POST'])
@require_auth
@require_property_access
def book_viewing(property_id):
    data = request.get_json()
    requested_date = data.get('requested_date')
    requested_time = data.get('requested_time')
    if not requested_date or not requested_time:
        return jsonify({'error': 'Date and time required'}), 400

    db = get_db()
    # Check for conflict
    conflict = db.execute(
        "SELECT id FROM viewing_requests WHERE property_id=? AND requested_date=? AND requested_time=? AND status NOT IN ('declined','cancelled_agent','cancelled_vendor')",
        (property_id, requested_date, requested_time)
    ).fetchone()
    if conflict:
        db.close()
        return jsonify({'error': 'This slot is no longer available'}), 409

    # Get availability mode for this date
    avail = db.execute(
        'SELECT * FROM viewing_availability WHERE property_id=? AND specific_date=?',
        (property_id, requested_date)
    ).fetchone()
    if not avail:
        target = datetime.date.fromisoformat(requested_date)
        avail = db.execute(
            'SELECT * FROM viewing_availability WHERE property_id=? AND day_of_week=?',
            (property_id, target.weekday())
        ).fetchone()
    if not avail or avail['mode'] == 'blocked':
        db.close()
        return jsonify({'error': 'This date is not available for viewings'}), 400

    mode = avail['mode']
    duration = avail['viewing_duration_mins'] or 45
    end_mins = _time_to_mins(requested_time) + duration
    slot_end = _mins_to_time(end_mins)

    # Determine negotiator details — agent from profile, broker can provide
    if g.role == 'agent':
        user = db.execute('SELECT full_name, email, phone, agency_name FROM users WHERE id=?', (g.user_id,)).fetchone()
        negotiator_name = user['full_name']
        negotiator_email = user['email']
        negotiator_phone = user['phone']
        agency_name = user['agency_name'] or data.get('agency_name', '')
    else:
        negotiator_name = data.get('negotiator_name', 'INHOUS')
        negotiator_email = data.get('negotiator_email', '')
        negotiator_phone = data.get('negotiator_phone', '')
        agency_name = data.get('agency_name', 'INHOUS')

    status = 'confirmed' if mode == 'instant' else 'pending'

    c = db.execute('''INSERT INTO viewing_requests
        (property_id,requested_by,agency_name,negotiator_name,negotiator_email,
         negotiator_phone,buyer_reference,buyer_notes,requested_date,requested_time,
         slot_end_time,booking_mode,status,confirmed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        property_id, g.user_id, agency_name, negotiator_name, negotiator_email,
        negotiator_phone, data.get('buyer_reference',''), data.get('buyer_notes',''),
        requested_date, requested_time, slot_end, mode, status,
        datetime.datetime.utcnow().isoformat() if mode == 'instant' else None
    ))
    viewing_id = c.lastrowid

    # Notify broker
    prop = db.execute('SELECT address_line1,broker_id FROM properties WHERE id=?', (property_id,)).fetchone()
    notify(db, prop['broker_id'], property_id, 'viewing_booked',
           f"{'Viewing confirmed' if mode == 'instant' else 'Viewing request'} — {agency_name}",
           f"{requested_date} at {requested_time}" + (f" · {data.get('buyer_reference','')}" if data.get('buyer_reference') else ''))

    if mode == 'confirm':
        # Also notify vendor if they have access
        vendor = db.execute("SELECT user_id FROM property_access WHERE property_id=? AND role='vendor'", (property_id,)).fetchone()
        if vendor:
            notify(db, vendor['user_id'], property_id, 'viewing_request',
                   f"Viewing request from {agency_name}",
                   f"{requested_date} at {requested_time} · Please confirm or decline")

    audit(db, property_id, g.user_id, 'viewing_booked', 'viewing', viewing_id, f'{mode}:{requested_date}:{requested_time}')
    db.commit()
    db.close()
    return jsonify({'id': viewing_id, 'status': status, 'message': 'Viewing booked' if mode == 'instant' else 'Viewing request submitted — awaiting confirmation'}), 201

@app.route('/api/properties/<int:property_id>/viewings/<int:viewing_id>/confirm', methods=['POST'])
@require_role('broker', 'vendor')
def confirm_viewing(property_id, viewing_id):
    data = request.get_json() or {}
    db = get_db()
    viewing = db.execute('SELECT * FROM viewing_requests WHERE id=? AND property_id=?', (viewing_id, property_id)).fetchone()
    if not viewing:
        db.close()
        return jsonify({'error': 'Viewing not found'}), 404
    if viewing['status'] != 'pending':
        db.close()
        return jsonify({'error': 'Viewing is not pending confirmation'}), 400
    action = data.get('action', 'confirm')
    if action == 'confirm':
        db.execute('UPDATE viewing_requests SET status=?, confirmed_by=?, confirmed_at=CURRENT_TIMESTAMP WHERE id=?',
                   ('confirmed', g.user_id, viewing_id))
        # Notify the agent who booked
        notify(db, viewing['requested_by'], property_id, 'viewing_confirmed',
               'Viewing confirmed', f"{viewing['requested_date']} at {viewing['requested_time']}")
    else:
        db.execute('UPDATE viewing_requests SET status=?, declined_reason=? WHERE id=?',
                   ('declined', data.get('reason',''), viewing_id))
        notify(db, viewing['requested_by'], property_id, 'viewing_declined',
               'Viewing request declined', data.get('reason',''))
    audit(db, property_id, g.user_id, f'viewing_{action}', 'viewing', viewing_id)
    db.commit()
    db.close()
    return jsonify({'message': f'Viewing {action}ed'})

# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/feedback', methods=['GET'])
@require_auth
@require_property_access
def get_feedback(property_id):
    db = get_db()
    if g.role in ('broker', 'vendor'):
        feedback = rows_to_list(db.execute('''
            SELECT vf.*, vr.requested_date, vr.requested_time,
                   vr.agency_name,
                   CASE WHEN ? = 'broker' THEN vr.negotiator_name ELSE NULL END as negotiator_name
            FROM viewing_feedback vf
            JOIN viewing_requests vr ON vf.viewing_id=vr.id
            WHERE vf.property_id=?
            ORDER BY vr.requested_date DESC
        ''', (g.role, property_id)).fetchall())
    else:
        feedback = rows_to_list(db.execute('''
            SELECT vf.*, vr.requested_date, vr.requested_time
            FROM viewing_feedback vf
            JOIN viewing_requests vr ON vf.viewing_id=vr.id
            WHERE vf.property_id=? AND vr.requested_by=?
        ''', (property_id, g.user_id)).fetchall())
    db.close()
    # Expose only whether audio exists, not the server file path
    for f in feedback:
        f['has_audio'] = bool(f.get('audio_path'))
        f.pop('audio_path', None)
    return jsonify(feedback)

@app.route('/api/properties/<int:property_id>/viewings/<int:viewing_id>/feedback', methods=['POST'])
@require_auth
@require_property_access
def submit_feedback(property_id, viewing_id):
    data = request.get_json()
    db = get_db()
    viewing = db.execute('SELECT * FROM viewing_requests WHERE id=? AND property_id=?', (viewing_id, property_id)).fetchone()
    if not viewing:
        db.close()
        return jsonify({'error': 'Viewing not found'}), 404
    # Update viewing status
    db.execute('UPDATE viewing_requests SET status=?, feedback_submitted_at=CURRENT_TIMESTAMP WHERE id=?',
               ('completed', viewing_id))
    c = db.execute('''INSERT INTO viewing_feedback
        (viewing_id,property_id,submitted_by,interest_level,buyer_type,chain_status,
         budget_range,objections,competing_properties,follow_up_likelihood,comments,broker_note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
        viewing_id, property_id, g.user_id,
        data.get('interest_level'), data.get('buyer_type'), data.get('chain_status'),
        data.get('budget_range'), data.get('objections'), data.get('competing_properties'),
        data.get('follow_up_likelihood'), data.get('comments'),
        data.get('broker_note') if g.role == 'broker' else None
    ))
    feedback_id = c.lastrowid
    # Notify broker
    prop = db.execute('SELECT broker_id FROM properties WHERE id=?', (property_id,)).fetchone()
    notify(db, prop['broker_id'], property_id, 'feedback_received',
           f"Feedback received — {viewing['agency_name']}", viewing['requested_date'])
    audit(db, property_id, g.user_id, 'feedback_submitted', 'viewing', viewing_id)
    db.commit()
    db.close()
    return jsonify({'id': feedback_id, 'message': 'Feedback submitted'}), 201

@app.route('/api/properties/<int:property_id>/feedback/<int:feedback_id>/audio', methods=['POST'])
@require_auth
@require_property_access
def upload_feedback_audio(property_id, feedback_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No audio uploaded'}), 400
    file = request.files['file']
    db = get_db()
    fb = db.execute('SELECT * FROM viewing_feedback WHERE id=? AND property_id=?', (feedback_id, property_id)).fetchone()
    if not fb:
        db.close()
        return jsonify({'error': 'Feedback not found'}), 404
    # Only the submitter (or the broker) may attach audio to a feedback record
    if g.role != 'broker' and fb['submitted_by'] != g.user_id:
        db.close()
        return jsonify({'error': 'You can only attach audio to your own feedback'}), 403
    ext = os.path.splitext(file.filename or '')[1] or '.webm'
    safe_name = secrets.token_hex(16) + ext
    save_dir = os.path.join(UPLOAD_DIR, 'voice_feedback')
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, safe_name)
    file.save(file_path)
    db.execute('UPDATE viewing_feedback SET audio_path=?, audio_filename=? WHERE id=?',
               (file_path, file.filename or safe_name, feedback_id))
    audit(db, property_id, g.user_id, 'feedback_audio_uploaded', 'viewing_feedback', feedback_id)
    db.commit()
    db.close()
    return jsonify({'message': 'Voice feedback uploaded'}), 201

@app.route('/api/properties/<int:property_id>/feedback/<int:feedback_id>/audio', methods=['GET'])
@require_auth
@require_property_access
def get_feedback_audio(property_id, feedback_id):
    db = get_db()
    fb = db.execute('SELECT * FROM viewing_feedback WHERE id=? AND property_id=?', (feedback_id, property_id)).fetchone()
    db.close()
    if not fb or not fb['audio_path']:
        return jsonify({'error': 'No audio for this feedback'}), 404
    # Agents may only hear their own; broker/vendor can hear all
    if g.role not in ('broker', 'vendor') and fb['submitted_by'] != g.user_id:
        return jsonify({'error': 'Access denied'}), 403
    if not os.path.exists(fb['audio_path']):
        return jsonify({'error': 'Audio file not found on server'}), 404
    return send_file(fb['audio_path'], mimetype='audio/webm')

# ══════════════════════════════════════════════════════════════════════════════
# OFFERS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/offers', methods=['GET'])
@require_auth
@require_property_access
def get_offers(property_id):
    db = get_db()
    if g.role in ('broker', 'vendor'):
        # Vendor sees all offers but NOT negotiator contact details or broker notes
        cols = '''o.id, o.property_id, o.amount, o.status, o.created_at, o.updated_at,
                  o.buyer_full_name, o.buyer_type, o.purchase_method, o.cash_percent,
                  o.mortgage_percent, o.chain_status, o.conditions, o.proposed_exchange,
                  o.proposed_completion, o.proof_of_funds_status, o.buyer_aml_status,
                  o.counter_amount, o.agency_name, o.buyer_solicitor_firm,
                  o.accepted_at, o.declined_at, o.valid_until,
                  o.offer_date, o.reason_for_purchase, o.properties_viewed'''
        if g.role == 'broker':
            cols += ''', o.negotiator_name, o.broker_notes,
                       o.agent_notes, o.buyer_email, o.buyer_phone,
                       o.buyer_profession, o.buyer_nationality, o.buyer_address,
                       o.financial_provider, o.property_to_sell, o.competing_properties,
                       o.buyer_solicitor_name, o.buyer_solicitor_email, o.buyer_solicitor_phone,
                       o.inhous_fee, o.time_looking'''
        offers = rows_to_list(db.execute(f'SELECT {cols} FROM offers o WHERE o.property_id=? ORDER BY o.amount DESC', (property_id,)).fetchall())
    else:
        # Agent sees own submission status only
        offers = rows_to_list(db.execute(
            'SELECT id, amount, status, created_at, conditions FROM offers WHERE property_id=? AND submitted_by=?',
            (property_id, g.user_id)
        ).fetchall())
    db.close()
    return jsonify(offers)

@app.route('/api/properties/<int:property_id>/offers', methods=['POST'])
@require_auth
@require_property_access
def submit_offer(property_id):
    data = request.get_json()
    if not data.get('amount') or not data.get('buyer_full_name'):
        return jsonify({'error': 'Amount and buyer name required'}), 400
    amount = to_int_or_none(data.get('amount'))
    if amount is None:
        return jsonify({'error': 'Amount must be a number'}), 400
    db = get_db()
    # Get negotiator details if agent
    if g.role == 'agent':
        user = db.execute('SELECT full_name, email, agency_name FROM users WHERE id=?', (g.user_id,)).fetchone()
        negotiator_name = user['full_name']
        negotiator_email = user['email']
        agency_name = user['agency_name'] or ''
    else:
        negotiator_name = data.get('negotiator_name', 'INHOUS')
        negotiator_email = data.get('negotiator_email', '')
        agency_name = data.get('agency_name', 'INHOUS direct')

    c = db.execute('''INSERT INTO offers (
        property_id, submitted_by, agency_name, negotiator_name, amount,
        buyer_full_name, buyer_name_on_contract, buyer_email, buyer_phone, buyer_address,
        buyer_profession, buyer_nationality, buyer_type, reason_for_purchase,
        time_looking, properties_viewed, purchase_method, cash_percent, mortgage_percent,
        financial_provider, proof_of_funds_status, chain_status, property_to_sell,
        proposed_exchange, proposed_completion, competing_properties,
        buyer_solicitor_firm, buyer_solicitor_name, buyer_solicitor_email, buyer_solicitor_phone,
        buyer_aml_status, conditions, valid_from, valid_until, broker_notes, agent_notes,
        inhous_fee, offer_date
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        property_id, g.user_id, agency_name, negotiator_name, amount,
        data['buyer_full_name'], data.get('buyer_name_on_contract'), data.get('buyer_email'),
        data.get('buyer_phone'), data.get('buyer_address'), data.get('buyer_profession'),
        data.get('buyer_nationality'), data.get('buyer_type'), data.get('reason_for_purchase'),
        data.get('time_looking'), data.get('properties_viewed'),
        data.get('purchase_method'), data.get('cash_percent'), data.get('mortgage_percent'),
        data.get('financial_provider'), data.get('proof_of_funds_status','not_requested'),
        data.get('chain_status'), data.get('property_to_sell'),
        data.get('proposed_exchange'), data.get('proposed_completion'),
        data.get('competing_properties'), data.get('buyer_solicitor_firm'),
        data.get('buyer_solicitor_name'), data.get('buyer_solicitor_email'),
        data.get('buyer_solicitor_phone'), data.get('buyer_aml_status','not_started'),
        data.get('conditions'), data.get('valid_from'), data.get('valid_until'),
        data.get('broker_notes') if g.role == 'broker' else None, data.get('agent_notes'),
        data.get('inhous_fee'), data.get('offer_date')
    ))
    offer_id = c.lastrowid
    # Notify broker and vendor
    prop = db.execute('SELECT broker_id, address_line1, currency FROM properties WHERE id=?', (property_id,)).fetchone()
    money = fmt_money(amount, prop['currency'])
    notify(db, prop['broker_id'], property_id, 'offer_received',
           f"New offer — {money} from {agency_name}",
           f"Buyer: {data['buyer_full_name']} · {data.get('purchase_method','').capitalize()}")
    vendor = db.execute("SELECT user_id FROM property_access WHERE property_id=? AND role='vendor'", (property_id,)).fetchone()
    if vendor:
        notify(db, vendor['user_id'], property_id, 'offer_received',
               f"New offer received — {money}",
               f"From {agency_name} · {data.get('purchase_method','').capitalize()} buyer")
    audit(db, property_id, g.user_id, 'offer_submitted', 'offer', offer_id, money)
    db.commit()
    db.close()
    return jsonify({'id': offer_id, 'message': 'Offer submitted successfully'}), 201

@app.route('/api/properties/<int:property_id>/offers/<int:offer_id>/action', methods=['POST'])
@require_role('broker', 'vendor')
def offer_action(property_id, offer_id):
    data = request.get_json()
    action = data.get('action')
    if action not in ('accept','decline','counter'):
        return jsonify({'error': 'Invalid action'}), 400
    db = get_db()
    offer = db.execute('SELECT * FROM offers WHERE id=? AND property_id=?', (offer_id, property_id)).fetchone()
    if not offer:
        db.close()
        return jsonify({'error': 'Offer not found'}), 404
    cur_row = db.execute('SELECT currency FROM properties WHERE id=?', (property_id,)).fetchone()
    currency = cur_row['currency'] if cur_row else 'GBP'
    status_map = {'accept':'accepted','decline':'declined','counter':'countered'}
    updates = {'status': status_map[action]}
    if action == 'accept':
        updates['accepted_at'] = datetime.datetime.utcnow().isoformat()
        # Trigger post-acceptance workflow
        _trigger_acceptance_workflow(db, property_id, offer_id, offer, currency)
        # Update property status
        db.execute("UPDATE properties SET status='under_offer' WHERE id=?", (property_id,))
    elif action == 'decline':
        updates['declined_at'] = datetime.datetime.utcnow().isoformat()
        updates['declined_reason'] = data.get('reason','')
    elif action == 'counter':
        updates['counter_amount'] = data.get('counter_amount')
        updates['counter_notes'] = data.get('counter_notes','')
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE offers SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?',
               list(updates.values()) + [offer_id])
    # Notify the agent who submitted
    notify(db, offer['submitted_by'], property_id, f'offer_{action}d',
           f"Offer {status_map[action]} — {fmt_money(offer['amount'], currency)}",
           data.get('counter_notes') or data.get('reason',''))
    audit(db, property_id, g.user_id, f'offer_{action}d', 'offer', offer_id)
    db.commit()
    db.close()
    return jsonify({'message': f'Offer {action}ed successfully'})

def _trigger_acceptance_workflow(db, property_id, offer_id, offer, currency='GBP'):
    prop = db.execute('SELECT broker_id, address_line1, city FROM properties WHERE id=?', (property_id,)).fetchone()
    accepted = fmt_money(offer['amount'], currency)
    # 1. Buyer solicitor invited (notification to broker to send invite)
    notify(db, prop['broker_id'], property_id, 'action_required',
           'Send invite — buyer solicitor',
           f"Invite {offer['buyer_solicitor_name']} at {offer['buyer_solicitor_firm']} to upload buyer AML")
    # 2. Vendor solicitor notified
    vendor_sol = db.execute("SELECT user_id FROM property_access WHERE property_id=? AND role='vendor_solicitor'", (property_id,)).fetchone()
    if vendor_sol:
        notify(db, vendor_sol['user_id'], property_id, 'offer_accepted',
               'Offer accepted — begin conveyancing preparation',
               f"Accepted offer: {accepted}. Please begin conveyancing prep for {prop['address_line1']}.")
    # 3. Vendor notified
    vendor = db.execute("SELECT user_id FROM property_access WHERE property_id=? AND role='vendor'", (property_id,)).fetchone()
    if vendor:
        notify(db, vendor['user_id'], property_id, 'offer_accepted',
               f"Offer accepted — {accepted}",
               "Your solicitor has been notified to begin conveyancing preparation.")
    # 4. Broker action items
    notify(db, prop['broker_id'], property_id, 'action_required',
           'Contact bank/lender — proof of funds',
           "Request proof of funds from " + (offer['financial_provider'] or "buyer's bank"))
    notify(db, prop['broker_id'], property_id, 'action_required',
           'Send removal company referrals',
           'Trigger removal company quote requests to vendor and buyer')
    notify(db, prop['broker_id'], property_id, 'action_required',
           'Send RICS surveyor referrals to buyer',
           'Send list of recommended surveyors for the buyer to consider')

# ══════════════════════════════════════════════════════════════════════════════
# AML / KYC
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/aml', methods=['GET'])
@require_auth
@require_property_access
def get_aml(property_id):
    db = get_db()
    records = rows_to_list(db.execute(
        'SELECT ar.*, u.full_name as certified_by_name FROM aml_records ar LEFT JOIN users u ON ar.certified_by=u.id WHERE ar.property_id=?',
        (property_id,)
    ).fetchall())
    # Instructed agents can see the VENDOR's AML/KYC (needed to market the property),
    # but never buyer-side AML (that belongs to a specific competing offer).
    if g.role == 'agent':
        records = [r for r in records if r['party_type'] == 'vendor']
    db.close()
    return jsonify(records)

@app.route('/api/properties/<int:property_id>/aml', methods=['POST'])
@require_role('broker', 'vendor_solicitor', 'buyer_solicitor')
def create_aml(property_id):
    data = request.get_json() or {}
    if data.get('party_type') not in ('vendor', 'buyer') or not data.get('person_name'):
        return jsonify({'error': "party_type (must be 'vendor' or 'buyer') and person_name are required"}), 400
    db = get_db()
    c = db.execute('''INSERT INTO aml_records (property_id, party_type, person_name, dob, nationality, status)
                      VALUES (?,?,?,?,?,?)''', (
        property_id, data.get('party_type'), data.get('person_name'),
        data.get('dob'), data.get('nationality'), 'pending'
    ))
    audit(db, property_id, g.user_id, 'aml_created', 'aml', c.lastrowid)
    db.commit()
    db.close()
    return jsonify({'id': c.lastrowid, 'message': 'AML record created'}), 201

@app.route('/api/properties/<int:property_id>/aml/<int:aml_id>/certify', methods=['POST'])
@require_role('broker', 'vendor_solicitor', 'buyer_solicitor')
def certify_aml(property_id, aml_id):
    db = get_db()
    db.execute('UPDATE aml_records SET status=?, certified_by=?, certified_at=CURRENT_TIMESTAMP WHERE id=? AND property_id=?',
               ('certified', g.user_id, aml_id, property_id))
    audit(db, property_id, g.user_id, 'aml_certified', 'aml', aml_id)
    db.commit()
    db.close()
    return jsonify({'message': 'AML certified'})

# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/documents', methods=['GET'])
@require_auth
@require_property_access
def get_documents(property_id):
    db = get_db()
    # Role-based document filtering
    role_visible = {
        'broker': None,  # all
        'vendor': ('photo','floorplan','epc','brochure','memo_of_sale','agent_terms'),
        'agent': ('photo','floorplan','epc','agent_brochure','memo_of_sale','agent_terms','aml_vendor','aml_verification'),
        'vendor_solicitor': ('aml_vendor','aml_verification','title_register','planning','memo_of_sale','epc','proof_of_funds'),
        'buyer_solicitor': ('aml_buyer','aml_verification','title_register','planning','memo_of_sale','epc','proof_of_funds','survey'),
        'buyer': ('memo_of_sale','epc','brochure'),
        'family_office': ('brochure','epc'),
    }
    allowed = role_visible.get(g.role)
    if allowed:
        placeholders = ','.join('?' for _ in allowed)
        # Role-visible doc types OR any document the user uploaded themselves
        # (so an agent/buyer can see their own proof-of-funds / AML uploads back).
        docs = rows_to_list(db.execute(
            f"SELECT d.*, u.full_name as uploaded_by_name FROM documents d LEFT JOIN users u ON d.uploaded_by=u.id WHERE d.property_id=? AND (d.doc_type IN ({placeholders}) OR d.uploaded_by=?) ORDER BY d.created_at DESC",
            (property_id, *allowed, g.user_id)
        ).fetchall())
    else:
        docs = rows_to_list(db.execute(
            'SELECT d.*, u.full_name as uploaded_by_name FROM documents d LEFT JOIN users u ON d.uploaded_by=u.id WHERE d.property_id=? ORDER BY d.created_at DESC',
            (property_id,)
        ).fetchall())
    # Agent isolation: agents never see the master brochure (but keep their own uploads)
    if g.role == 'agent':
        docs = [d for d in docs if not (d['doc_type'] == 'brochure' and d['uploaded_by'] != g.user_id)]
    db.close()
    return jsonify(docs)

@app.route('/api/properties/<int:property_id>/documents', methods=['POST'])
@require_auth
@require_property_access
def upload_document(property_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    doc_type = request.form.get('doc_type', 'other')
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    safe_name = secrets.token_hex(16) + '_' + file.filename.replace(' ','_')
    save_dir = os.path.join(UPLOAD_DIR, doc_type)
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, safe_name)
    file.save(file_path)
    db = get_db()
    c = db.execute('''INSERT INTO documents (property_id, doc_type, filename, original_filename, file_path, uploaded_by, description)
                      VALUES (?,?,?,?,?,?,?)''', (
        property_id, doc_type, safe_name, file.filename,
        file_path, g.user_id, request.form.get('description','')
    ))
    doc_id = c.lastrowid
    audit(db, property_id, g.user_id, 'document_uploaded', 'document', doc_id, file.filename)
    db.commit()
    db.close()
    return jsonify({'id': doc_id, 'message': 'Document uploaded'}), 201

@app.route('/api/properties/<int:property_id>/documents/<int:doc_id>/download', methods=['GET'])
@require_auth
@require_property_access
def download_document(property_id, doc_id):
    db = get_db()
    doc = db.execute('SELECT * FROM documents WHERE id=? AND property_id=?', (doc_id, property_id)).fetchone()
    db.close()
    if not doc:
        return jsonify({'error': 'Document not found'}), 404
    if not doc['file_path'] or not os.path.exists(doc['file_path']):
        return jsonify({'error': 'File not found on server'}), 404
    return send_file(doc['file_path'], as_attachment=True, download_name=doc['original_filename'] or doc['filename'])

# ── DOCUMENT SHARING (secure links to outside parties) ────────────────────────
SHARE_PARTY_TYPES = ('estate_agent', 'solicitor', 'mortgage_advisor', 'insurance',
                     'surveyor', 'accountant', 'other')

@app.route('/api/properties/<int:property_id>/documents/<int:doc_id>/share', methods=['POST'])
@require_auth
@require_property_access
def share_document(property_id, doc_id):
    if g.role not in ('broker', 'vendor', 'vendor_solicitor', 'buyer_solicitor'):
        return jsonify({'error': 'You do not have permission to share documents'}), 403
    data = request.get_json() or {}
    db = get_db()
    doc = db.execute('SELECT id FROM documents WHERE id=? AND property_id=?', (doc_id, property_id)).fetchone()
    if not doc:
        db.close()
        return jsonify({'error': 'Document not found'}), 404
    party_type = data.get('party_type') if data.get('party_type') in SHARE_PARTY_TYPES else 'other'
    try:
        days = int(data.get('expires_days', 30))
    except (TypeError, ValueError):
        days = 30
    expires = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() if days and days > 0 else None
    token = secrets.token_urlsafe(32)
    c = db.execute('''INSERT INTO document_shares
        (document_id, property_id, token, party_type, recipient_name, recipient_email, created_by, expires_at)
        VALUES (?,?,?,?,?,?,?,?)''',
        (doc_id, property_id, token, party_type, data.get('recipient_name'),
         data.get('recipient_email'), g.user_id, expires))
    audit(db, property_id, g.user_id, 'document_shared', 'document', doc_id,
          f"{party_type}:{data.get('recipient_email') or ''}")
    db.commit()
    db.close()
    return jsonify({'id': c.lastrowid, 'token': token,
                    'share_path': f'/api/shared-documents/{token}/download',
                    'expires_at': expires}), 201

@app.route('/api/properties/<int:property_id>/documents/<int:doc_id>/shares', methods=['GET'])
@require_role('broker')
def list_document_shares(property_id, doc_id):
    db = get_db()
    rows = rows_to_list(db.execute(
        '''SELECT id, party_type, recipient_name, recipient_email, created_at,
                  expires_at, revoked, access_count, last_accessed_at, token
           FROM document_shares WHERE document_id=? AND property_id=? ORDER BY created_at DESC''',
        (doc_id, property_id)).fetchall())
    db.close()
    return jsonify(rows)

@app.route('/api/shares/<int:share_id>/revoke', methods=['POST'])
@require_role('broker')
def revoke_share(share_id):
    db = get_db()
    db.execute('UPDATE document_shares SET revoked=1 WHERE id=?', (share_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Share link revoked'})

def _valid_share(row):
    if not row or row['revoked']:
        return False, ('This share link is invalid or has been revoked', 404)
    if row['expires_at'] and row['expires_at'] < datetime.datetime.utcnow().isoformat():
        return False, ('This share link has expired', 410)
    return True, None

@app.route('/api/shared-documents/<token>', methods=['GET'])
def shared_document_meta(token):
    """Public: metadata for a shared document (no login required)."""
    db = get_db()
    row = db.execute('''SELECT s.*, d.original_filename, d.doc_type, p.address_line1, p.city
                        FROM document_shares s JOIN documents d ON s.document_id=d.id
                        JOIN properties p ON s.property_id=p.id WHERE s.token=?''', (token,)).fetchone()
    db.close()
    ok, err = _valid_share(row)
    if not ok:
        return jsonify({'error': err[0]}), err[1]
    return jsonify({
        'filename': row['original_filename'], 'doc_type': row['doc_type'],
        'property': f"{row['address_line1']}, {row['city']}",
        'recipient_name': row['recipient_name'], 'expires_at': row['expires_at'],
        'download_url': f'/api/shared-documents/{token}/download'})

@app.route('/api/shared-documents/<token>/download', methods=['GET'])
def shared_document_download(token):
    """Public: download a shared document (no login required)."""
    db = get_db()
    row = db.execute('''SELECT s.*, d.file_path, d.original_filename, d.filename
                        FROM document_shares s JOIN documents d ON s.document_id=d.id
                        WHERE s.token=?''', (token,)).fetchone()
    ok, err = _valid_share(row)
    if not ok:
        db.close()
        return jsonify({'error': err[0]}), err[1]
    db.execute('UPDATE document_shares SET access_count=access_count+1, last_accessed_at=CURRENT_TIMESTAMP WHERE id=?', (row['id'],))
    db.commit()
    db.close()
    if not row['file_path'] or not os.path.exists(row['file_path']):
        return jsonify({'error': 'File not found on server'}), 404
    return send_file(row['file_path'], as_attachment=True, download_name=row['original_filename'] or row['filename'])

# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/notifications', methods=['GET'])
@require_auth
def get_notifications():
    db = get_db()
    notifs = rows_to_list(db.execute(
        'SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50',
        (g.user_id,)
    ).fetchall())
    db.close()
    return jsonify(notifs)

@app.route('/api/notifications/mark-read', methods=['POST'])
@require_auth
def mark_notifications_read():
    db = get_db()
    db.execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (g.user_id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Notifications marked as read'})

# ══════════════════════════════════════════════════════════════════════════════
# USERS (admin)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/users', methods=['POST'])
@require_role('broker')
def create_user():
    data = request.get_json()
    required = ['email','password','full_name','role']
    for f in required:
        if not data.get(f):
            return jsonify({'error': f'{f} is required'}), 400
    if len(data['password']) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE email=?', (data['email'].lower(),)).fetchone()
    if existing:
        db.close()
        return jsonify({'error': 'Email already registered'}), 400
    c = db.execute(
        'INSERT INTO users (email,password_hash,full_name,role,agency_name,phone) VALUES (?,?,?,?,?,?)',
        (data['email'].lower(), hash_password(data['password']), data['full_name'],
         data['role'], data.get('agency_name'), data.get('phone'))
    )
    audit(db, None, g.user_id, 'user_created', 'user', c.lastrowid, data['email'])
    db.commit()
    db.close()
    return jsonify({'id': c.lastrowid, 'message': 'User created'}), 201

@app.route('/api/properties/<int:property_id>/access', methods=['GET'])
@require_role('broker')
def get_property_access(property_id):
    db = get_db()
    access = rows_to_list(db.execute('''
        SELECT pa.*, u.full_name, u.email, u.agency_name, u.phone
        FROM property_access pa JOIN users u ON pa.user_id=u.id
        WHERE pa.property_id=? ORDER BY pa.role, u.full_name
    ''', (property_id,)).fetchall())
    db.close()
    return jsonify(access)

@app.route('/api/properties/<int:property_id>/participants', methods=['GET'])
@require_auth
@require_property_access
def get_participants(property_id):
    """Everyone involved in the transaction. INHOUS (broker) sees full contact
    details; external parties see names / firms only."""
    is_broker = (g.role == 'broker')
    db = get_db()
    rows = db.execute('''
        SELECT u.id, u.full_name, pa.role AS role, u.agency_name, u.email, u.phone
        FROM property_access pa JOIN users u ON pa.user_id=u.id
        WHERE pa.property_id=? ORDER BY pa.role, u.full_name
    ''', (property_id,)).fetchall()
    people = []
    seen = set()
    # The managing INHOUS broker first
    bk = db.execute('SELECT u.full_name, u.agency_name, u.email, u.phone FROM properties p JOIN users u ON p.broker_id=u.id WHERE p.id=?', (property_id,)).fetchone()
    if bk:
        b = {'full_name': bk['full_name'], 'role': 'broker', 'agency_name': bk['agency_name'] or 'INHOUS'}
        if is_broker: b['email'] = bk['email']; b['phone'] = bk['phone']
        people.append(b); seen.add((bk['full_name'], 'broker'))
    for r in rows:
        if (r['full_name'], r['role']) in seen:
            continue
        seen.add((r['full_name'], r['role']))
        p = {'full_name': r['full_name'], 'role': r['role'], 'agency_name': r['agency_name']}
        if is_broker: p['email'] = r['email']; p['phone'] = r['phone']
        people.append(p)
    # Third-party services engaged on this property (via a referral event)
    tp_rows = db.execute('''
        SELECT DISTINCT rp.company_name, rp.category, rp.contact_name, rp.contact_email, rp.contact_phone
        FROM referral_events re JOIN referral_partners rp ON re.partner_id=rp.id
        WHERE re.property_id=? ORDER BY rp.category, rp.company_name
    ''', (property_id,)).fetchall()
    third_parties = []
    for r in tp_rows:
        tp = {'company_name': r['company_name'], 'category': r['category']}
        if is_broker:
            tp['contact_name'] = r['contact_name']; tp['contact_email'] = r['contact_email']; tp['contact_phone'] = r['contact_phone']
        third_parties.append(tp)
    db.close()
    return jsonify({'is_broker': is_broker, 'people': people, 'third_parties': third_parties})

# ══════════════════════════════════════════════════════════════════════════════
# VALUATIONS (pre-instruction)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/properties/<int:property_id>/valuations', methods=['GET'])
@require_auth
@require_property_access
def get_valuations(property_id):
    db = get_db()
    if g.role in ('broker', 'vendor'):
        rows = rows_to_list(db.execute(
            'SELECT * FROM valuations WHERE property_id=? ORDER BY valuation_amount DESC', (property_id,)).fetchall())
    else:
        # agents see only their own valuation
        rows = rows_to_list(db.execute(
            'SELECT * FROM valuations WHERE property_id=? AND submitted_by=?', (property_id, g.user_id)).fetchall())
    db.close()
    return jsonify(rows)

@app.route('/api/properties/<int:property_id>/valuations', methods=['POST'])
@require_auth
@require_property_access
def submit_valuation(property_id):
    data = request.get_json() or {}
    amount = to_int_or_none(data.get('valuation_amount'))
    if amount is None:
        return jsonify({'error': 'Valuation amount is required'}), 400
    db = get_db()
    if g.role == 'agent':
        u = db.execute('SELECT full_name, agency_name FROM users WHERE id=?', (g.user_id,)).fetchone()
        agency = u['agency_name'] or data.get('agency_name', '')
        negotiator = u['full_name']
    else:
        agency = data.get('agency_name', 'INHOUS')
        negotiator = data.get('negotiator_name', '')
    c = db.execute('''INSERT INTO valuations
        (property_id, submitted_by, agency_name, negotiator_name, valuation_amount,
         suggested_asking_price, recommended_fee, estimated_timeframe, marketing_strategy, comments)
        VALUES (?,?,?,?,?,?,?,?,?,?)''', (
        property_id, g.user_id, agency, negotiator, amount,
        to_int_or_none(data.get('suggested_asking_price')), data.get('recommended_fee'),
        data.get('estimated_timeframe'), data.get('marketing_strategy'), data.get('comments')))
    prop = db.execute('SELECT broker_id, currency FROM properties WHERE id=?', (property_id,)).fetchone()
    notify(db, prop['broker_id'], property_id, 'valuation_received',
           f"Valuation received — {agency}", fmt_money(amount, prop['currency']))
    audit(db, property_id, g.user_id, 'valuation_submitted', 'valuation', c.lastrowid)
    db.commit()
    db.close()
    return jsonify({'id': c.lastrowid, 'message': 'Valuation submitted'}), 201

# ══════════════════════════════════════════════════════════════════════════════
# HEALTH + SEED DATA
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'version': '1.0.0', 'platform': 'INHOUS'})

@app.route('/api/seed', methods=['POST'])
def seed():
    """Create demo data for testing — remove in production"""
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email='david@inhous.com'").fetchone()
    if existing:
        db.close()
        return jsonify({'message': 'Already seeded'})
    # Create broker
    c = db.execute("INSERT INTO users (email,password_hash,full_name,role) VALUES (?,?,?,?)",
                   ('david@inhous.com', hash_password('inhous2026'), 'David Johnson', 'broker'))
    broker_id = c.lastrowid
    # Create demo property
    c2 = db.execute('''INSERT INTO properties (address_line1,city,postcode,tenure,guide_price,bedrooms,floor_area_sqft,year_built,epc_rating,sale_mode,broker_id,status)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('32 Mapesbury Road','London','NW2 4JD','Freehold',5850000,6,5278,1895,'C','managed',broker_id,'photography_pending'))
    prop_id = c2.lastrowid
    db.execute('INSERT INTO price_log (property_id,price,event_type,logged_by) VALUES (?,?,?,?)',
               (prop_id, 5850000, 'launch', broker_id))
    db.execute('INSERT INTO photography_bookings (property_id,booking_type) VALUES (?,?)', (prop_id,'photography'))
    db.execute('INSERT INTO photography_bookings (property_id,booking_type) VALUES (?,?)', (prop_id,'floorplan'))
    for dow, mode in [(0,'instant'),(1,'instant'),(2,'instant'),(3,'instant'),(4,'instant'),(5,'blocked'),(6,'blocked')]:
        db.execute('INSERT OR IGNORE INTO viewing_availability (property_id,day_of_week,mode) VALUES (?,?,?)', (prop_id,dow,mode))
    # Create vendor
    c3 = db.execute("INSERT INTO users (email,password_hash,full_name,role,phone) VALUES (?,?,?,?,?)",
                    ('james.kermisch@email.com', hash_password('vendor2026'), 'James Kermisch', 'vendor', '+44 7700 900123'))
    vendor_id = c3.lastrowid
    db.execute('INSERT INTO property_access (property_id,user_id,role,accepted_at,invited_by) VALUES (?,?,?,CURRENT_TIMESTAMP,?)',
               (prop_id, vendor_id, 'vendor', broker_id))
    db.commit()
    db.close()
    return jsonify({
        'message': 'Demo data created',
        'credentials': {
            'broker': {'email': 'david@inhous.com', 'password': 'inhous2026'},
            'vendor': {'email': 'james.kermisch@email.com', 'password': 'vendor2026'},
        },
        'property_id': prop_id
    })

# ── SERVE FRONTEND ────────────────────────────────────────────────────────────
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    base = os.path.dirname(os.path.abspath(__file__))
    if path and os.path.exists(os.path.join(base, path)):
        return send_from_directory(base, path)
    index = os.path.join(base, 'index.html')
    if os.path.exists(index):
        return send_file(index)
    return jsonify({'message': 'INHOUS Platform API v1.0'}), 200

if __name__ == '__main__':
    init_db()
    print("INHOUS Platform starting on http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)


# ══════════════════════════════════════════════════════════════════════════════
# REFERRAL PARTNERS & DISCLOSURES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/referral-partners', methods=['GET'])
@require_auth
def get_referral_partners():
    category = request.args.get('category')
    db = get_db()
    if category:
        partners = rows_to_list(db.execute(
            'SELECT * FROM referral_partners WHERE category=? AND is_active=1 ORDER BY sort_order',
            (category,)
        ).fetchall())
    else:
        partners = rows_to_list(db.execute(
            'SELECT * FROM referral_partners WHERE is_active=1 ORDER BY category, sort_order'
        ).fetchall())
    # Non-brokers don't see fee amounts or internal notes — disclosure text only
    if g.role != 'broker':
        for p in partners:
            p.pop('referral_fee_amount', None)
            p.pop('referral_fee_type', None)
            p.pop('referral_fee_notes', None)
    db.close()
    return jsonify(partners)

@app.route('/api/referral-partners', methods=['POST'])
@require_role('broker')
def create_referral_partner():
    data = request.get_json()
    if not data.get('company_name') or not data.get('category'):
        return jsonify({'error': 'Company name and category required'}), 400
    db = get_db()
    c = db.execute('''INSERT INTO referral_partners
        (category, company_name, contact_name, contact_email, contact_phone, website_url,
         referral_fee_type, referral_fee_amount, referral_fee_notes, disclosure_text, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
        data['category'], data['company_name'], data.get('contact_name'),
        data.get('contact_email'), data.get('contact_phone'), data.get('website_url'),
        data.get('referral_fee_type', 'none'), data.get('referral_fee_amount'),
        data.get('referral_fee_notes'), data.get('disclosure_text'), data.get('notes')
    ))
    audit(db, None, g.user_id, 'referral_partner_created', 'referral_partner', c.lastrowid)
    db.commit()
    db.close()
    return jsonify({'id': c.lastrowid, 'message': 'Partner added'}), 201

@app.route('/api/referral-partners/<int:partner_id>', methods=['PATCH'])
@require_role('broker')
def update_referral_partner(partner_id):
    data = request.get_json()
    allowed = ['company_name','contact_name','contact_email','contact_phone','website_url',
               'referral_fee_type','referral_fee_amount','referral_fee_notes',
               'disclosure_text','notes','is_active','sort_order']
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'Nothing to update'}), 400
    db = get_db()
    set_clause = ', '.join(f'{k}=?' for k in updates)
    db.execute(f'UPDATE referral_partners SET {set_clause} WHERE id=?', list(updates.values()) + [partner_id])
    audit(db, None, g.user_id, 'referral_partner_updated', 'referral_partner', partner_id)
    db.commit()
    db.close()
    return jsonify({'message': 'Partner updated'})

@app.route('/api/properties/<int:property_id>/referrals/acknowledge', methods=['POST'])
@require_auth
@require_property_access
def acknowledge_disclosure(property_id):
    """Buyer acknowledges referral fee disclosure before clicking through"""
    data = request.get_json()
    category = data.get('category')
    partner_id = data.get('partner_id')
    if not category:
        return jsonify({'error': 'Category required'}), 400
    db = get_db()
    # Check if already acknowledged for this category/property
    existing = db.execute(
        'SELECT id FROM referral_disclosures WHERE property_id=? AND user_id=? AND category=? AND partner_id=? AND acknowledged_at IS NOT NULL',
        (property_id, g.user_id, category, partner_id)
    ).fetchone()
    if existing:
        db.close()
        return jsonify({'message': 'Already acknowledged', 'already_done': True})
    db.execute('''INSERT INTO referral_disclosures
        (property_id, user_id, category, partner_id, acknowledged_at)
        VALUES (?,?,?,?,CURRENT_TIMESTAMP)''',
        (property_id, g.user_id, category, partner_id))
    # Log referral event
    db.execute('''INSERT INTO referral_events (property_id, user_id, partner_id, event_type)
                  VALUES (?,?,?,?)''', (property_id, g.user_id, partner_id, 'clicked'))
    audit(db, property_id, g.user_id, 'referral_disclosure_acknowledged', 'referral', partner_id,
          f'{category}:{partner_id}')
    db.commit()
    db.close()
    return jsonify({'message': 'Disclosure acknowledged — proceeding to partner', 'acknowledged': True})

@app.route('/api/properties/<int:property_id>/referrals/convert', methods=['POST'])
@require_role('broker')
def log_referral_conversion(property_id):
    """Broker logs when a referral results in a completed booking/policy"""
    data = request.get_json()
    partner_id = data.get('partner_id')
    db = get_db()
    partner = db.execute('SELECT * FROM referral_partners WHERE id=?', (partner_id,)).fetchone()
    if not partner:
        db.close()
        return jsonify({'error': 'Partner not found'}), 404
    fee = data.get('fee_earned') or partner['referral_fee_amount']
    db.execute('''INSERT INTO referral_events (property_id, user_id, partner_id, event_type, fee_earned, notes)
                  VALUES (?,?,?,?,?,?)''',
        (property_id, g.user_id, partner_id, 'converted', fee, data.get('notes','')))
    audit(db, property_id, g.user_id, 'referral_converted', 'referral', partner_id,
          f'fee={fee}')
    db.commit()
    db.close()
    return jsonify({'message': 'Conversion logged', 'fee_earned': fee})

@app.route('/api/referrals/summary', methods=['GET'])
@require_role('broker')
def referral_summary():
    """Summary of all referral activity and fees earned"""
    db = get_db()
    by_partner = rows_to_list(db.execute('''
        SELECT rp.company_name, rp.category, rp.referral_fee_type, rp.referral_fee_amount,
               COUNT(CASE WHEN re.event_type='clicked' THEN 1 END) as clicks,
               COUNT(CASE WHEN re.event_type='converted' THEN 1 END) as conversions,
               COALESCE(SUM(CASE WHEN re.event_type='converted' THEN re.fee_earned END), 0) as total_fees_earned
        FROM referral_partners rp
        LEFT JOIN referral_events re ON re.partner_id=rp.id
        WHERE rp.is_active=1
        GROUP BY rp.id
        ORDER BY rp.category, total_fees_earned DESC
    ''').fetchall())
    total_earned = sum(r['total_fees_earned'] or 0 for r in by_partner)
    db.close()
    return jsonify({'partners': by_partner, 'total_fees_earned': total_earned})
