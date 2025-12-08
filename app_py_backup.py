# app.py
from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
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

# ---------- LOGIN ----------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login_page.html')

# ---------- SIGNUP ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        try:
            cursor.execute(
                "INSERT INTO users (fullname, username, email, password) VALUES (%s, %s, %s, %s)",
                (fullname, username, email, password)
            )
            db.commit()
            flash("Account created successfully! Please login.")
            return redirect('/')
        except mysql.connector.Error:
            db.rollback()
            flash("Username or email already exists!")
            return redirect('/signup')
    return render_template('signup.html')

# ---------- LOGIN VERIFY ----------
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, username))
    user = cursor.fetchone()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect('/dashboard')
    else:
        flash("Invalid credentials!")
        return redirect('/')

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('home2.0.html', username=session['username'])

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
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.form['email']

    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if user:
        send_reset_email(email)
        return "✅ A password reset link has been sent to your email."
    else:
        return "❌ Email not found. Please try again."
    
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
    # optionally pass session data
    return render_template('mytask.html', username=session.get('username'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user_id = session['user_id']
    cursor.execute("SELECT fullname, email, created_at FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    fullname = user.get('fullname') if user else ''
    email = user.get('email') if user else ''
    created_at = user.get('created_at') if user else None
    if isinstance(created_at, datetime):
        join_date = created_at.strftime('%d %b %Y')
    else:
        join_date = str(created_at) if created_at else 'Not available'
    return render_template('profile.html', fullname=fullname, email=email, join_date=join_date)

@app.route('/about')
def about():
    return render_template('about.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    # ensure scheduler stops on exit
    try:
        app.run(debug=True)
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
