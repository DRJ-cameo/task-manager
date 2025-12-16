from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash, current_app
import mysql.connector
from mysql.connector import Error as MySQLError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import uuid, os, logging, smtplib, traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ================= CONFIG =================
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')

UPLOAD_FOLDER = os.path.join('static', 'uploads', 'avatars')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("task-manager")

# ================= DB ENV =================
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

def parse_port(v, default=3306):
    try:
        return int(v)
    except Exception:
        return default

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=parse_port(DB_PORT),
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        connection_timeout=10
    )

def get_cursor():
    conn = get_db_connection()
    return conn, conn.cursor(dictionary=True)

# ================= HELPERS =================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapped

# ================= SCHEDULER =================
scheduler = BackgroundScheduler()

def find_and_send_reminders():
    try:
        conn, cursor = get_cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            SELECT t.id, t.title, u.email
            FROM tasks t JOIN users u ON t.user_id=u.id
            WHERE t.reminder_sent=0 AND t.reminder_at IS NOT NULL AND t.reminder_at<=%s
        """, (now,))
        rows = cursor.fetchall()

        for r in rows:
            if send_reminder_email(r['email'], r['title']):
                cursor.execute(
                    "UPDATE tasks SET reminder_sent=1 WHERE id=%s",
                    (r['id'],)
                )
                conn.commit()
    except Exception as e:
        logger.warning("Reminder error: %s", e)
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

@app.before_first_request
def start_scheduler():
    try:
        scheduler.add_job(find_and_send_reminders, 'interval', minutes=1)
        scheduler.start()
    except Exception as e:
        logger.warning("Scheduler disabled: %s", e)

# ================= ROUTES =================

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

# ---------- AUTH ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        avatar_filename = None
        avatar_file = request.files.get('avatar')

        if avatar_file and allowed_file(avatar_file.filename):
            ext = avatar_file.filename.rsplit('.', 1)[1]
            avatar_filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

        try:
            password = request.form['password']

            conn, cursor = get_cursor()
            cursor.execute(
             "INSERT INTO users (fullname, username, email, password, avatar) VALUES (%s,%s,%s,%s,%s)",
             (
                request.form['fullname'],
                request.form['username'],
                request.form['email'],
                generate_password_hash(
                password,
                method="pbkdf2:sha256",
                salt_length=16
           ),
             avatar_filename
            )
        )
            conn.commit()
            flash("Account created successfully!")
        except MySQLError:
            flash("Username or email already exists")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_input = request.form['username']
        password = request.form['password']

        conn, cursor = get_cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username=%s OR email=%s",
            (user_input, user_input)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        try:
           valid = check_password_hash(user['password'], password)
        except ValueError:
           flash("Password format not supported. Please reset your password.")
           return redirect(url_for("login"))

        if user and valid:
         session['user_id'] = user['id']
         session['username'] = user.get('username')
         return redirect(url_for("dashboard"))


        flash("Invalid credentials")

    return render_template('login_page.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------- DASHBOARD ----------
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('home2.0.html', username=session.get('username'))

# ---------- TASKS ----------
@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    data = request.get_json(force=True)
    conn, cursor = get_cursor()
    cursor.execute(
        """INSERT INTO tasks (user_id,title,description,due_date,priority,status,created_at)
           VALUES (%s,%s,%s,%s,%s,'Pending',NOW())""",
        (
            session['user_id'],
            data['title'],
            data.get('description'),
            data.get('due_date'),
            data.get('priority', 'Medium')
        )
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Task added'})

@app.route('/update_task', methods=['POST'])
@login_required
def update_task():
    data = request.get_json(force=True)
    conn, cursor = get_cursor()
    cursor.execute(
        "UPDATE tasks SET status=%s WHERE id=%s AND user_id=%s",
        (data['status'], data['id'], session['user_id'])
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Task updated'})

@app.route('/delete_task/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    conn, cursor = get_cursor()
    cursor.execute(
        "DELETE FROM tasks WHERE id=%s AND user_id=%s",
        (task_id, session['user_id'])
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message': 'Task deleted'})

# ---------- EMAIL ----------
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')

def send_reminder_email(to_email, title):
    if not SMTP_PASS:
        return False
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        msg = MIMEText(f"Reminder for task: {title}")
        msg['Subject'] = "Task Reminder"
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        server.send_message(msg)
        server.quit()
        return True
    except Exception:
        return False

# ---------- OTHER PAGES ----------
@app.route('/mytask')
def mytask():
    return render_template('mytask.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/edit_profile')
def edit_profile():
    return render_template('edit_profile.html')

@app.route('/about')
def about():
    return render_template('about.html')

# ---------- RUN ----------
if __name__ == '__main__':
    PORT = parse_port(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=PORT, debug=False)
