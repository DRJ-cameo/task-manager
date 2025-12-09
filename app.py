# app.py
from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')

# MySQL connection (adjust credentials if needed)
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="drjcameo@28",   # your MySQL password
    database="task_management",
    autocommit=False
)
cursor = db.cursor(dictionary=True)


from flask import session  # already imported in your app; ensure session is available


# ------------------ NEW: Splash route ------------------
# Renders the splash animation page. The template should include the MP4 in static/videos/splash.mp4
@app.route('/splash')
def splash():
    # If user is already logged in, skip splash and go to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    # render splash.html which should autoplay the video and redirect to the login page after finish
    return render_template('splash.html')
# ------------------------------------------------------


# ---------- LOGIN ----------
@app.route('/')
def index():
    # NOTE: When not logged in, redirect to splash which will show the animation
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('splash'))   # <--- changed to go to splash first


# # ---------- LOGIN ----------
# @app.route('/')
# def index():
#     if 'user_id' in session:
#         return redirect(url_for('dashboard'))
#     return render_template('login_page.html')


# ---------- SIGNUP ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        print(">>> SIGNUP POST RECEIVED")  # debug line

        fullname = request.form.get('fullname', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        raw_password = request.form.get('password', '')

        # hash password (same as before)
        password = generate_password_hash(raw_password)

        # ---- handle avatar file from Step 2 (name="avatar") ----
        avatar_file = request.files.get('avatar')
        avatar_filename = None

        if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
            # get extension
            ext = avatar_file.filename.rsplit('.', 1)[1].lower()
            # make a unique filename so users don't overwrite each other
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            safe_name = secure_filename(unique_name)

            save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
            avatar_file.save(save_path)
            avatar_filename = safe_name   # store this in DB

        try:
            cursor.execute(
                "INSERT INTO users (fullname, username, email, password, avatar) "
                "VALUES (%s, %s, %s, %s, %s)",
                (fullname, username, email, password, avatar_filename)
            )
            db.commit()
            flash("Account created successfully! Please login.")
            return redirect('/')
        except mysql.connector.Error as e:
            print("Signup error:", e)
            db.rollback()
            flash("Username or email already exists!")
            return redirect('/signup')

    return render_template('signup.html')


# ===== Avatar upload config =====
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'avatars')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# =================================


