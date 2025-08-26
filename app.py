from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
from email_remainder import send_email
import mysql.connector
import random, string
from generate_password import generate_password
import os, secrets
from datetime import datetime, date


# correct the duplicate members in adding team members in team manager field
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))  

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response

@app.route('/')
def index():
    return render_template('index.html')

#manger login
@app.route("/manager_login", methods=["GET", "POST"])
def manager_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if not email.endswith("@gmail.com"):
            flash("⚠️ Only Gmail addresses are allowed!", "warning")
            return redirect(url_for("manager_login"))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM team_managers WHERE email=%s AND password=%s",
            (email, password)
        )
        manager = cursor.fetchone()
        conn.close()

        if manager:
            session["manager_email"] = email  # store login info in session
            return redirect(url_for("managers_dashboard"))

        else:
            flash(f"🤦‍♂️ Wrong credientals!", 'danger')
            return redirect(url_for("manager_login"))

    return render_template("manager_login.html")

#manager dashboard
@app.route("/managers_dashboard")
def managers_dashboard():
    if "manager_email" not in session:
        return redirect(url_for("manager_login"))
    
    email = session.get("manager_email")
    sort_by = request.args.get("sort_by")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT manager_id FROM team_managers WHERE email = %s", (email,))
    manager_id = cursor.fetchone()[0]

    query = f"SELECT * FROM teams WHERE manager_id = '{manager_id}'"

    if sort_by == "email_a":
        query += " ORDER BY leader_email ASC"
    elif sort_by == "date_new":
        query += " ORDER BY created_at DESC"
    elif sort_by == "date_old":
        query += " ORDER BY created_at ASC"
    elif sort_by == "email_z":
        query += " ORDER BY leader_email DESC"

    cursor.execute(query)

    teams = cursor.fetchall()
    conn.close()

    #get success/error from query params
    success = request.args.get("success")
    error = request.args.get("error")

    return render_template("manager_dashboard.html", teams=teams, success=success, error=error)

