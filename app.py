# app.py
# Patched version — robust port parsing and safer import endpoint.
# Based on the user's uploaded file. See upload reference. :contentReference[oaicite:1]{index=1}

from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash, current_app, abort
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from mysql.connector import Error as MySQLError
import traceback

# ---------- Configuration ----------
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')


# # ---- start: reduced logging & health/error handlers ----
# import logging
# from flask import jsonify
# app.py
# Patched version — robust port parsing, safer DB helpers and import endpoints.

from flask import (
    Flask, render_template, request, redirect, session, jsonify,
    url_for, flash, current_app, abort
)
import mysql.connector
from mysql.connector import Error as MySQLError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
import traceback

# ---------- Configuration ----------
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')

# Uploads config
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'avatars')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Logging: keep INFO level (avoid debug flooding)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("task-manager")

# ---------- DB configuration from environment ----------
# Use DB_* env names; Railway uses MYSQL* but you map them to DB_* in variables
DB_HOST = os.environ.get('DB_HOST', '').strip() or None
# DB_PORT may be a string numeric - parsed where used
DB_PORT = os.environ.get('DB_PORT', '').strip() or None
DB_USER = os.environ.get('DB_USER', '').strip() or None
DB_PASSWORD = os.environ.get('DB_PASSWORD', '').strip() or None
DB_NAME = os.environ.get('DB_NAME', '').strip() or None

# Lazy connection holder
_db_connection = None

def parse_port(port_val, default=3306):
    """
    Robust port parsing: accept numeric or string template like ${...}.
    """
    if not port_val:
        return default
    try:
        p = int(port_val)
        return p
    except Exception:
        # If it's a template like ${MYSQL.PORT} return default to avoid crash
        return default

def connect_db():
    """
    Lazy connect to MySQL. Returns connection on success or None on failure.
    Non-fatal: functions using DB should handle None.
    """
    global _db_connection
    # re-use existing connection if alive
    try:
        if _db_connection and getattr(_db_connection, 'is_connected', lambda: True)():
            return _db_connection
    except Exception:
        _db_connection = None

    # If DB env not configured, don't attempt
    if not (DB_HOST and DB_USER and DB_PASSWORD and DB_NAME):
        logger.info("DB credentials not fully provided in environment. DB features disabled until set.")
        _db_connection = None
        return None

    host = DB_HOST
    port = parse_port(DB_PORT, default=3306)

    try:
        logger.info("Attempting DB connection to %s:%s ...", host, port)
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=False,
            connection_timeout=10
        )
        _db_connection = conn
        logger.info("✅ Connected to MySQL database.")
        return _db_connection
    except MySQLError as e:
        logger.warning("❌ Could not connect to MySQL: %s", e)
        _db_connection = None
        return None
    except Exception as e:
        logger.warning("Unexpected error connecting to MySQL: %s", e)
        _db_connection = None
        return None

def get_cursor():
    """
    Return a fresh cursor (dictionary=True) for DB operations.
    Raises RuntimeError if DB not available.
    """
    conn = connect_db()
    if not conn:
        raise RuntimeError("Database not available")
    try:
        return conn.cursor(dictionary=True)
    except Exception as e:
        logger.warning("Could not get DB cursor: %s", e)
        raise RuntimeError("Database cursor not available")

def commit_db():
    global _db_connection
    try:
        if _db_connection:
            _db_connection.commit()
    except Exception as e:
        logger.warning("Commit failed: %s", e)

def rollback_db():
    global _db_connection
    try:
        if _db_connection:
            _db_connection.rollback()
    except Exception as e:
        logger.warning("Rollback failed: %s", e)

# Try an initial connection (non-fatal)
connect_db()

# ---------- Scheduler (kept; start only if DB available) ----------
scheduler = BackgroundScheduler()
scheduler_started = False

