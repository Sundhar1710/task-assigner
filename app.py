from flask import Flask, render_template, request, redirect, url_for
from db_config import get_connection
from email_remainder import send_email
app = Flask(__name__)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/check_leader', methods=['POST'])
def check_leader():
    code = request.form['leader_code']
    if code == 'admin123':
        return redirect(url_for('leader_dashboard'))
    else:
        return "<h3>❌ Invalid Leader Code</h3>"

@app.route('/check_member', methods=['POST'])
def check_member():
    team_id = request.form['team_id']
    member_email = request.form['email']
    return redirect(url_for('member_dashboard', team_id=team_id, member_email=member_email))


@app.route('/leader')
def leader_dashboard():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY due_date ASC")
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('leader_dashboard.html', tasks=tasks)

@app.route('/member_dashboard')
def member_dashboard():
    team_id = request.args.get('team_id')
    member_email = request.args.get('member_email')

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, description, due_date, status
        FROM tasks
        WHERE email = %s
    """, (member_email,))

    tasks = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("member_dashboard.html", tasks=tasks, member_email=member_email)


@app.route('/add', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date']
        email = request.form['email']

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (title, description, due_date, email, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (title, description, due_date, email, 'pending'))
        conn.commit()
        cursor.close()
        conn.close()

        subject = "📝 New Task Assigned"
        body = f"Hello,\n\nA new task has been assigned to you:\n\n" \
               f"📌 Title: {title}\n" \
               f"📝 Description: {description or 'No Description'}\n" \
               f"📅 Due Date: {due_date}\n\n" \
               f"This is a system generated mail so don't reply\n\n"\
               f"Thanks,\nTask Assigner System"
        send_email(email, subject, body)

        return redirect(url_for('leader_dashboard'))

    return render_template('add_task.html')

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT email FROM tasks WHERE id = %s", (task_id,))
    existing_task = cursor.fetchone()
    email_id = existing_task[0]
    if not existing_task:
        cursor.close()
        conn.close()
        return redirect(url_for('leader_dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date']
        status = request.form['status']

        cursor.execute("""
            UPDATE tasks
            SET title = %s, description = %s, due_date = %s, status = %s
            WHERE id = %s
        """, (title, description, due_date, status, task_id))
        conn.commit()

        subject = "✏️ Task Updated"
        body = (
            f"Hello,\n\n"
            f"A task assigned to you has been updated:\n\n"
            f"📌 Title: {title}\n"
            f"📝 Description: {description or 'No Description'}\n"
            f"📅 Due Date: {due_date}\n"
            f"📘 Status: {status}\n\n"
            f"This is a system generated mail so don't reply\n\n"
            f"Thanks,\nTask Management System"
        )
        try:
            send_email(email_id, subject, body)
        except Exception as e:
            print("Edit email error:", e)
        cursor.close()
        conn.close()
        return redirect(url_for('leader_dashboard'))
   
    cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    task = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('edit_task.html', task=task)

@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('leader_dashboard'))

@app.route('/complete_task', methods=['POST'])
def complete_task():
    title = request.form['title']
    email = request.form['email']

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET status = 'complete'
        WHERE title = %s AND email = %s
    """, (title, email))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('member_dashboard', member_email=email))

if __name__ == '__main__':
    app.run(debug=True)
