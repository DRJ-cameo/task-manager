from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="drjcameo@28",   # your MySQL password
    database="task_management"
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
            flash("Username or email already exists!")
            return redirect('/signup')
    return render_template('signup.html')

# ---------- LOGIN VERIFY ----------
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect('/dashboard')
    else:
        return "Invalid credentials!"

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('home2.0.html', username=session['username'])
# import at top if not present
from flask import Flask, request, jsonify, session, render_template, redirect, url_for
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import os

# ... your existing connection and app setup ...

# Add task (accepts description, due_date, priority)
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
            "INSERT INTO tasks (user_id, title, description, due_date, priority) VALUES (%s,%s,%s,%s,%s)",
            (session['user_id'], title, description, due_date, priority)
        )
        db.commit()
        return jsonify({'message': 'Task added successfully'}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500

# Get tasks (return due_date and priority as-is)
@app.route('/get_tasks')
def get_tasks():
    if 'user_id' not in session:
        return jsonify([])

    try:
        cursor.execute("""
            SELECT id, title, description, due_date, priority, status, created_at
            FROM tasks
            WHERE user_id = %s
            ORDER BY 
              CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
              IFNULL(due_date, '9999-12-31') ASC,
              created_at DESC
        """, (session['user_id'],))
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': 'DB error', 'detail': str(e)}), 500


# ---------- TOGGLE TASK ----------
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

# ---------- DELETE TASK ----------
@app.route('/delete_task/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})

    cursor.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, session['user_id']))
    db.commit()
    return jsonify({'message': 'Task deleted'})


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

# (You can keep your existing email send function here; I'd add a secure reset token in future)

# in app.py (with your existing imports & db/session code)
from flask import render_template

@app.route('/mytask')
def mytask():
    # optionally pass session data
    return render_template('mytask.html', username=session.get('username'))

from datetime import datetime
from flask import session, redirect, url_for, render_template

@app.route('/profile')
def profile():
    # require login
    if 'user_id' not in session:
        return redirect(url_for('index'))   # send to login

    user_id = session['user_id']

    # fetch user info
    cursor.execute("SELECT fullname, email, created_at FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if user:
        fullname = user.get('fullname') or ''
        email = user.get('email') or ''
        created_at = user.get('created_at')  # may be None if column not present
        # format created_at as readable string if it is a datetime
        if isinstance(created_at, datetime):
            join_date = created_at.strftime('%d %b %Y')
        elif created_at:
            join_date = str(created_at)
        else:
            join_date = 'Not available'
    else:
        # fallback if user not found
        fullname = ''
        email = ''
        join_date = 'Not available'

    return render_template('profile.html',
                           fullname=fullname,
                           email=email,
                           join_date=join_date)


@app.route('/about')
def about():
    return render_template('about.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