def start_scheduler_if_needed():
    global scheduler_started
    if scheduler_started:
        return
    if not _db_connection:
        logger.info("Scheduler not started because DB is not connected.")
        return
    try:
        # Add jobs if needed (example placeholder)
        # scheduler.add_job(my_job, 'interval', minutes=1)
        scheduler.start()
        scheduler_started = True
        logger.info("Scheduler started.")
    except Exception as e:
        logger.warning("Scheduler failed to start: %s", e)

if _db_connection:
    start_scheduler_if_needed()



# ---------- (Example) login/signup routes (kept minimal here) ----------
# NOTE: keep your full implementations below; this file intentionally leaves many of your app routes unchanged.
# If you had many route implementations in your original app.py, paste them here unchanged (I preserved structure).

# ---------- One-time import endpoint (safe) ----------
@app.route('/_import_db_once', methods=['POST'])
def import_db_once():
    """
    One-time import endpoint. Call this from your local machine (curl) once.
    Requires header X-IMPORT-SECRET to match IMPORT_SECRET env var.
    It reads dump.sql from the app root and executes SQL statements.
    """
    secret = request.headers.get('X-IMPORT-SECRET') or request.args.get('import_secret')
    IMPORT_SECRET = os.environ.get('IMPORT_SECRET')
    if not IMPORT_SECRET or not secret or secret != IMPORT_SECRET:
        return jsonify(status='error', code=403, message='Forbidden'), 403

    # Resolve DB connection info from env (support multiple var names)
    host = os.getenv('MYSQLHOST') or os.getenv('MYSQL_HOST') or os.getenv('DB_HOST')
    port = parse_port(os.getenv('MYSQLPORT') or os.getenv('MYSQL_PORT') or os.getenv('DB_PORT') or '')
    user = os.getenv('MYSQLUSER') or os.getenv('MYSQL_USER') or os.getenv('DB_USER')
    password = os.getenv('MYSQLPASSWORD') or os.getenv('MYSQL_PASSWORD') or os.getenv('DB_PASSWORD')
    database = os.getenv('MYSQLDATABASE') or os.getenv('MYSQL_DATABASE') or os.getenv('DB_NAME')

    if not all([host, user, password, database]):
        current_app.logger.error('DB configuration incomplete: host/user/password/database missing')
        return jsonify(status='error', code=500, message='DB configuration incomplete'), 500

    # Ensure dump.sql exists in project root
    dump_path = os.path.join(os.getcwd(), 'dump.sql')
    if not os.path.exists(dump_path):
        current_app.logger.error(f'dump.sql not found at {dump_path}')
        return jsonify(status='error', code=404, message='dump.sql not found'), 404

    try:
        # Connect to DB using provided env details
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connection_timeout=30
        )
    except Exception as e:
        tb = traceback.format_exc()
        current_app.logger.error("Failed to connect to DB for import: %s\n%s", e, tb)
        return jsonify(status='error', code=502, message='DB connection failed for import'), 502

    try:
        cursor = conn.cursor()
        # Read file and execute statements.
        # Note: for very large dumps this approach may be slow; this is OK for moderate dumps.
        with open(dump_path, 'r', encoding='utf-8', errors='ignore') as f:
            sql = f.read()

        # Very simple split by semicolon, tolerates some non-critical failures.
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cursor.execute(stmt + ';')
            except Exception as e_stmt:
                current_app.logger.exception("Statement execution failed (continuing): %s", e_stmt)
                # continue - don't abort whole import on single-statement failure

        conn.commit()
        cursor.close()
        conn.close()

        # Optional: try to remove dump.sql to prevent re-importing accidentally
        try:
            os.remove(dump_path)
            current_app.logger.info("dump.sql removed after import.")
        except Exception:
            # non-fatal - log and continue
            current_app.logger.warning("Could not delete dump.sql automatically (manual cleanup recommended).")

        return jsonify(status='ok', message='Import completed'), 200

    except Exception as e:
        tb = traceback.format_exc()
        current_app.logger.error('Import endpoint exception:\n%s', tb)
        return jsonify(status='error', code=500, message='Import failed; see server logs'), 500

