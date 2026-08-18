"""
CloudKida Workshop Backend API v2.0
Flask application with RDS MySQL database support.
Serves both the REST API and static frontend files.

Used in: AWS Architecting & Security 2-Day Workshop
"""

import os
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

# Load environment variables
load_dotenv()

import pathlib
_base_dir = pathlib.Path(__file__).resolve().parent
_frontend_dir = _base_dir / 'frontend'
if not _frontend_dir.exists():
    _frontend_dir = _base_dir.parent / 'frontend'

app = Flask(__name__, static_folder=str(_frontend_dir), static_url_path='')

# CORS configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
CORS(app, origins=allowed_origins)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'workshop-secret-key')


# ========================================
# Database Configuration
# ========================================

def get_db_connection():
    """Create and return a database connection."""
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 3306)),
            database=os.getenv('DB_NAME', 'cloudkida'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', ''),
            connect_timeout=5
        )
        return connection
    except Error as e:
        print(f"[DB ERROR] Failed to connect: {e}")
        return None


def init_database():
    """Initialize database tables if they don't exist."""
    connection = get_db_connection()
    if not connection:
        print("[DB] Could not connect to database. Running without DB support.")
        return False

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(150) NOT NULL,
                subject VARCHAR(200) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visitors (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ip_address VARCHAR(45),
                user_agent TEXT,
                page_visited VARCHAR(200),
                visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS labs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                category VARCHAR(50) NOT NULL,
                duration VARCHAR(50),
                level VARCHAR(50),
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INT AUTO_INCREMENT PRIMARY KEY,
                lab_id INT,
                rating INT CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                user_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE SET NULL
            )
        """)

        # Insert default labs if table is empty
        cursor.execute("SELECT COUNT(*) FROM labs")
        count = cursor.fetchone()[0]
        if count == 0:
            default_labs = [
                ('EC2 Instance Management', 'aws', '45 mins', 'Beginner', 'Launch, configure and manage EC2 instances in AWS cloud.'),
                ('S3 Static Website Hosting', 'aws', '30 mins', 'Beginner', 'Host a static website using Amazon S3 and CloudFront.'),
                ('Linux Administration', 'linux', '60 mins', 'Intermediate', 'Learn essential Linux system administration commands and tools.'),
                ('Container Orchestration', 'docker', '90 mins', 'Advanced', 'Build, run and manage Docker containers and compose applications.'),
                ('VPC Networking', 'aws', '75 mins', 'Intermediate', 'Design and configure Virtual Private Cloud networking in AWS.'),
                ('Kubernetes Basics', 'docker', '120 mins', 'Advanced', 'Deploy and manage containerized applications with Kubernetes.'),
            ]
            cursor.executemany(
                "INSERT INTO labs (title, category, duration, level, description) VALUES (%s, %s, %s, %s, %s)",
                default_labs
            )

        connection.commit()
        print("[DB] Database initialized successfully.")
        return True

    except Error as e:
        print(f"[DB ERROR] Initialization failed: {e}")
        return False
    finally:
        cursor.close()
        connection.close()


# ========================================
# Frontend Routes
# ========================================

@app.route('/')
def serve_frontend():
    """Serve the frontend index.html."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static frontend files."""
    return send_from_directory(app.static_folder, path)


# ========================================
# API Routes
# ========================================