#manager create team
@app.route("/create_team", methods=["GET", "POST"])
def create_team():
    if "manager_email" not in session:
        return redirect(url_for("manager_login"))

    if request.method == "POST":
        leader_email = request.form["leader_email"]
        member_emails = request.form.getlist("member_email")

        email = session.get('manager_email')

        if not leader_email or not member_emails or not email:
            flash("🤔 Login Again", "warning")
            return redirect(url_for("create_team"))
        
        if not leader_email.endswith("@gmail.com"):
            flash("⚠️ Only Gmail addresses are allowed!", "warning")
            return redirect(url_for("create_team"))

        # Generate unique team_id, password
        team_id = "TEAM" + ''.join(random.choices(string.digits, k=5))
        leader_password = generate_password()

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT manager_id FROM team_managers WHERE email = %s", (email,))
            temp = cursor.fetchone()
            manager_id = temp[0]

            cursor.execute(
            "INSERT INTO teams (team_id, leader_email, password, manager_id) VALUES (%s, %s, %s, %s)", (team_id, leader_email, leader_password, manager_id)) 

        except mysql.connector.IntegrityError:
            #leder_email is unique in database so if we try with same email this except will happen
            flash("😪 This leader already has a team!", "danger")
            return redirect(url_for('create_team')) 
        
        validated_members = []  # store members who passed validation
        seen = set()  #for duplicate

        for m_email in member_emails:
            m_email = m_email.strip()
            if not m_email:
                continue

            if not m_email.endswith("@gmail.com"):
                flash("⚠️ Only Gmail addresses are allowed!", "warning")
                return redirect(url_for("create_team"))

            # check duplicates in the submitted form itself
            if m_email in seen:
                conn.rollback()
                conn.close()
                flash(f"⚠️ {m_email} is entered two or more times!", "danger")
                return redirect(url_for("create_team"))
            seen.add(m_email)


            # check if member is a leader in some other team
            cursor.execute("SELECT * FROM teams WHERE leader_email = %s", (m_email,))
            if cursor.fetchone():
                conn.rollback()
                conn.close()
                flash(f"⚠️ {m_email} is a leader, cannot be added as member!", "danger")
                return redirect(url_for("create_team"))

            # check for password reuse
            cursor.execute("SELECT password FROM team_members WHERE member_email = %s", (m_email,))
            member_exist = cursor.fetchone()
        
            if member_exist:
                validated_members.append(
                    {"email": m_email, "password": member_exist[0], "new": False}
                )
            else:
                validated_members.append(
                    {"email": m_email, "password": generate_password(), "new": True}
                )

        # Step 2: Insert all validated members
        try:
            for member in validated_members:
                cursor.execute(
                    "INSERT INTO team_members (team_id, member_email, password) VALUES (%s, %s, %s)",
                    (team_id, member["email"], member["password"]))

            conn.commit()

        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f"🙄 Error while creating team: {str(e)}", "danger")
            return redirect(url_for("create_team"))

        finally:
            conn.close()

        # Step 3: Send emails after success
        # Leader mail
        subject = "✅ Assigned as a Team Leader"
        body = f"""Hello,

            Your team has been created successfully.
            Team ID: {team_id}
            Password: {leader_password}

            Don't share your password with anyone.

            Thanks."""
        send_email(leader_email, subject, body)

        # Members mail
        for member in validated_members:
            if member["new"]:
                subject = "✅ Assigned as a Team Member"
                body = f"""Hello,

                You are assigned to team {team_id}.
                Team ID: {team_id}
                Password: {member['password']}

                Login with your credentials to see the tasks.
                Don't share your password with anyone.

                Thanks."""
            else:
                subject = "✅ Assigned as a Team Member for exist Team"
                body = f"""Hello,

                You are assigned to a new team {team_id}. Please use your existing password to login.

                Team ID: {team_id}
                Password: USE EXISTING PASSWORD (same as before)

                Don't share your password with anyone.

                Thanks."""
            send_email(member["email"], "✅ Assigned to New Team", body)

        flash("👍 Team created successfully!", "success")
        return redirect(url_for("managers_dashboard"))
    return render_template("create_team.html")