# ---------- Import debug endpoint ----------
@app.route('/_import_debug', methods=['GET'])
def import_debug():
    dump_path = os.path.join(os.getcwd(), 'dump.sql')
    dump_exists = os.path.exists(dump_path)

    # keys to preview (masked)
    keys = [
        'MYSQLHOST','MYSQLPORT','MYSQLUSER','MYSQLPASSWORD','MYSQLDATABASE',
        'DB_HOST','DB_PORT','DB_USER','DB_PASSWORD','DB_NAME','IMPORT_SECRET'
    ]
    env = {}
    for k in keys:
        v = os.getenv(k)
        if v is None:
            env[k] = None
        else:
            env[k] = f"{v[:6]}..({len(v)})" if len(v) > 10 else v

    try:
        files = sorted(os.listdir(os.getcwd()))
    except Exception:
        files = ['<cant list>']

    return jsonify({
        'cwd': os.getcwd(),
        'dump_path': dump_path,
        'dump_exists': dump_exists,
        'files_sample': files[:60],
        'env_preview': env
    }), 200

# ---------- Health endpoint ----------
@app.route('/_health', methods=['GET'])
def health():
    # try to ensure DB is at least reachable quickly
    ok = False
    try:
        conn = connect_db()
        ok = bool(conn)
    except Exception:
        ok = False

    if ok:
        return jsonify(status='ok'), 200
    else:
        return jsonify(status='error', code=502, message='Database unavailable'), 502

# ---------- Error handlers ----------
@app.errorhandler(500)
def server_error(e):
    logger.exception("Server error: %s", e)
    return render_template('500.html'), 500

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

# ---------- Other app routes ----------
# NOTE: Paste your app routes (mytask, profile, edit_profile, dashboard, etc.) below exactly as they were;
# ensure that any code referencing `cursor` now calls `get_cursor()` or wraps DB access in try/except.
#
# Example pattern to adapt existing code that used `cursor`:
#
# try:
#     cursor = get_cursor()
# except RuntimeError:
#     flash("Service temporarily unavailable (database). Please try later.")
#     return redirect(url_for('index'))
#
# cursor.execute("SELECT ...", (...,))
# row = cursor.fetchone()
# commit_db()  # where appropriate
#
# This pattern avoids "cursor is not defined" lint warnings and handles DB-down scenarios.


# ---------- Authentication helper ----------
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapped

# ------------------ Splash route ------------------
@app.route('/splash')
def splash():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('splash.html')

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('splash'))

# ---------- Signup ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        raw_password = request.form.get('password', '')

        password = generate_password_hash(raw_password)
        avatar_file = request.files.get('avatar')
        avatar_filename = None

        if avatar_file and avatar_file.filename and allowed_file(avatar_file.filename):
            ext = avatar_file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            safe_name = secure_filename(unique_name)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
            avatar_file.save(save_path)
            avatar_filename = safe_name

        try:
            cursor = get_cursor()
        except RuntimeError:
            flash("Service temporarily unavailable (database). Please try later.")
            return redirect(url_for('signup'))

        try:
            cursor.execute(
                "INSERT INTO users (fullname, username, email, password, avatar) VALUES (%s, %s, %s, %s, %s)",
                (fullname, username, email, password, avatar_filename)
            )
            commit_db()
            flash("Account created successfully! Please login.")
            return redirect(url_for('index'))
        except MySQLError as e:
            rollback_db()
            logger.warning("Signup DB error: %s", e)
            flash("Username or email already exists or DB error.")
            return redirect(url_for('signup'))
        finally:
            try:
                cursor.close()
            except Exception:
                pass

