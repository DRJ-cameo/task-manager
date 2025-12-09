# app.py
# Patched version — tightened DB handling, lazy connection, safer cursors, scheduler guarding.
# Based on the user's original file (uploaded). See: file upload reference. :contentReference[oaicite:1]{index=1}

from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash
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

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("task-manager")

# ---------- DB configuration from environment ----------
DB_HOST = os.environ.get('DB_HOST', '').strip() or None
DB_USER = os.environ.get('DB_USER', '').strip() or None
DB_PASSWORD = os.environ.get('DB_PASSWORD', '').strip() or None
DB_NAME = os.environ.get('DB_NAME', '').strip() or None

# Internal connection holder (lazy connect)
_db_connection = None

def connect_db():
    """
    Lazy connect to MySQL. Returns connection on success or None on failure.
    This will not raise on connection failure — it logs and returns None.
    """
    global _db_connection
    if _db_connection and _db_connection.is_connected():
        return _db_connection

    # Ensure we have credentials
    if not (DB_HOST and DB_USER and DB_PASSWORD and DB_NAME):
        logger.info("DB credentials not fully provided in environment. DB features disabled until set.")
        _db_connection = None
        return None

    try:
        logger.info("Attempting DB connection to %s ...", DB_HOST)
        conn = mysql.connector.connect(
            host=DB_HOST,
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
        # Always return a new cursor to avoid reuse issues
        return conn.cursor(dictionary=True)
    except Exception as e:
        logger.warning("Could not get DB cursor: %s", e)
        raise RuntimeError("Database cursor not available")

def commit_db():
    global _db_connection
    if _db_connection:
        try:
            _db_connection.commit()
        except Exception as e:
            logger.warning("Commit failed: %s", e)

def rollback_db():
    global _db_connection
    if _db_connection:
        try:
            _db_connection.rollback()
        except Exception as e:
            logger.warning("Rollback failed: %s", e)

# ---------- Scheduler ----------
scheduler = BackgroundScheduler()
scheduler_started = False

def start_scheduler_if_needed():
    """
    Start the scheduler only if not started and DB is available.
    The scheduled job uses a fresh cursor each run.
    """
    global scheduler_started
    if scheduler_started:
        return

    if not connect_db():
        logger.info("Scheduler not started because DB not connected (yet).")
        return

    try:
        # reference function below
        scheduler.add_job(find_and_send_reminders, 'interval', seconds=60, id='reminder_job', max_instances=1)
        scheduler.start()
        scheduler_started = True
        logger.info("Scheduler started (reminder job).")
    except Exception as e:
        logger.warning("Could not start scheduler: %s", e)

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

        # Use get_cursor() safely
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

    return render_template('signup.html')

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

# ---------- App bootstrap ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Debug False in production; set FLASK_ENV if you want debugging locally
    app.run(host='0.0.0.0', port=port, debug=False)