#manager edit team
@app.route("/edit_team/<team_id>", methods=["GET", "POST"])
def edit_team(team_id):
    if "manager_email" not in session:
        return redirect(url_for("manager_login"))

    conn = get_connection()
    cursor = conn.cursor()

    # Fetch existing team and members
    cursor.execute("SELECT leader_email FROM teams WHERE team_id = %s", (team_id,))
    team = cursor.fetchone()

    cursor.execute("SELECT member_email FROM team_members WHERE team_id = %s", (team_id,))
    members = [row[0] for row in cursor.fetchall()]  # extract just the email string

    if request.method == "POST":
        leader_email = request.form["leader_email"]
        member_emails = request.form.getlist("member_email")

        if not leader_email.endswith("@gmail.com"):
            flash("⚠️ Only Gmail addresses are allowed!", "warning")
            return redirect(url_for("edit_team", team_id=team_id))
        
        for m in member_emails:
            if not m.endswith("@gmail.com"):
                flash("⚠️ Only Gmail addresses are allowed!", "warning")
                return redirect(url_for('edit_team', team_id=team_id))

        try:
            if leader_email != team[0]:
                # Update leader email
                password = generate_password()
                cursor.execute("UPDATE teams SET leader_email = %s, password = %s WHERE team_id = %s", (leader_email, password, team_id,))
    
                # Send email to team leader
                subject = "✅ Assigned as a New Team Leader to Exist Team"
                body = f"Hello,\n\nYour where assigned as a new Leader for {team_id}. \
                \nTeam ID: {team_id}\nPassword: {password} \
                \nLogin with those credentials to modify or assign task to team members\n \
                \nDon't share password with anyone\n\nThanks."
                send_email(leader_email, subject, body)

            to_delete = set(members) - set(member_emails) #members -> old team members
            to_add = set(member_emails) - set(members)    #member_emails -> new team members

            #delete old members
            if to_delete:
                for m_email in to_delete:
                    cursor.execute("DELETE FROM team_members WHERE team_id = %s AND member_email = %s", (team_id, m_email))

            # add new one and send mail
            if to_add:
                for m_email in to_add:
                    cursor.execute("SELECT password FROM team_members WHERE member_email = %s", (m_email,))
                    member_exist = cursor.fetchone()
                    if member_exist:
                        exist_password = member_exist[0]
                        print(exist_password)
                        cursor.execute(
                            "INSERT INTO team_members (team_id, member_email, password) VALUES (%s, %s, %s)",
                            (team_id, m_email.strip(), exist_password)
                        )
                        # Send email to team members
                        subject = "✅ Assigned to New Team"
                        body = f"Hello,\n\nYou are assigned to a new team {team_id}. Please use your existing password to login.. \
                        \n\nTeam ID: {team_id}\nPassword: USE EXIST PASSWORD WHICH PREVIOUSLY USED FOR LOGIN AS MEMBER.\n\n \
                        Don't share password with anyone\n\nThanks."
                        send_email(m_email, subject, body)
                    else:
                        password = generate_password()
                        cursor.execute(
                            "INSERT INTO team_members (team_id, member_email, password) VALUES (%s, %s, %s)",
                            (team_id, m_email, password,)
                        )
                        subject = "✅ Assigned as a Team Member to Exist Team"
                        body = f"Hello,\n\nYour where assigned as a Member for {team_id}. \
                        \nTeam ID: {team_id}\nPassword: {password} \
                        \nLogin to see further details \
                        \nDon't share password with anyone\n\nThanks."
                        send_email(m_email, subject, body)
            conn.commit()
            conn.close()
            flash("👍 Team successfully edited!", "success")
            return redirect(url_for("managers_dashboard"))
        except mysql.connector.InterfaceError:
            conn.rollback()
            conn.close()
            flash("⚠️ Something went wrong while editing!", "danger")
            return redirect(url_for("managers_dashboard"))

    conn.close()
    return render_template("edit_team.html", team=team, members=members)

@app.route("/delete_team/<team_id>")
def delete_team(team_id):

    if "manager_email" not in session:
        return redirect(url_for("manager_login"))
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM tasks WHERE team_id = %s", (team_id,))
        cursor.execute("DELETE FROM team_members WHERE team_id = %s", (team_id,))
        cursor.execute("DELETE FROM teams WHERE team_id = %s", (team_id,))
    except Exception:
        conn.rollback()
        conn.close()
        flash("🙄 Something went wrong while Deleting the Team Try again!", "danger")
        return redirect(url_for("managers_dashboard"))
    
    conn.commit()
    conn.close()    

    flash(f"⚰️ Team Deleted Successfully!", "success")
    return redirect(url_for("managers_dashboard"))

@app.route("/manager_logout")
def manager_logout():
    session.pop("manager_email", None)
    return redirect(url_for("manager_login"))

#leader login
@app.route("/leader_login", methods=["GET", "POST"])
def leader_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if not email.endswith("@gmail.com"):
            flash("⚠️ Only Gmail addresses are allowed!", "warning")
            return redirect(url_for("leader_login"))

        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM teams WHERE leader_email=%s AND password=%s", (email, password))
            user = cursor.fetchone()
        conn.close()

        if user:
            session["leader_email"] = email
            session["team_id"] = user[1]
            return redirect(url_for("leader_dashboard"))  # change to leader dashboard later
        else:
            flash(f"🤦‍♂️ Wrong credientals!", 'danger')
            return redirect(url_for("leader_login"))
        
    return render_template("leader_login.html")

@app.route('/leader')
def leader_dashboard():
    if "leader_email" not in session:
        return redirect(url_for("leader_login"))
    
    assigned_by = session.get("leader_email")
    sort_by = request.args.get("sort_by")

    conn = get_connection()
    cursor = conn.cursor()

    query = f"SELECT * FROM tasks WHERE assigned_by = '{assigned_by}'"

    if sort_by == "pending":
        query += " AND status = 'pending'"
    elif sort_by == "completed":
        query += " AND status = 'complete'"
    elif sort_by == "new":
        query += " ORDER BY created_at DESC"
    elif sort_by == "old":
        query += " ORDER BY created_at ASC"
    
    cursor.execute(query)
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('leader_dashboard.html', tasks=tasks)