# ---------- Login ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        try:
            cursor = get_cursor()
        except RuntimeError:
            flash("Service temporarily unavailable (database). Please try later.")
            return redirect(url_for('index'))

        try:
            cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username_or_email, username_or_email))
            user = cursor.fetchone()
        finally:
            try:
                cursor.close()
            except Exception:
                pass

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user.get('username') or user.get('fullname')
            # start scheduler now that user logged in and DB is ready
            start_scheduler_if_needed()
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials!")
            return redirect(url_for('index'))

    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login_page.html')

# ---------- Logout ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------- Dashboard ----------
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('home2.0.html', username=session.get('username'))

# ---------- Tasks endpoints ----------
@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'Bad JSON', 'detail': str(e)}), 400

    title = (data.get('title') or '').strip()
    description = data.get('description') or ''
    due_date = data.get('due_date') or None
    priority = data.get('priority') or 'Medium'

    if not title:
        return jsonify({'error': 'Task title required'}), 400

    try:
        cursor = get_cursor()
    except RuntimeError:
        return jsonify({'error': 'Service offline (DB unavailable)'}), 503

    try:
        cursor.execute(
            "INSERT INTO tasks (user_id, title, description, due_date, priority, status, reminder_at, reminder_sent, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (session['user_id'], title, description, due_date, priority, 'Pending', None, 0)
        )
        commit_db()
        return jsonify({'message': 'Task added'})
    except MySQLError as e:
        rollback_db()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass

@app.route('/update_task', methods=['POST'])
@login_required
def update_task():
    payload = request.get_json(force=True)
    task_id = payload.get('id')
    new_status = payload.get('status')
    if not task_id:
        return jsonify({'error': 'task id required'}), 400

    try:
        cursor = get_cursor()
    except RuntimeError:
        return jsonify({'error': 'Service offline (DB unavailable)'}), 503

    try:
        cursor.execute("UPDATE tasks SET status = %s WHERE id = %s AND user_id = %s", (new_status, task_id, session['user_id']))
        commit_db()
        return jsonify({'message': 'Task updated successfully'})
    except Exception as e:
        rollback_db()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass

