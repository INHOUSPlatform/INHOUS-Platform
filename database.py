import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'inhous.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # ── USERS ─────────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        agency_name TEXT,
        phone TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME,
        is_active INTEGER DEFAULT 1,
        two_factor_enabled INTEGER DEFAULT 0
    )''')

    # ── PROPERTIES ────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address_line1 TEXT NOT NULL,
        address_line2 TEXT,
        city TEXT NOT NULL,
        postcode TEXT NOT NULL,
        country TEXT DEFAULT 'United Kingdom',
        state_region TEXT,
        tenure TEXT CHECK(tenure IN ('Freehold','Leasehold','Share of Freehold')),
        guide_price INTEGER,
        currency TEXT DEFAULT 'GBP',
        bedrooms INTEGER,
        floor_area_sqft INTEGER,
        year_built INTEGER,
        epc_rating TEXT,
        epc_cert_number TEXT,
        epc_valid_until DATE,
        sale_mode TEXT NOT NULL DEFAULT 'managed' CHECK(sale_mode IN ('direct','managed')),
        status TEXT NOT NULL DEFAULT 'onboarding' CHECK(status IN (
            'onboarding','photography_pending','photography_booked',
            'photography_review','active','under_offer','sold','withdrawn'
        )),
        broker_id INTEGER REFERENCES users(id),
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── PROPERTY ACCESS (links users to properties with role) ─────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS property_access (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        role TEXT NOT NULL,
        access_level TEXT DEFAULT 'full',
        invited_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        accepted_at DATETIME,
        invited_by INTEGER REFERENCES users(id),
        UNIQUE(property_id, user_id)
    )''')

    # ── INVITES ───────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER REFERENCES properties(id),
        email TEXT NOT NULL,
        role TEXT NOT NULL,
        token TEXT UNIQUE NOT NULL,
        invited_by INTEGER REFERENCES users(id),
        agency_name TEXT,
        message TEXT,
        expires_at DATETIME NOT NULL,
        used_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── PRICE LOG ─────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS price_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        price INTEGER NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN (
            'launch','conversation','reduction','increase','offer_agreed'
        )),
        notes TEXT,
        logged_by INTEGER REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── PHOTOGRAPHY BOOKINGS ──────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS photography_bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        booking_type TEXT NOT NULL CHECK(booking_type IN ('photography','floorplan','both')),
        preferred_date DATE,
        preferred_time TEXT,
        photographer_firm TEXT,
        photographer_contact TEXT,
        photographer_email TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN (
            'pending','date_selected','confirmed','completed','cancelled'
        )),
        vendor_notes TEXT,
        broker_brief TEXT,
        shoot_date DATE,
        shoot_time TEXT,
        confirmed_at DATETIME,
        completed_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── DOCUMENTS ─────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        doc_type TEXT NOT NULL CHECK(doc_type IN (
            'photo','floorplan','epc','brochure','agent_brochure',
            'aml_vendor','aml_buyer','aml_verification',
            'title_register','planning','proof_of_funds',
            'agent_terms','data_handling_declaration',
            'memo_of_sale','offer_form','survey','other'
        )),
        filename TEXT NOT NULL,
        original_filename TEXT,
        file_path TEXT NOT NULL,
        file_size INTEGER,
        mime_type TEXT,
        status TEXT DEFAULT 'pending' CHECK(status IN (
            'pending','approved','rejected','archived'
        )),
        uploaded_by INTEGER REFERENCES users(id),
        approved_by INTEGER REFERENCES users(id),
        approved_at DATETIME,
        description TEXT,
        version INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── DOCUMENT ACCESS LOG ───────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS document_access_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES documents(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        action TEXT NOT NULL CHECK(action IN ('view','download','sign')),
        ip_address TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── AML / KYC ─────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS aml_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        party_type TEXT NOT NULL CHECK(party_type IN ('vendor','buyer')),
        person_name TEXT NOT NULL,
        dob DATE,
        nationality TEXT,
        ssid TEXT,
        verification_provider TEXT,
        verification_date DATE,
        verification_result TEXT CHECK(verification_result IN ('pass','fail','pending','not_run')),
        certified_by INTEGER REFERENCES users(id),
        certified_at DATETIME,
        status TEXT DEFAULT 'pending' CHECK(status IN (
            'pending','documents_uploaded','certified','failed'
        )),
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── VIEWING AVAILABILITY ──────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS viewing_availability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        day_of_week INTEGER,
        specific_date DATE,
        mode TEXT NOT NULL DEFAULT 'instant' CHECK(mode IN ('instant','confirm','blocked')),
        viewing_duration_mins INTEGER DEFAULT 45,
        buffer_mins INTEGER DEFAULT 60,
        max_per_day INTEGER DEFAULT 4,
        earliest_start TEXT DEFAULT '09:00',
        latest_start TEXT DEFAULT '16:00',
        min_notice_hours INTEGER DEFAULT 4,
        UNIQUE(property_id, day_of_week),
        UNIQUE(property_id, specific_date)
    )''')

    # ── VIEWING REQUESTS ──────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS viewing_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        requested_by INTEGER NOT NULL REFERENCES users(id),
        agency_name TEXT NOT NULL,
        negotiator_name TEXT NOT NULL,
        negotiator_email TEXT,
        negotiator_phone TEXT,
        buyer_reference TEXT,
        buyer_notes TEXT,
        requested_date DATE NOT NULL,
        requested_time TEXT NOT NULL,
        slot_end_time TEXT,
        booking_mode TEXT NOT NULL CHECK(booking_mode IN ('instant','confirm')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
            'pending','confirmed','declined','cancelled_agent',
            'cancelled_vendor','completed','no_show'
        )),
        confirmed_by INTEGER REFERENCES users(id),
        confirmed_at DATETIME,
        declined_reason TEXT,
        feedback_sent_at DATETIME,
        feedback_submitted_at DATETIME,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(property_id, requested_date, requested_time)
    )''')

    # ── VIEWING FEEDBACK ──────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS viewing_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        viewing_id INTEGER NOT NULL REFERENCES viewing_requests(id),
        property_id INTEGER NOT NULL REFERENCES properties(id),
        submitted_by INTEGER REFERENCES users(id),
        interest_level TEXT CHECK(interest_level IN ('hot','warm','cold','not_proceeding')),
        buyer_type TEXT,
        chain_status TEXT,
        budget_range TEXT,
        objections TEXT,
        competing_properties TEXT,
        follow_up_likelihood TEXT,
        comments TEXT,
        audio_path TEXT,
        audio_filename TEXT,
        broker_note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── OFFERS ────────────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        submitted_by INTEGER NOT NULL REFERENCES users(id),
        agency_name TEXT,
        negotiator_name TEXT,
        amount INTEGER NOT NULL,
        buyer_full_name TEXT NOT NULL,
        buyer_name_on_contract TEXT,
        buyer_email TEXT,
        buyer_phone TEXT,
        buyer_address TEXT,
        buyer_profession TEXT,
        buyer_nationality TEXT,
        buyer_type TEXT,
        reason_for_purchase TEXT,
        time_looking TEXT,
        properties_viewed INTEGER,
        purchase_method TEXT CHECK(purchase_method IN ('cash','mortgage','part')),
        cash_percent INTEGER,
        mortgage_percent INTEGER,
        financial_provider TEXT,
        proof_of_funds_status TEXT DEFAULT 'not_requested' CHECK(proof_of_funds_status IN (
            'not_requested','requested','received','confirmed'
        )),
        chain_status TEXT,
        property_to_sell TEXT,
        proposed_exchange DATE,
        proposed_completion DATE,
        competing_properties TEXT,
        buyer_solicitor_firm TEXT,
        buyer_solicitor_name TEXT,
        buyer_solicitor_email TEXT,
        buyer_solicitor_phone TEXT,
        buyer_aml_status TEXT DEFAULT 'not_started' CHECK(buyer_aml_status IN (
            'not_started','uploaded','certified','failed'
        )),
        conditions TEXT,
        valid_from DATE,
        valid_until DATE,
        broker_notes TEXT,
        agent_notes TEXT,
        inhous_fee TEXT,
        offer_date TEXT,
        status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN (
            'submitted','under_review','countered','accepted','declined','withdrawn'
        )),
        counter_amount INTEGER,
        counter_notes TEXT,
        accepted_at DATETIME,
        declined_at DATETIME,
        declined_reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── NOTIFICATIONS ─────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        property_id INTEGER REFERENCES properties(id),
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        action_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── AUDIT LOG (append-only) ───────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER REFERENCES properties(id),
        user_id INTEGER REFERENCES users(id),
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        detail TEXT,
        ip_address TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── DOCUMENT SHARES (secure links to outside parties) ─────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS document_shares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES documents(id),
        property_id INTEGER NOT NULL REFERENCES properties(id),
        token TEXT UNIQUE NOT NULL,
        party_type TEXT,
        recipient_name TEXT,
        recipient_email TEXT,
        created_by INTEGER REFERENCES users(id),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME,
        revoked INTEGER DEFAULT 0,
        access_count INTEGER DEFAULT 0,
        last_accessed_at DATETIME
    )''')

    # ── BROCHURES (one per property; assembled from photos + details) ─────────
    c.execute('''CREATE TABLE IF NOT EXISTS brochures (
        property_id INTEGER PRIMARY KEY REFERENCES properties(id),
        headline TEXT,
        summary TEXT,
        highlights TEXT,
        hero_doc_id INTEGER,
        updated_by INTEGER REFERENCES users(id),
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── VALUATIONS (pre-instruction valuations from agents) ───────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS valuations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        submitted_by INTEGER REFERENCES users(id),
        agency_name TEXT,
        negotiator_name TEXT,
        valuation_amount INTEGER,
        suggested_asking_price INTEGER,
        recommended_fee TEXT,
        estimated_timeframe TEXT,
        marketing_strategy TEXT,
        comments TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── Schema migrations: add new columns to pre-existing tables (idempotent) ──
    migrations = {
        'properties': [("state_region", "TEXT"), ("currency", "TEXT DEFAULT 'GBP'")],
        'offers': [("inhous_fee", "TEXT"), ("offer_date", "TEXT")],
        'viewing_feedback': [("audio_path", "TEXT"), ("audio_filename", "TEXT")],
    }
    for table, cols in migrations.items():
        for col, ddl in cols:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass  # column already exists

    conn.commit()
    conn.close()
    print("Database initialised successfully")

def relax_user_roles():
    """Drop the hard-coded users.role CHECK on pre-existing databases so new roles
    (e.g. photographer) are permitted. Runs outside a transaction so the temporary
    foreign_keys=OFF actually takes effect during the table rebuild."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if row and row[0] and "role IN (" in row[0]:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript('''
            BEGIN;
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                agency_name TEXT,
                phone TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME,
                is_active INTEGER DEFAULT 1,
                two_factor_enabled INTEGER DEFAULT 0
            );
            INSERT INTO users_new (id,email,password_hash,full_name,role,agency_name,phone,created_at,last_login,is_active,two_factor_enabled)
                SELECT id,email,password_hash,full_name,role,agency_name,phone,created_at,last_login,is_active,two_factor_enabled FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
            COMMIT;
        ''')
        conn.execute("PRAGMA foreign_keys=ON")
        print("Relaxed users.role constraint (new roles allowed)")
    conn.close()

def audit(conn, property_id, user_id, action, entity_type=None, entity_id=None, detail=None):
    conn.execute('''INSERT INTO audit_log 
        (property_id, user_id, action, entity_type, entity_id, detail)
        VALUES (?,?,?,?,?,?)''',
        (property_id, user_id, action, entity_type, entity_id, detail))

if __name__ == '__main__':
    init_db()


def add_referral_tables():
    """Add referral fee and third-party partner tables"""
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS referral_partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        company_name TEXT NOT NULL,
        contact_name TEXT,
        contact_email TEXT,
        contact_phone TEXT,
        website_url TEXT,
        referral_fee_type TEXT CHECK(referral_fee_type IN ('fixed','percentage','none')),
        referral_fee_amount REAL,
        referral_fee_notes TEXT,
        disclosure_text TEXT,
        is_active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS referral_disclosures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        category TEXT NOT NULL,
        partner_id INTEGER REFERENCES referral_partners(id),
        disclosure_shown_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        acknowledged_at DATETIME,
        proceeded INTEGER DEFAULT 0,
        ip_address TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS referral_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER NOT NULL REFERENCES properties(id),
        user_id INTEGER REFERENCES users(id),
        partner_id INTEGER NOT NULL REFERENCES referral_partners(id),
        event_type TEXT NOT NULL CHECK(event_type IN ('sent','clicked','quoted','converted')),
        fee_earned REAL,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # Migration: drop the restrictive category CHECK on pre-existing DBs so new
    # introduction categories (interior_designer, builder, cleaning, …) are allowed.
    row = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='referral_partners'").fetchone()
    if row and row[0] and "category IN ('insurance'" in row[0]:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute('''CREATE TABLE referral_partners_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            company_name TEXT NOT NULL,
            contact_name TEXT, contact_email TEXT, contact_phone TEXT, website_url TEXT,
            referral_fee_type TEXT CHECK(referral_fee_type IN ('fixed','percentage','none')),
            referral_fee_amount REAL, referral_fee_notes TEXT, disclosure_text TEXT,
            is_active INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0, notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''INSERT INTO referral_partners_new
            (id,category,company_name,contact_name,contact_email,contact_phone,website_url,
             referral_fee_type,referral_fee_amount,referral_fee_notes,disclosure_text,
             is_active,sort_order,notes,created_at)
            SELECT id,category,company_name,contact_name,contact_email,contact_phone,website_url,
             referral_fee_type,referral_fee_amount,referral_fee_notes,disclosure_text,
             is_active,sort_order,notes,created_at FROM referral_partners''')
        c.execute("DROP TABLE referral_partners")
        c.execute("ALTER TABLE referral_partners_new RENAME TO referral_partners")
        c.execute("PRAGMA foreign_keys=ON")

    # Seed default partners
    existing = c.execute("SELECT id FROM referral_partners LIMIT 1").fetchone()
    if not existing:
        partners = [
            # Insurance
            ('insurance','Hiscox','High-value home specialists','percentage',15.0,'15% of first year premium','INHOUS may receive a referral fee of up to 15% of your first year\'s premium if you take out a policy with Hiscox. This does not affect the price you pay.'),
            ('insurance','AXA','Comprehensive buildings cover','percentage',12.0,'12% of first year premium','INHOUS may receive a referral fee of up to 12% of your first year\'s premium if you take out a policy with AXA. This does not affect the price you pay.'),
            ('insurance','Aviva','Flexible buildings and contents cover','percentage',12.0,'12% of first year premium','INHOUS may receive a referral fee of up to 12% of your first year\'s premium if you take out a policy with Aviva. This does not affect the price you pay.'),
            ('insurance','Zurich','Specialist period property cover','percentage',12.0,'12% of first year premium','INHOUS may receive a referral fee of up to 12% of your first year\'s premium if you take out a policy with Zurich. This does not affect the price you pay.'),
            # Removal companies
            ('removal','Bishops Move','Full-service removals and storage','fixed',100.0,'£100 per completed move','INHOUS receives a fixed referral fee of £100 from Bishops Move for each completed removal booking made through this introduction. This does not affect the price you are quoted.'),
            ('removal','Pickfords','UK and international removals','fixed',100.0,'£100 per completed move','INHOUS receives a fixed referral fee of £100 from Pickfords for each completed removal booking made through this introduction. This does not affect the price you are quoted.'),
            ('removal','Gentlemen Movers','Specialist high-value property removals','fixed',125.0,'£125 per completed move','INHOUS receives a fixed referral fee of £125 from Gentlemen Movers for each completed removal booking made through this introduction. This does not affect the price you are quoted.'),
            # Surveyors
            ('surveyor','Carter Walsh Surveyors','RICS Level 2 and 3 surveys','fixed',75.0,'£75 per completed survey','INHOUS receives a fixed referral fee of £75 from Carter Walsh Surveyors for each completed survey booked through this introduction. This does not affect the price you are quoted.'),
            ('surveyor','Knight Frank Surveying','Residential valuations and surveys','fixed',75.0,'£75 per completed survey','INHOUS receives a fixed referral fee of £75 from Knight Frank Surveying for each completed survey booked through this introduction. This does not affect the price you are quoted.'),
        ]
        for i, (cat, name, notes, fee_type, fee_amt, fee_notes, disc) in enumerate(partners):
            c.execute('''INSERT INTO referral_partners 
                (category, company_name, notes, referral_fee_type, referral_fee_amount, 
                 referral_fee_notes, disclosure_text, sort_order)
                VALUES (?,?,?,?,?,?,?,?)''',
                (cat, name, notes, fee_type, fee_amt, fee_notes, disc, i))

    # Idempotent seed of third-party introduction partners (interior designers,
    # builders, cleaning) — added on both fresh and existing databases.
    intro_partners = [
        ('interior_designer','Studio Maven','Full-service luxury interior design','none',None,None,''),
        ('interior_designer','Albion & Vale Interiors','Heritage & period-property specialists','none',None,None,''),
        ('builder','Hartley Build & Restore','High-end refurbishment & structural works','none',None,None,''),
        ('builder','Meridian Contractors','Extensions, new-build & fit-out','none',None,None,''),
        ('cleaning','Spotless London','Deep cleans and move-in / move-out','fixed',50.0,'£50 per booking','INHOUS receives a £50 referral fee from Spotless London for each completed booking made through this introduction. This does not affect the price you are quoted.'),
    ]
    for cat, name, notes, ft, fa, fn, disc in intro_partners:
        if not c.execute("SELECT id FROM referral_partners WHERE company_name=?", (name,)).fetchone():
            c.execute('''INSERT INTO referral_partners
                (category, company_name, notes, referral_fee_type, referral_fee_amount, referral_fee_notes, disclosure_text)
                VALUES (?,?,?,?,?,?,?)''', (cat, name, notes, ft, fa, fn, disc))

    conn.commit()
    conn.close()
    print("Referral tables created and seeded")

if __name__ == '__main__':
    init_db()
    add_referral_tables()