@app.route("/leader_logout")
def leader_logout():
    session.pop("leader_email", None)                # ✅ clear session
    return redirect(url_for("leader_login"))

#member login
@app.route("/member/login", methods=["GET", "POST"])
def member_login():
    
    if request.method == "POST":
        password = request.form["password"]
        email = request.form["email"]
        team_id = request.form["team_id"]

        if not email.endswith("@gmail.com"):
            flash("⚠️ Only Gmail addresses are allowed!", "warning")
            return redirect(url_for("member_login"))
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM team_members WHERE password=%s AND member_email=%s AND team_id=%s", (password, email, team_id))
        user = cursor.fetchone()
        conn.close()

        if user:
            session["member_email"] = email
            session["team_id"] = team_id
            return redirect(url_for("member_dashboard")) 
        else:
            flash(f"🙅‍♂️ Wrong credential!", 'danger')
            return redirect(url_for('member_login'))
        

    return render_template("member_login.html")

@app.route('/member_dashboard')
def member_dashboard():
    if "member_email" not in session or "team_id" not in session:
        flash("Session time out! Try to login again", 'warning')
        return redirect(url_for("member_login"))
    
    member_email = session.get('member_email')
    team_id = session.get('team_id')
    sort_by = request.args.get("sort_by")

    conn = get_connection()
    cursor = conn.cursor()

    query = f"SELECT title, description, due_date, status, assigned_by FROM tasks WHERE email = '{member_email}' and team_id = '{team_id}'"

    if sort_by == "pending":
        query += " AND status = 'pending'"
    elif sort_by == "completed":
        query += " AND status = 'complete'"
    elif sort_by == "new":
        query += " ORDER BY due_date DESC"
    elif sort_by == "old":
        query += " ORDER BY due_date ASC"

    cursor.execute(query)
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("member_dashboard.html", tasks=tasks, member_email=member_email)

@app.route("/member_logout")
def member_logout():
    session.pop("member_email", None)                # ✅ clear session
    return redirect(url_for("member_login"))