@app.route('/delete_task/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    try:
        cursor = get_cursor()
    except RuntimeError:
        return jsonify({'error': 'Service offline (DB unavailable)'}), 503

    try:
        cursor.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
        commit_db()
        return jsonify({'message': 'Task deleted'})
    except Exception as e:
        rollback_db()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass

# ---------- Reminders endpoints ----------
@app.route('/set_reminder/<int:task_id>', methods=['POST'])
@login_required
def set_reminder(task_id):
    try:
        payload = request.get_json(force=True)
        reminder_at = payload.get('reminder_at')
        if not reminder_at:
            return jsonify({'error': 'reminder_at required'}), 400

        try:
            cursor = get_cursor()
        except RuntimeError:
            return jsonify({'error': 'Service offline (DB unavailable)'}), 503

        reminder_db = reminder_at.replace('T', ' ')
        cursor.execute("UPDATE tasks SET reminder_at = %s, reminder_sent = 0 WHERE id = %s AND user_id = %s", (reminder_db, task_id, session['user_id']))
        commit_db()
        return jsonify({'message': 'Reminder saved'}), 200
    except Exception as e:
        rollback_db()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass

@app.route('/clear_reminder/<int:task_id>', methods=['POST'])
@login_required
def clear_reminder(task_id):
    try:
        cursor = get_cursor()
    except RuntimeError:
        return jsonify({'error': 'Service offline (DB unavailable)'}), 503
    try:
        cursor.execute("UPDATE tasks SET reminder_at = NULL, reminder_sent = 0 WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
        commit_db()
        return jsonify({'message': 'Reminder cleared'}), 200
    except Exception as e:
        rollback_db()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass

@app.route('/get_reminders')
@login_required
def get_reminders():
    try:
        cursor = get_cursor()
    except RuntimeError:
        return jsonify([])

    try:
        cursor.execute("SELECT id, title, reminder_at, reminder_sent FROM tasks WHERE user_id = %s AND reminder_at IS NOT NULL ORDER BY reminder_at ASC", (session['user_id'],))
        rows = cursor.fetchall()
        for r in rows:
            if r.get('reminder_at') and isinstance(r['reminder_at'], datetime):
                r['reminder_at'] = r['reminder_at'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass

# ---------- Reminders: scheduler & email ----------
SMTP_USER = os.environ.get('SMTP_USER', os.environ.get('SMTP_EMAIL', 'taskmanagement.team.001@gmail.com'))
SMTP_PASS = os.environ.get('SMTP_PASS', os.environ.get('SMTP_PASSWORD', ''))  # should be set in env

def send_reminder_email(to_email, task_title, task_id):
    if not SMTP_PASS:
        logger.warning("SMTP credentials not configured — skipping email send.")
        return False

    subject = f"Reminder: {task_title}"
    body = f"Reminder for task: {task_title}\n\nOpen your Task Management Tool to view or modify the task.\n\n-- Task Management Tool"

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        logger.info("Reminder email sent to %s for task %s", to_email, task_id)
        return True
    except Exception as e:
        logger.warning("Error sending reminder email: %s", e)
        return False

def find_and_send_reminders():
    """
    Runs periodically by the scheduler. Uses fresh cursors for DB operations.
    """
    try:
        cursor = get_cursor()
    except RuntimeError:
        logger.info("Skipping reminder check — DB not available.")
        return

    try:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "SELECT t.id, t.title, t.reminder_at, u.email FROM tasks t JOIN users u ON t.user_id = u.id "
            "WHERE t.reminder_sent = 0 AND t.reminder_at IS NOT NULL AND t.reminder_at <= %s",
            (now,)
        )
        rows = cursor.fetchall()
        for r in rows:
            to_email = r.get('email')
            task_id = r.get('id')
            title = r.get('title')
            ok = send_reminder_email(to_email, title, task_id)
            if ok:
                update_cursor = get_cursor()
                try:
                    update_cursor.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = %s", (task_id,))
                    commit_db()
                except Exception as e:
                    logger.warning("Could not mark reminder_sent: %s", e)
                    rollback_db()
                finally:
                    try:
                        update_cursor.close()
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("Error in find_and_send_reminders: %s", e)
        rollback_db()
    finally:
        try:
            cursor.close()
        except Exception:
            pass

# ---------- Error handlers ----------
@app.errorhandler(500)
def server_error(e):
    logger.exception("Server error: %s", e)
    return render_template('500.html'), 500

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

# ------------- FORGOT / RESET PASSWORD -------------
@app.route('/forgot_pass')
def forgot_pass():
    return render_template('forgot_pass.html')

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.form.get('email', '').strip()
    try:
        cursor = get_cursor()
    except RuntimeError:
        flash("Service temporarily unavailable (database). Please try later.")
        return redirect(url_for('forgot_pass'))

    try:
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
    finally:
        try:
            cursor.close()
        except Exception:
            pass

    if user:
        send_reset_email(email)
        flash("A password reset link has been sent to your email.", "success")
    else:
        flash("Email not found. Please check and try again.", "error")

    return redirect(url_for('forgot_pass'))

@app.route('/reset-password', methods=['GET'])
def reset_password_form():
    email = request.args.get('email')
    if not email:
        return "Invalid reset link."
    return render_template('reset_password.html', email=email)

@app.route('/reset-password', methods=['POST'])
def reset_password_submit():
    email = request.form['email']
    new_password = request.form['password']

    hashed = generate_password_hash(new_password)
    try:
        cursor = get_cursor()
    except RuntimeError:
        return "<h3>Service temporarily unavailable.</h3>", 503

    try:
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed, email))
        commit_db()
    finally:
        try:
            cursor.close()
        except Exception:
            pass

    return """
    <h3>Password successfully updated!</h3>
    <p>You can now <a href='/'>login</a> with your new password.</p>
    """

