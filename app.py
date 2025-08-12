from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
from email_remainder import send_email
import random, string
from datetime import datetime

app = Flask(__name__)
app.secret_key = "yoursecretkey"  # Needed for sessions

@app.route('/')
def index():
    return render_template('index.html')

#manger login
@app.route("/manager_login", methods=["GET", "POST"])
def manager_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM team_managers WHERE email=%s AND password=%s",
            (email, password)
        )
        manager = cursor.fetchone()
        conn.close()

        if manager:
            return redirect(url_for("managers_dashboard"))
        else:
            return redirect(url_for("manager_login"))

    return render_template("manager_login.html")

#manager dashboard
@app.route("/managers_dashboard")
def managers_dashboard():
    if "manager_email" not in session:
        return redirect(url_for("manager_login"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teams ORDER BY created_at DESC")
    teams = cursor.fetchall()
    conn.close()

    return render_template("manager_dashboard.html", teams=teams)

#manager create team
@app.route("/create_team", methods=["GET", "POST"])
def create_team():
    if "manager_email" not in session:
        return redirect(url_for("manager_login"))

    if request.method == "POST":
        leader_email = request.form["leader_email"]
        member_emails = request.form.getlist("member_email")

        if not leader_email or not member_emails:
            flash("Leader and at least one member email are required.")
            return redirect(url_for("create_team"))

        # Generate unique team_id
        team_id = "TEAM" + ''.join(random.choices(string.digits, k=5))
        characters = string.ascii_letters + string.digits
        password = "".join(random.choices(characters, k=7))

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO teams (team_id, leader_email, password) VALUES (%s, %s, %s)",
            (team_id, leader_email, password)
        )

        for m_email in member_emails:
            if m_email.strip():
                cursor.execute(
                    "INSERT INTO team_members (team_id, member_email) VALUES (%s, %s)",
                    (team_id, m_email.strip())
                )

        conn.commit()
        conn.close()

        # Send email to team leader
        subject = "✅ Your New Team ID"
        body = f"Hello,\n\nYour team has been created successfully. \
        \nTeam ID: {team_id}\nPassword: {password}\n Don't share password with anyone\n\nThanks."
        send_email(leader_email, subject, body)

        return redirect(url_for("managers_dashboard"))

    return render_template("create_team.html")

#manager edit team
@app.route("/edit_team/<team_id>", methods=["GET", "POST"])
def edit_team(team_id):
    if "manager_email" not in session:
        return redirect(url_for("manager_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch existing team and members
    cursor.execute("SELECT * FROM teams WHERE team_id = %s", (team_id,))
    team = cursor.fetchone()

    cursor.execute("SELECT member_email FROM team_members WHERE team_id = %s", (team_id,))
    members = cursor.fetchall()

    if request.method == "POST":
        leader_email = request.form["leader_email"]
        member_emails = request.form.getlist("member_email")

        # Update leader email
        cursor.execute("UPDATE teams SET leader_email = %s WHERE team_id = %s", (leader_email, team_id))

        # Remove old members and insert new ones
        cursor.execute("DELETE FROM team_members WHERE team_id = %s", (team_id,))
        for m_email in member_emails:
            if m_email.strip():
                cursor.execute(
                    "INSERT INTO team_members (team_id, member_email) VALUES (%s, %s)",
                    (team_id, m_email.strip())
                )

        conn.commit()
        conn.close()

        flash("Team updated successfully!", "success")
        return redirect(url_for("managers_dashboard"))

    conn.close()
    return render_template("edit_team.html", team=team, members=members)


#leader login
@app.route("/leader_login", methods=["GET", "POST"])
def leader_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM teams WHERE leader_email=%s AND password=%s", (email, password))
            user = cursor.fetchone()
        conn.close()

        if user:
            flash("Leader login successful!", "success")
            return redirect(url_for("leader_dashboard"))  # change to leader dashboard later
        else:
            flash("Invalid Leader credentials!", "danger")

    return render_template("leader_login.html")

#member login
@app.route("/member/login", methods=["GET", "POST"])
def member_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM team_members WHERE email=%s AND password=%s", (email, password))
            user = cursor.fetchone()
        conn.close()

        if user:
            flash("Member login successful!", "success")
            return redirect(url_for("member_dashboard"))  # change to member dashboard later
        else:
            flash("Invalid Member credentials!", "danger")

    return render_template("member_login.html")


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


@app.route('/add_task', methods=['GET', 'POST'])
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

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
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