@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    if "leader_email" not in session:
        return redirect(url_for("leader_login"))

    conn = get_connection()
    cursor = conn.cursor()

    # get leader’s team_id
    assigned_email = session.get("leader_email")
    cursor.execute("SELECT team_id FROM teams WHERE leader_email = %s", (assigned_email,))
    temp = cursor.fetchone()
    if not temp:
        conn.close()
        flash('⚠️ You don’t belong to any team!', 'danger')
        return redirect(url_for("leader_dashboard"))

    team_id = temp[0]

    # fetch team members
    cursor.execute("SELECT member_email FROM team_members WHERE team_id = %s", (team_id,))
    team_members = [row[0] for row in cursor.fetchall()]  # extract emails

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date']
        selected_emails = request.form.getlist("emails")  # list of selected members

        try:
            # Convert string to date
            due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            error = "Invalid date format. Please use MM-DD-YYYY."
            return redirect(url_for("add_task", error=error))

        # Validate that the date is not in the past
        if due_date < date.today():
            error = "Due date cannot be in the past."
            return redirect(url_for("add_task",error=error))
    
        if not selected_emails:
            conn.close()
            flash('⚠️ Please select at least one member!','warning')
            return redirect(url_for("add_task"))

        try:
            for m_email in selected_emails:
                
                cursor.execute("""
                    INSERT INTO tasks (title, description, due_date, email, status, 
                    assigned_by, team_id) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (title, description, due_date, m_email, 'pending', assigned_email, team_id))

                # send email for each member
                subject = "📝 New Task Assigned"
                body = f"Hello,\n\nA new task has been assigned to you:\n\n" \
                       f"📌 Title: {title}\n" \
                       f"📅 Due Date: {due_date}\n" \
                       f"for further details please login\n\n" \
                       f"This is a system generated mail so don't reply\n\n" \
                       f"Thanks,\nTask Assigner System"
                send_email(m_email, subject, body)

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            print("Error adding task:", e)
            flash('⚠️ Failed to add task.','warning')
            return redirect(url_for("leader_dashboard"))

        conn.close()
        flash('✅ Task(s) assigned successfully','success')
        return redirect(url_for('leader_dashboard'))

    conn.close()
    error = request.args.get('error')
    return render_template('add_task.html', team_members=team_members, error=error)

@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT email FROM tasks WHERE id = %s", (task_id,))
    existing_task = cursor.fetchone()
    if not existing_task:
        cursor.close()
        conn.close()
        return redirect(url_for('leader_dashboard'))
    email_id = existing_task[0]

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date']
        status = request.form['status']

        try:
            # Convert string to date
            due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format. Please use MM-DD-YYYY.", 'warning')
            return redirect(url_for("edit_task"))

        # Validate that the date is not in the past
        if due_date < date.today():
            flash("⚠️ Due date cannot be in the past.", 'warning')
            return redirect(url_for("edit_task"))

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
            f"📅 Due Date: {due_date}\n"
            f"for more details please login\n\n"
            f"This is a system generated mail so don't reply\n\n"
            f"Thanks,\nTask Assigner System"
        )
        try:
            flash("👍 Team edit Successful", 'success')
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

@app.route('/delete_task/<int:task_id>')
def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('deleted done!', 'success')
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

#manager_analysis
@app.route("/analysis/<team_id>")
def analysis(team_id):
    conn = get_connection()
    cursor = conn.cursor()

    # Total tasks for this team
    cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE team_id = %s", (team_id,))
    total_tasks = cursor.fetchone()[0]

    # Pending tasks for this team
    cursor.execute("SELECT COUNT(*) AS pending FROM tasks WHERE status='pending' AND team_id = %s", (team_id,))
    pending_tasks = cursor.fetchone()[0]

    # Team leader email 
    cursor.execute("SELECT leader_email FROM teams WHERE team_id = %s", (team_id,))
    row = cursor.fetchone()
    leader_email = row[0] if row else "N/A"

    # Number of members in this team
    cursor.execute("SELECT COUNT(*) FROM team_members WHERE team_id = %s", (team_id,))
    member_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT tm.member_email, COUNT(t.id) AS task_count
        FROM team_members tm
        LEFT JOIN tasks t
               ON t.team_id = tm.team_id
              AND t.email = tm.member_email
        WHERE tm.team_id = %s
        GROUP BY tm.member_email
    """, (team_id,))
    member_rows = cursor.fetchall()

    # Convert tuples -> dicts so m.member_email / m.task_count
    members = [{"member_email": r[0], "task_count": int(r[1] or 0)} for r in member_rows]

    conn.close()

    return render_template(
        "analysis.html",
        team_id=team_id,
        total=total_tasks,
        pending=pending_tasks,
        leader_email=leader_email,   
        member_count=member_count,   
        members=members              
    )

#leader_analysis
@app.route('/leader_analysis')
def leader_analysis():
    if "team_id" not in session:
        flash("something went wrong while fetching the team details")
        return redirect(url_for("leader_dashboard"))
    
    team_id = session.get('team_id')

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT tm.member_email,COUNT(t.id) AS total_tasks,
    SUM(CASE WHEN t.status = 'complete' THEN 1 ELSE 0 END) AS completed_tasks,
    SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) AS pending_tasks
    FROM team_members tm LEFT JOIN tasks t 
    ON tm.member_email = t.email AND tm.team_id = t.team_id
    WHERE tm.team_id = %s   -- pass your team_id here
    GROUP BY tm.member_email;
    """,(team_id,))
    data = cursor.fetchall()
    cursor.close()
   
    return render_template('teamdetails.html', team=data)

if __name__ == '__main__':
    app.run(debug=True)