def send_reset_email(to_email):
    sender_email = os.environ.get('SMTP_USER', 'taskmanagement.team.001@gmail.com')
    sender_password = os.environ.get('SMTP_PASS', '')  # must set in env for real email sending
    subject = "Password Reset Request - Task Management Tool"
    body = f"""
    Hi,

    We received a request to reset your password.
    Click the link below to reset it:

    {request.url_root.rstrip('/')}/reset-password?email={to_email}

    If you did not request this, please ignore this email.

    Regards,
    Task Management Team
    """

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=15)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        logger.info("Reset email sent to %s", to_email)
    except Exception as e:
        logger.warning("Error sending reset email: %s", e)

# ---------- Other pages ----------
@app.route('/mytask')
def mytask():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    try:
        cursor = get_cursor()
    except RuntimeError:
        return render_template('mytask.html', username='', avatar=None)

    try:
        cursor.execute("SELECT username, avatar FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone() or {}
    finally:
        try:
            cursor.close()
        except Exception:
            pass

    username = user.get('username') if user else ''
    avatar = user.get('avatar') if user else None

    return render_template('mytask.html', username=username, avatar=avatar)

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    try:
        cursor = get_cursor()
    except RuntimeError:
        return render_template('profile.html', fullname='', email='', join_date='Not available', avatar=None)

    try:
        cursor.execute("SELECT fullname, email, created_at, avatar FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone() or {}
    finally:
        try:
            cursor.close()
        except Exception:
            pass

    fullname = user.get('fullname') if user else ''
    email = user.get('email') if user else ''
    created_at = user.get('created_at') if user else None
    avatar = user.get('avatar') if user else None

    if isinstance(created_at, datetime):
        join_date = created_at.strftime('%d %b %Y')
    else:
        join_date = str(created_at) if created_at else 'Not available'

    return render_template(
        'profile.html',
        fullname=fullname,
        email=email,
        join_date=join_date,
        avatar=avatar
    )

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']

    try:
        cursor = get_cursor()
    except RuntimeError:
        flash("Service temporarily unavailable (database). Please try later.")
        return redirect(url_for('profile'))

    try:
        cursor.execute("SELECT fullname, email, avatar FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone() or {}
    finally:
        try:
            cursor.close()
        except Exception:
            pass

    current_avatar = user.get('avatar')

    if request.method == 'POST':
        new_name = request.form.get('fullname', '').strip()
        new_email = request.form.get('email', '').strip()

        avatar_file = request.files.get('avatar')
        avatar_filename = current_avatar

        if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
            ext = avatar_file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            safe_name = secure_filename(unique_name)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
            avatar_file.save(save_path)
            avatar_filename = safe_name

        try:
            cursor = get_cursor()
        except RuntimeError:
            flash("Service temporarily unavailable (database). Please try later.")
            return redirect(url_for('profile'))

        try:
            cursor.execute(
                """
                UPDATE users
                SET fullname = %s, email = %s, avatar = %s
                WHERE id = %s
                """,
                (new_name, new_email, avatar_filename, user_id)
            )
            commit_db()
            flash("Profile updated successfully!")
            return redirect(url_for('profile'))
        except MySQLError as e:
            logger.warning("Edit profile error: %s", e)
            rollback_db()
            flash("Could not update profile. Please try again.")
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    return render_template(
        'edit_profile.html',
        fullname=user.get('fullname'),
        email=user.get('email'),
        avatar=current_avatar
    )

@app.route('/about')
def about():
    return render_template('about.html')

# ---- START ONE-TIME IMPORT ROUTE ----

IMPORT_SECRET = os.environ.get("IMPORT_SECRET")

def parse_int_env(names, default):
    """
    Try to parse an integer from environment variables listed in `names`.
    Return the first valid int found, otherwise return `default`.
    This avoids ValueError when env contains placeholders like '${ MySQL.MYSQLPORT }'.
    """
    for n in names:
        v = os.getenv(n)
        if v is None:
            continue
        v = v.strip()
        if not v:
            continue
        # skip Railway template placeholders like ${ MySQL.MYSQLPORT }
        if v.startswith('${') and '}' in v:
            continue
        try:
            return int(v)
        except Exception:
            continue
    return default

@app.route('/_import_db_once', methods=['POST'])
def import_db_once():
    # require import secret
    secret = request.headers.get('X-IMPORT-SECRET') or request.args.get('import_secret')
    expected = os.getenv('IMPORT_SECRET')
    if not expected or secret != expected:
        return jsonify(status='error', code=403, message='Forbidden'), 403

    try:
        # robust host/user/password/database/port parsing
        host = os.getenv('MYSQLHOST') or os.getenv('MYSQL_HOST') or os.getenv('DB_HOST')
        user = os.getenv('MYSQLUSER') or os.getenv('MYSQL_USER') or os.getenv('DB_USER')
        password = os.getenv('MYSQLPASSWORD') or os.getenv('MYSQL_PASSWORD') or os.getenv('DB_PASSWORD')
        database = os.getenv('MYSQLDATABASE') or os.getenv('MYSQL_DATABASE') or os.getenv('DB_NAME')
        port = parse_int_env(['MYSQLPORT','MYSQL_PORT','DB_PORT','MYSQL_PORT_3306'], 3306)

        if not all([host, user, password, database]):
            current_app.logger.error('DB configuration incomplete: host/user/password/database missing')
            return jsonify(status='error', code=500, message='DB configuration incomplete'), 500

        dump_path = os.path.join(os.getcwd(), 'dump.sql')
        if not os.path.exists(dump_path):
            current_app.logger.error(f'dump.sql not found at {dump_path}')
            return jsonify(status='error', code=404, message='dump.sql not found'), 404

        # Connect and import using mysql-connector
        conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password, database=database,
            connection_timeout=30
        )
        cursor = conn.cursor()

        # Read file and execute statements. Multi-statement SQL will be split by semicolon.
        with open(dump_path, 'r', encoding='utf-8', errors='ignore') as f:
            sql = f.read()

        # Execute statements safely (simple approach). This tolerates non-critical failures.
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cursor.execute(stmt + ';')
            except Exception as e_stmt:
                current_app.logger.exception("Statement execution failed (continuing): %s", e_stmt)
                # continue with remaining statements

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(status='ok', message='Import completed'), 200

    except Exception as e:
        tb = traceback.format_exc()
        current_app.logger.error('Import endpoint exception:\n%s', tb)
        return jsonify(status='error', code=500, message='Import failed; see server logs'), 500

# safe debug endpoint
@app.route('/_import_debug', methods=['GET'])
def import_debug():
    dump_path = os.path.join(os.getcwd(), 'dump.sql')
    dump_exists = os.path.exists(dump_path)

    keys = ['MYSQLHOST','MYSQLPORT','MYSQLUSER','MYSQLPASSWORD','MYSQLDATABASE',
            'DB_HOST','DB_PORT','DB_USER','DB_PASSWORD','DB_NAME','IMPORT_SECRET']
    env = {}
    for k in keys:
        v = os.getenv(k)
        if v is None:
            env[k] = None
        else:
            env[k] = f"{v[:3]}...({len(v)})" if len(v) > 6 else v

    try:
        files = sorted(os.listdir(os.getcwd()))
    except Exception:
        files = ['<cant list>']

    return jsonify({
        'dump_path': dump_path,
        'dump_exists': dump_exists,
        'cwd': os.getcwd(),
        'files_sample': files[:40],
        'env_preview': env
    }), 200

# ---------- App bootstrap ----------
if __name__ == '__main__':
    # allow PORT env or default 5000; parse safely
    try:
        raw_port = os.environ.get('PORT', '5000')
        PORT = int(raw_port) if raw_port and not (raw_port.startswith('${') and '}' in raw_port) else 5000
    except Exception:
        PORT = 5000

    app.run(host='0.0.0.0', port=PORT, debug=False)