@app.route('/api', methods=['GET'])
def api_home():
    """API root endpoint with information."""
    return jsonify({
        'app': 'CloudKida Workshop API',
        'version': '2.0',
        'status': 'running',
        'database': 'MySQL (RDS)',
        'endpoints': {
            'health': '/api/health',
            'info': '/api/info',
            'contact': '/api/contact (POST)',
            'contacts': '/api/contacts (GET)',
            'labs': '/api/labs (GET, POST)',
            'stats': '/api/stats',
            'visitors': '/api/visitors (POST)',
            'visitor_count': '/api/visitors/count',
            'feedback': '/api/feedback (POST)',
        }
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint with database status."""
    db_status = 'disconnected'
    connection = get_db_connection()
    if connection:
        db_status = 'connected'
        connection.close()

    return jsonify({
        'status': 'healthy',
        'version': '2.0',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'cloudkida-workshop-backend',
        'database': db_status
    })


@app.route('/api/info', methods=['GET'])
def app_info():
    """Application information endpoint."""
    return jsonify({
        'app_name': 'CloudKida',
        'description': 'Experiential Learning Platform',
        'version': '2.0',
        'environment': os.getenv('FLASK_ENV', 'production'),
        'features': [
            'Hands-on Cloud Labs',
            'Linux Platform',
            'Windows Platform',
            'Custom Labs',
            'Self-Service Portal',
            'Dynamic Lab Management',
            'Visitor Tracking',
            'Feedback System'
        ],
        'contact': {
            'email': 'inquiry@cloudkida.com',
            'phone': '75748 77958',
            'location': 'Ahmedabad, Gujarat, India'
        }
    })


@app.route('/api/labs', methods=['GET'])
def get_labs():
    """Get list of available labs from database."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database unavailable'}), 503

    try:
        cursor = connection.cursor(dictionary=True)

        category = request.args.get('category')
        if category and category != 'all':
            cursor.execute(
                "SELECT * FROM labs WHERE is_active = TRUE AND category = %s ORDER BY id",
                (category,)
            )
        else:
            cursor.execute("SELECT * FROM labs WHERE is_active = TRUE ORDER BY id")

        labs = cursor.fetchall()

        for lab in labs:
            if lab.get('created_at'):
                lab['created_at'] = lab['created_at'].isoformat()

        return jsonify({
            'labs': labs,
            'total': len(labs)
        })

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/labs', methods=['POST'])
def create_lab():
    """Add a new lab to the database."""
    data = request.get_json()

    required_fields = ['title', 'category']
    for field in required_fields:
        if not data or not data.get(field):
            return jsonify({'error': f'Field "{field}" is required'}), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database unavailable'}), 503

    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO labs (title, category, duration, level, description) VALUES (%s, %s, %s, %s, %s)",
            (data['title'], data['category'], data.get('duration', ''), data.get('level', ''), data.get('description', ''))
        )
        connection.commit()

        return jsonify({
            'message': 'Lab created successfully',
            'lab_id': cursor.lastrowid
        }), 201

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get platform statistics from database."""
    connection = get_db_connection()
    if not connection:
        return jsonify({
            'students_enrolled': 1098,
            'labs_available': 6,
            'total_visitors': 0,
            'total_contacts': 0,
            'database': 'disconnected'
        })

    try:
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM labs WHERE is_active = TRUE")
        labs_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM visitors")
        visitors_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM contacts")
        contacts_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM feedback")
        feedback_count = cursor.fetchone()[0]

        return jsonify({
            'students_enrolled': 1098,
            'labs_available': labs_count,
            'total_visitors': visitors_count,
            'total_contacts': contacts_count,
            'total_feedback': feedback_count,
            'database': 'connected',
            'last_updated': datetime.utcnow().isoformat()
        })

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/contact', methods=['POST'])
def submit_contact():
    """Handle contact form submissions - stores in database."""
    data = request.get_json()

    required_fields = ['name', 'email', 'subject', 'message']
    for field in required_fields:
        if not data or not data.get(field):
            return jsonify({'error': f'Field "{field}" is required'}), 400

    email = data.get('email', '')
    if '@' not in email or '.' not in email:
        return jsonify({'error': 'Invalid email address'}), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database unavailable. Please try again later.'}), 503

    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO contacts (name, email, subject, message) VALUES (%s, %s, %s, %s)",
            (data['name'], data['email'], data['subject'], data['message'])
        )
        connection.commit()

        return jsonify({
            'message': 'Thank you for contacting us! We will get back to you soon.',
            'status': 'stored',
            'id': cursor.lastrowid
        }), 201

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    """Retrieve all contact submissions (admin endpoint)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database unavailable'}), 503

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM contacts ORDER BY created_at DESC LIMIT 50")
        contacts = cursor.fetchall()

        for contact in contacts:
            if contact.get('created_at'):
                contact['created_at'] = contact['created_at'].isoformat()

        return jsonify({
            'contacts': contacts,
            'total': len(contacts)
        })

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/visitors', methods=['POST'])
def track_visitor():
    """Track a visitor (called from frontend)."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'status': 'skipped'}), 200

    try:
        cursor = connection.cursor()
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'unknown')
        page = request.get_json().get('page', '/') if request.is_json else '/'

        cursor.execute(
            "INSERT INTO visitors (ip_address, user_agent, page_visited) VALUES (%s, %s, %s)",
            (ip, user_agent, page)
        )
        connection.commit()

        return jsonify({'status': 'tracked'}), 201

    except Error as e:
        return jsonify({'status': 'error'}), 200
    finally:
        cursor.close()
        connection.close()


@app.route('/api/visitors/count', methods=['GET'])
def visitor_count():
    """Get total visitor count."""
    connection = get_db_connection()
    if not connection:
        return jsonify({'count': 0, 'database': 'disconnected'})

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM visitors")
        count = cursor.fetchone()[0]

        return jsonify({'count': count, 'database': 'connected'})

    except Error as e:
        return jsonify({'count': 0, 'error': str(e)}), 200
    finally:
        cursor.close()
        connection.close()


@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """Submit feedback for a lab."""
    data = request.get_json()

    if not data or not data.get('rating'):
        return jsonify({'error': 'Rating is required'}), 400

    rating = data.get('rating')
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({'error': 'Rating must be between 1 and 5'}), 400

    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database unavailable'}), 503

    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO feedback (lab_id, rating, comment, user_name) VALUES (%s, %s, %s, %s)",
            (data.get('lab_id'), rating, data.get('comment', ''), data.get('user_name', 'Anonymous'))
        )
        connection.commit()

        return jsonify({
            'message': 'Thank you for your feedback!',
            'id': cursor.lastrowid
        }), 201

    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


# ========================================
# Error Handlers
# ========================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405


# ========================================
# Main Entry Point
# ========================================

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'

    print(f"""
    ╔══════════════════════════════════════════╗
    ║   CloudKida Workshop API v2.0           ║
    ║   Running on http://{host}:{port}         ║
    ║   Database: MySQL (RDS)                 ║
    ║   Frontend: Serving static files        ║
    ╚══════════════════════════════════════════╝
    """)

    # Initialize database tables
    init_database()

    app.run(host=host, port=port, debug=debug)