# ---------- LOGIN VERIFY ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username']
        password = request.form['password']

        # example: fetch user
        cursor.execute(
            "SELECT * FROM users WHERE username=%s OR email=%s",
            (username_or_email, username_or_email)
        )
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password'], password):
            # 👇 this is the key line
            flash("Invalid username or password", "error")
            return redirect(url_for('login'))  # or your index route that shows login

        # if OK -> log in user
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect(url_for('dashboard'))

    # GET request -> show login page
    return render_template('login_page.html')

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/')

    user_id = session['user_id']

    # Fetch avatar + username
    cursor.execute("SELECT username, avatar FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    username = user.get("username")
    avatar = user.get("avatar")

    return render_template('home2.0.html', username=username, avatar=avatar)


# ---------- Add task (accepts description, due_date, priority) ----------
@app.route('/add_task', methods=['POST'])
def add_task():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'Bad JSON', 'detail': str(e)}), 400

    title = (data.get('title') or '').strip()
    description = data.get('description') or ''
    due_date = data.get('due_date') or None   # expect YYYY-MM-DD or empty
    priority = data.get('priority') or 'Medium'

    if not title:
        return jsonify({'error': 'Task title required'}), 400

    try:
        cursor.execute(
            "INSERT INTO tasks (user_id, title, description, due_date, priority, status, reminder_at, reminder_sent, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (session['user_id'], title, description, due_date, priority, 'Pending', None, 0)
        )
        db.commit()
        return jsonify({'message': 'Task added successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500

# ---------- Get tasks (for current user) ----------
@app.route('/get_tasks')
def get_tasks():
    if 'user_id' not in session:
        return jsonify([])

    try:
        cursor.execute("""
            SELECT id, title, description, due_date, priority, status, created_at, reminder_at, reminder_sent
            FROM tasks
            WHERE user_id = %s
            ORDER BY 
              CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
              IFNULL(due_date, '9999-12-31') ASC,
              created_at DESC
        """, (session['user_id'],))
        rows = cursor.fetchall()
        # Normalize reminder fields to simple strings (or null)
        for r in rows:
            if r.get('reminder_at'):
                # MySQL datetime to ISO-like string for client
                if isinstance(r['reminder_at'], datetime):
                    # to local naive string: keep as returned
                    r['reminder_at'] = r['reminder_at'].strftime('%Y-%m-%d %H:%M:%S')
                else:
                    r['reminder_at'] = str(r['reminder_at'])
            else:
                r['reminder_at'] = None
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500

# ---------- Toggle task ----------
@app.route('/toggle_task/<int:task_id>', methods=['POST'])
def toggle_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})

    cursor.execute("SELECT status FROM tasks WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
    task = cursor.fetchone()
    if not task:
        return jsonify({'error': 'Task not found'})

    new_status = 'Completed' if task['status'] == 'Pending' else 'Pending'
    cursor.execute("UPDATE tasks SET status = %s WHERE id = %s AND user_id = %s", (new_status, task_id, session['user_id']))
    db.commit()
    return jsonify({'message': 'Task updated successfully'})

# ---------- Delete task ----------
@app.route('/delete_task/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})

    cursor.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
    db.commit()
    return jsonify({'message': 'Task deleted'})

# ---------- Reminders endpoints ----------
@app.route('/set_reminder/<int:task_id>', methods=['POST'])
def set_reminder(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        payload = request.get_json(force=True)
        reminder_at = payload.get('reminder_at')  # expecting 'YYYY-MM-DDTHH:MM' (from datetime-local)
        if not reminder_at:
            return jsonify({'error': 'reminder_at required'}), 400

        # convert to MySQL-friendly format (replace T with space if present)
        reminder_db = reminder_at.replace('T', ' ')
        # update DB
        cursor.execute("UPDATE tasks SET reminder_at = %s, reminder_sent = 0 WHERE id = %s AND user_id = %s", (reminder_db, task_id, session['user_id']))
        db.commit()
        return jsonify({'message': 'Reminder saved'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500

@app.route('/clear_reminder/<int:task_id>', methods=['POST'])
def clear_reminder(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        cursor.execute("UPDATE tasks SET reminder_at = NULL, reminder_sent = 0 WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
        db.commit()
        return jsonify({'message': 'Reminder cleared'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500

@app.route('/get_reminders')
def get_reminders():
    """Return upcoming reminders for current user (for UI or polling)."""
    if 'user_id' not in session:
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

# ---------- Reminders: scheduler to find due reminders and send emails ----------
def send_reminder_email(to_email, task_title, task_id):
    sender_email = "taskmanagement.team.001@gmail.com"
    sender_password = "egtj tdez nwao dbkf"  # Gmail app password — replace with your secure secret
    subject = f"Reminder: {task_title}"
    body = f"Reminder for task: {task_title}\n\nYou asked to be reminded about this task. Open your Task Management Tool to view or modify the task.\n\n-- Task Management Tool"

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
        print("✅ Reminder email sent to", to_email, "for task", task_id)
        return True
    except Exception as e:
        print("❌ Error sending reminder email:", e)
        return False

def find_and_send_reminders():
    """Run periodically to find reminders that are due and not yet sent."""
    try:
        now_utc = datetime.now(timezone.utc)
        # We will compare with server timezone; assume reminder_at stored in DB as local server time.
        # A robust solution is to store UTC in DB and compare using UTC consistently.
        # For now, fetch tasks with reminder_sent = 0 and reminder_at <= now.
        cursor.execute("SELECT t.id, t.title, t.reminder_at, u.email FROM tasks t JOIN users u ON t.user_id = u.id WHERE t.reminder_sent = 0 AND t.reminder_at IS NOT NULL")
        rows = cursor.fetchall()
        for row in rows:
            reminder_at = row.get('reminder_at')
            if not reminder_at:
                continue
            # reminder_at from DB may be datetime or string
            if isinstance(reminder_at, datetime):
                reminder_dt = reminder_at
            else:
                try:
                    reminder_dt = datetime.strptime(str(reminder_at), '%Y-%m-%d %H:%M:%S')
                except Exception:
                    # try alternative format
                    try:
                        reminder_dt = datetime.strptime(str(reminder_at), '%Y-%m-%dT%H:%M:%S')
                    except Exception:
                        continue
            # compare naive to naive (server local) — adjust if needed
            now_local = datetime.now()
            if reminder_dt <= now_local:
                # send email
                success = send_reminder_email(row['email'], row['title'], row['id'])
                if success:
                    cursor.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = %s", (row['id'],))
                    db.commit()
    except Exception as e:
        print("Error in find_and_send_reminders:", e)

# start scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=find_and_send_reminders, trigger="interval", seconds=60, id='reminder_job', replace_existing=True)
scheduler.start()



# ------------- FORGOT PASSWORD (simple flow) -------------
@app.route('/forgot_pass')
def forgot_pass():
    return render_template('forgot_pass.html')


# ✅ Handle forgot password form submission
# ✅ Handle forgot password form submission — flash and redirect back to form
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.form.get('email', '').strip()

    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if user:
        send_reset_email(email)
        flash("A password reset link has been sent to your email.", "success")
    else:
        flash("Email not found. Please check and try again.", "error")

    return redirect(url_for('forgot_pass'))

    
# ✅ Route to show the reset password form
@app.route('/reset-password', methods=['GET'])
def reset_password_form():
    email = request.args.get('email')  # from the link in email
    if not email:
        return "Invalid reset link."
    return render_template('reset_password.html', email=email)


# ✅ Route to handle the actual password update
@app.route('/reset-password', methods=['POST'])
def reset_password_submit():
    email = request.form['email']
    new_password = request.form['password']

    hashed = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed, email))
    db.commit()

    return """
    <h3>Password successfully updated!</h3>
    <p>You can now <a href='/'>login</a> with your new password.</p>
    """
    

# ✅ Function to send the actual reset email
def send_reset_email(to_email):
    sender_email = "taskmanagement.team.001@gmail.com"       # <-- your Gmail address
    sender_password = "egtj tdez nwao dbkf"      # <-- Gmail App Password (not your real password)
    subject = "Password Reset Request - Task Management Tool"
    body = f"""
    Hi,

    We received a request to reset your password.
    Click the link below to reset it:

    http://127.0.0.1:5000/reset-password?email={to_email}

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
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print("✅ Email sent successfully to", to_email)
    except Exception as e:
        print("❌ Error sending email:", e)


# ---------- Other pages ----------
@app.route('/mytask')
def mytask():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor.execute(
        "SELECT username, avatar FROM users WHERE id = %s",
        (user_id,)
    )
    user = cursor.fetchone()

    username = user.get('username') if user else ''
    avatar = user.get('avatar') if user else None

    return render_template('mytask.html', username=username, avatar=avatar)



@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user_id = session['user_id']
    cursor.execute(
        "SELECT fullname, email, created_at, avatar FROM users WHERE id = %s",
        (user_id,)
    )
    user = cursor.fetchone()

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

    # get current user data
    cursor.execute("SELECT fullname, email, avatar FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone() or {}

    current_avatar = user.get('avatar')

    if request.method == 'POST':
        new_name = request.form.get('fullname', '').strip()
        new_email = request.form.get('email', '').strip()

        # avatar upload (optional)
        avatar_file = request.files.get('avatar')
        avatar_filename = current_avatar  # keep old one by default

        if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
            ext = avatar_file.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            safe_name = secure_filename(unique_name)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
            avatar_file.save(save_path)
            avatar_filename = safe_name

        try:
            cursor.execute(
                """
                UPDATE users
                SET fullname = %s, email = %s, avatar = %s
                WHERE id = %s
                """,
                (new_name, new_email, avatar_filename, user_id)
            )
            db.commit()
            flash("Profile updated successfully!")
            return redirect(url_for('profile'))
        except mysql.connector.Error as e:
            print("Edit profile error:", e)
            db.rollback()
            flash("Could not update profile. Please try again.")

    # GET request: show form with current values
    return render_template(
        'edit_profile.html',
        fullname=user.get('fullname'),
        email=user.get('email'),
        avatar=current_avatar
    )


@app.route('/about')
def about():
    return render_template('about.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    # Useful for local testing: read PORT env var if present
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0'
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    # Use threaded=True only for local dev; Gunicorn handles concurrency in production
    app.run(host=host, port=port, debug=debug, threaded=True)