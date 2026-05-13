import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, add_referral_tables
init_db()
add_referral_tables()

from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"INHOUS Platform starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
