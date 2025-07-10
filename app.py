from flask import Flask, render_template, request, redirect, session, url_for, flash
from datetime import datetime
import mysql.connector
import hashlib
from config import DB_CONFIG

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


# ---------------- ROOT ----------------
@app.route('/')
def home():
    return redirect('/login')


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form.get('username')
        raw_password = request.form.get('password')

        if not username or not raw_password:
            error = "Both fields are required."
        else:
            hashed_password = hashlib.sha256(raw_password.encode()).hexdigest()
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)

                # Validate user
                cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, hashed_password))
                user = cursor.fetchone()

                if user:
                    session['user_id'] = user['id']
                    session['role'] = user['role']

                    if user['role'] == 'student':
                        cursor.close()
                        conn.close()
                        return redirect(url_for('student_home'))

                    elif user['role'] == 'teacher':
                        # Check if teacher is a class teacher
                        cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user['id'],))
                        teacher = cursor.fetchone()

                        if teacher:
                            teacher_id = teacher['id']
                            cursor.execute("SELECT * FROM classes WHERE class_teacher_id = %s", (teacher_id,))
                            assigned_class = cursor.fetchone()

                            cursor.close()
                            conn.close()

                            if assigned_class:
                                session['is_class_teacher'] = True
                                return render_template('teacher/choose_path.html')

                        # If not a class teacher
                        return redirect(url_for('teacher_dashboard'))

                    elif user['role'] == 'admin':
                        cursor.close()
                        conn.close()
                        return redirect(url_for('admin_dashboard'))

                    else:
                        error = "Unauthorized user role."

                else:
                    error = "Invalid username or password."

            except Exception as e:
                error = f"An error occurred: {str(e)}"

    return render_template('login.html', error=error)


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        raw_password = request.form['password']
        hashed_password = hashlib.sha256(raw_password.encode()).hexdigest()
        role = request.form['role']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check duplicate usernames
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            error = "Username already exists"
        else:
            try:
                # Insert into users
                cursor.execute(
                    "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
                    (username, email, hashed_password, role)
                )
                user_id = cursor.lastrowid

                if role == 'teacher':
                    teacher_name = request.form['teacher_name']
                    staff_no = request.form['staff_no']
                    contact = request.form['contact']
                    cursor.execute(
                        "INSERT INTO teachers (name, staff_no, contact, user_id) VALUES (%s, %s, %s, %s)",
                        (teacher_name, staff_no, contact, user_id)
                    )

                elif role == 'student':
                    student_name = request.form['student_name']
                    admission_no = request.form['admission_no']
                    class_id = request.form['class_id']
                    next_of_kin = request.form['next_of_kin']
                    kin_contact = request.form['next_of_kin_contact']
                    cursor.execute(
                        "INSERT INTO students (name, admission_no, class_id, next_of_kin, next_of_kin_contact, user_id) VALUES (%s, %s, %s, %s, %s, %s)",
                        (student_name, admission_no, class_id, next_of_kin, kin_contact, user_id)
                    )

                conn.commit()
                return redirect('/login')
            except Exception as e:
                conn.rollback()
                error = "Registration failed: " + str(e)
            finally:
                cursor.close()
                conn.close()

    # Load classes for student dropdown
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, stream FROM classes")
    class_list = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('register.html', error=error, class_list=class_list)



# ---------------- STUDENT ROUTES ----------------
@app.route('/student/home')
def student_home():
    if session.get('role') != 'student':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.*, c.name AS class_name, c.stream 
        FROM students s 
        JOIN classes c ON s.class_id = c.id 
        WHERE s.user_id = %s
    """, (user_id,))
    student = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('student/home.html', student=student)


@app.route('/student/profile', methods=['GET', 'POST'])
def student_profile():
    if session.get('role') != 'student':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get list of all classes for dropdown
    cursor.execute("SELECT id, name, stream FROM classes")
    classes = cursor.fetchall()

    if request.method == 'POST':
        name = request.form['name']
        admission_no = request.form['admission_no']
        next_of_kin = request.form['next_of_kin']
        next_of_kin_contact = request.form['next_of_kin_contact']
        email = request.form['email']
        class_id = request.form['class_id']

        try:
            # Update student info
            cursor.execute("""
                UPDATE students
                SET name=%s, admission_no=%s, next_of_kin=%s, next_of_kin_contact=%s, class_id=%s
                WHERE user_id=%s
            """, (name, admission_no, next_of_kin, next_of_kin_contact, class_id, user_id))

            # Update email in users table
            cursor.execute("""
                UPDATE users SET email=%s WHERE id=%s
            """, (email, user_id))

            conn.commit()
            flash("Profile updated successfully!")
            return redirect('/student/profile')

        except Exception as e:
            conn.rollback()
            flash(f"Update failed: {str(e)}")

    # Fetch student data
    cursor.execute("""
        SELECT s.name, s.admission_no, s.class_id, c.name AS class_name,
               s.next_of_kin, s.next_of_kin_contact, u.email
        FROM students s
        JOIN users u ON s.user_id = u.id
        JOIN classes c ON s.class_id = c.id
        WHERE s.user_id = %s
    """, (user_id,))
    
    student = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('student/profile.html', student=student, classes=classes)


@app.route('/student/results')
def student_results():
    if session.get('role') != 'student':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get student info
    cursor.execute("""
        SELECT s.*, c.name AS class_name, c.stream 
        FROM students s
        JOIN classes c ON s.class_id = c.id 
        WHERE s.user_id = %s
    """, (user_id,))
    student = cursor.fetchone()

    if not student:
        cursor.close()
        conn.close()
        return render_template('student/results.html', error="Student data not found.", student=None, results=[])

    # Get results
    cursor.execute("""
        SELECT r.score, r.remarks, r.date_entered, sub.name AS subject
        FROM results r
        JOIN subjects sub ON r.subject_id = sub.id
        WHERE r.student_id = %s
    """, (student['id'],))
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('student/results.html', student=student, results=results)


@app.route('/teacher/subjects', methods=['GET', 'POST'])
def teacher_subjects():
    if session.get('role') != 'teacher':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get teacher_id from users table
    cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user_id,))
    teacher = cursor.fetchone()

    if not teacher:
        cursor.close()
        conn.close()
        return render_template('teacher/subjects.html', error="Teacher not found.", assignments=[], subjects=[], classes=[])

    teacher_id = teacher['id']

    # Add new assignment
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        class_id = request.form.get('class_id')

        if subject_id and class_id:
            cursor.execute("""
                SELECT * FROM teacher_subjects 
                WHERE teacher_id = %s AND subject_id = %s AND class_id = %s
            """, (teacher_id, subject_id, class_id))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute("""
                    INSERT INTO teacher_subjects (teacher_id, subject_id, class_id)
                    VALUES (%s, %s, %s)
                """, (teacher_id, subject_id, class_id))
                conn.commit()

    # Handle deletion
    delete_id = request.args.get('delete')
    if delete_id:
        cursor.execute("""
            DELETE FROM teacher_subjects 
            WHERE id = %s AND teacher_id = %s
        """, (delete_id, teacher_id))
        conn.commit()
        return redirect('/teacher/subjects')

    # Get assigned subject-class pairs
    cursor.execute("""
        SELECT ts.id, s.name AS subject, c.name AS class_name, c.stream 
        FROM teacher_subjects ts
        JOIN subjects s ON ts.subject_id = s.id
        JOIN classes c ON ts.class_id = c.id
        WHERE ts.teacher_id = %s
    """, (teacher_id,))
    assignments = cursor.fetchall()

    # Dropdown options
    cursor.execute("SELECT id, name FROM subjects")
    subjects = cursor.fetchall()

    cursor.execute("SELECT id, name, stream FROM classes")
    classes = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'teacher/subjects.html',
        assignments=assignments,
        subjects=subjects,
        classes=classes
    )

@app.route('/student/fees', methods=['GET', 'POST'])
def student_fees():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session.get('student_id')
    current_year = datetime.now().year
    current_term = 'Term 2'  # optionally fetch from settings

    # Connect to DB
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor(dictionary=True)

    # Get current term's fee status
    cursor.execute("""
        SELECT * FROM fees 
        WHERE student_id = %s AND term = %s AND year = %s
    """, (student_id, current_term, current_year))
    current_fee = cursor.fetchone()

    # Get full payment history
    cursor.execute("""
        SELECT f.term, f.year, fp.payment_date, fp.amount, fp.payment_method, fp.receipt_no
        FROM fee_payments fp
        JOIN fees f ON f.id = fp.fee_id
        WHERE f.student_id = %s
        ORDER BY fp.payment_date DESC
    """, (student_id,))
    payment_history = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('student/fees.html',
                           current_fee=current_fee,
                           payment_history=payment_history,
                           term=current_term,
                           year=current_year)

@app.route('/teacher/enter_results', methods=['GET', 'POST'])
def teacher_enter_results():
    if session.get('role') != 'teacher':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get teacher ID
    cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user_id,))
    teacher = cursor.fetchone()
    if not teacher:
        cursor.close()
        conn.close()
        return render_template('teacher/enter_results.html', error="Teacher not found.", assignments=[], exams=[], students=[])

    teacher_id = teacher['id']

    # Get all subjects & classes assigned to this teacher
    cursor.execute("""
        SELECT ts.id, ts.subject_id, ts.class_id, s.name AS subject_name, c.name AS class_name, c.stream 
        FROM teacher_subjects ts 
        JOIN subjects s ON ts.subject_id = s.id 
        JOIN classes c ON ts.class_id = c.id 
        WHERE ts.teacher_id = %s
    """, (teacher_id,))
    assignments = cursor.fetchall()

    # Get all exams
    cursor.execute("SELECT id, name, term, year FROM exams")
    exams = cursor.fetchall()

    students = []
    selected_class_id = None
    selected_subject_id = None
    selected_exam_id = None

    if request.method == 'POST':
        selected_subject_id = request.form['subject_id']
        selected_class_id = request.form['class_id']
        selected_exam_id = request.form['exam_id']

        # Get students in selected class
        cursor.execute("SELECT id, name FROM students WHERE class_id = %s", (selected_class_id,))
        students = cursor.fetchall()

        # Save results if score inputs are present
        if 'scores' in request.form:
            for student in students:
                sid = str(student['id'])
                score = request.form.get(f"score_{sid}")
                remarks = request.form.get(f"remarks_{sid}")

                # Check if result already exists (optional: prevent duplicate)
                cursor.execute("""
                    SELECT * FROM results
                    WHERE student_id = %s AND subject_id = %s AND exam_id = %s
                """, (sid, selected_subject_id, selected_exam_id))
                existing = cursor.fetchone()

                if not existing:
                    cursor.execute("""
                        INSERT INTO results (student_id, subject_id, teacher_id, exam_id, score, remarks, date_entered)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """, (sid, selected_subject_id, teacher_id, selected_exam_id, score, remarks))
                    conn.commit()

    cursor.close()
    conn.close()

    return render_template('teacher/enter_results.html',
                           assignments=assignments,
                           exams=exams,
                           students=students,
                           selected_class_id=selected_class_id,
                           selected_subject_id=selected_subject_id,
                           selected_exam_id=selected_exam_id)


@app.route('/teacher/edit_results', methods=['GET', 'POST'])
def teacher_edit_results():
    if session.get('role') != 'teacher':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get teacher ID
    cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user_id,))
    teacher = cursor.fetchone()
    if not teacher:
        cursor.close()
        conn.close()
        return render_template('teacher/edit_results.html', error="Teacher not found.")

    teacher_id = teacher['id']

    # Fetch only subjects and classes assigned to this teacher
    cursor.execute("""
        SELECT ts.subject_id, ts.class_id, s.name AS subject_name, c.name AS class_name, c.stream
        FROM teacher_subjects ts
        JOIN subjects s ON ts.subject_id = s.id
        JOIN classes c ON ts.class_id = c.id
        WHERE ts.teacher_id = %s
    """, (teacher_id,))
    assignments = cursor.fetchall()

    # Fetch available exams
    cursor.execute("SELECT id, name, term, year FROM exams")
    exams = cursor.fetchall()

    results = []
    selected_subject_id = None
    selected_class_id = None
    selected_exam_id = None

    if request.method == 'POST':
        selected_subject_id = int(request.form['subject_id'])
        selected_class_id = int(request.form['class_id'])
        selected_exam_id = int(request.form['exam_id'])

        # Confirm subject/class is assigned to the teacher
        valid_assignment = any(
            a['subject_id'] == selected_subject_id and a['class_id'] == selected_class_id
            for a in assignments
        )
        if not valid_assignment:
            cursor.close()
            conn.close()
            return render_template('teacher/edit_results.html',
                                   assignments=assignments,
                                   exams=exams,
                                   error="You are not assigned to this subject and class.")

        if 'update' in request.form:
            # Update each result
            student_ids = request.form.getlist('student_id')
            for sid in student_ids:
                score = request.form.get(f"score_{sid}")
                remarks = request.form.get(f"remarks_{sid}")
                cursor.execute("""
                    UPDATE results
                    SET score = %s, remarks = %s
                    WHERE student_id = %s AND subject_id = %s AND exam_id = %s AND teacher_id = %s
                """, (score, remarks, sid, selected_subject_id, selected_exam_id, teacher_id))
            conn.commit()

        # Retrieve results
        cursor.execute("""
            SELECT r.student_id, st.name AS student_name, r.score, r.remarks
            FROM results r
            JOIN students st ON r.student_id = st.id
            WHERE r.subject_id = %s AND r.exam_id = %s AND r.teacher_id = %s AND st.class_id = %s
        """, (selected_subject_id, selected_exam_id, teacher_id, selected_class_id))
        results = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('teacher/edit_results.html',
                           assignments=assignments,
                           exams=exams,
                           results=results,
                           selected_class_id=selected_class_id,
                           selected_subject_id=selected_subject_id,
                           selected_exam_id=selected_exam_id)

@app.route('/teacher/performance', methods=['GET', 'POST'])
def teacher_performance():
    if session.get('role') != 'teacher':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get teacher ID
    cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user_id,))
    teacher = cursor.fetchone()
    if not teacher:
        return "Teacher not found"

    teacher_id = teacher['id']

    # Get teacher's assignments
    cursor.execute("""
        SELECT ts.subject_id, s.name AS subject_name,
               ts.class_id, c.name AS class_name, c.stream
        FROM teacher_subjects ts
        JOIN subjects s ON ts.subject_id = s.id
        JOIN classes c ON ts.class_id = c.id
        WHERE ts.teacher_id = %s
    """, (teacher_id,))
    assignments = cursor.fetchall()

    # Get all exams
    cursor.execute("SELECT id, name FROM exams")
    exams = cursor.fetchall()

    selected_exam_id = request.form.get('exam_id') if request.method == 'POST' else None

    charts_data = []

    if selected_exam_id:
        selected_exam_id = int(selected_exam_id)
        for assignment in assignments:
            cursor.execute("""
                SELECT st.name AS student_name, r.score
                FROM results r
                JOIN students st ON r.student_id = st.id
                WHERE r.exam_id = %s AND r.subject_id = %s AND st.class_id = %s
            """, (selected_exam_id, assignment['subject_id'], assignment['class_id']))
            scores = cursor.fetchall()

            if scores:
                charts_data.append({
                    'title': f"{assignment['subject_name']} - {assignment['class_name']} {assignment['stream']}",
                    'labels': [s['student_name'] for s in scores],
                    'scores': [s['score'] for s in scores]
                })

    cursor.close()
    conn.close()

    return render_template('teacher/performance.html',
                           exams=exams,
                           charts_data=charts_data,
                           selected_exam_id=selected_exam_id)


# ---------------- TEACHER ----------------
@app.route('/teacher/dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Step 1: Get the teacher's ID from the teachers table
    cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user_id,))
    teacher = cursor.fetchone()

    if not teacher:
        cursor.close()
        conn.close()
        return render_template('teacher/dashboard.html', assignments=[], error="Teacher profile not found.")

    teacher_id = teacher['id']

    # Step 2: Fetch assigned subjects and classes from teacher_subjects
    cursor.execute("""
        SELECT ts.id, s.name AS subject, c.name AS class_name, c.stream 
        FROM teacher_subjects ts 
        JOIN subjects s ON ts.subject_id = s.id 
        JOIN classes c ON ts.class_id = c.id 
        WHERE ts.teacher_id = %s
    """, (teacher_id,))
    assignments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('teacher/dashboard.html', assignments=assignments)

@app.route('/teacher/class-management', methods=['GET', 'POST'])
def class_management():
    if session.get('role') != 'teacher':
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get the teacher's record
    cursor.execute("SELECT id FROM teachers WHERE user_id = %s", (user_id,))
    teacher = cursor.fetchone()

    if not teacher:
        cursor.close()
        conn.close()
        return render_template('teacher/class_management.html', error="Teacher record not found")

    teacher_id = teacher['id']

    # Get the class assigned to the teacher
    cursor.execute("SELECT * FROM classes WHERE class_teacher_id = %s", (teacher_id,))
    class_info = cursor.fetchone()

    if not class_info:
        cursor.close()
        conn.close()
        return render_template('teacher/class_management.html', error="No class assigned to this teacher")

    class_id = class_info['id']

    # Add a new student to the class
    if request.method == 'POST':
        name = request.form['name']
        admission_no = request.form['admission_no']
        next_of_kin = request.form['next_of_kin']
        next_of_kin_contact = request.form['next_of_kin_contact']

        try:
            cursor.execute("""
                INSERT INTO students (name, admission_no, class_id, next_of_kin, next_of_kin_contact)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, admission_no, class_id, next_of_kin, next_of_kin_contact))
            conn.commit()
        except Exception as e:
            conn.rollback()
            return render_template('teacher/class_management.html', error=f"Error: {e}", students=[], class_info=class_info)

    # Fetch students in the class
    cursor.execute("SELECT * FROM students WHERE class_id = %s", (class_id,))
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('teacher/class_management.html', students=students, class_info=class_info)


@app.route('/teacher/remove-student/<int:student_id>', methods=['POST'])
def remove_student(student_id):
    if session.get('role') != 'teacher':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Delete the student
    cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for('class_management'))

# ---------- ADMIN DASHBOARD ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM students")
    student_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM teachers")
    teacher_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    return render_template('admin/dashboard.html', student_count=student_count, teacher_count=teacher_count)


# ---------- accounts ----------#
@app.route('/admin/accounts')
@app.route('/admin/accounts/class/<int:class_id>', methods=['GET', 'POST'])
def admin_accounts(class_id=None):
    if session.get('role') != 'admin':
        return redirect('/login')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Handle fee update
    if request.method == 'POST':
        fee_id = request.form.get('fee_id')

        try:
            amount_due = float(request.form.get('amount_due') or 0)
            amount_paid = float(request.form.get('amount_paid') or 0)
        except ValueError:
            flash("Please enter valid numbers for amount due and amount paid.", "danger")
            return redirect(request.path)

        status = request.form.get('status') or 'Unpaid'

        cursor.execute("""
            UPDATE fees SET amount_due = %s, amount_paid = %s, status = %s
            WHERE id = %s
        """, (amount_due, amount_paid, status, fee_id))
        db.commit()
        flash('Fee record updated successfully.', 'success')
        return redirect(request.path)

    # Fetch class list
    cursor.execute("SELECT id, name, stream FROM classes")
    classes = cursor.fetchall()

    student_fees = []
    if class_id:
        cursor.execute("""
            SELECT s.id AS student_id, s.name AS student_name,
                   f.id AS fee_id, f.term, f.year,
                   f.amount_due, f.amount_paid, f.status,
                   c.name AS class_name, c.stream
            FROM students s
            JOIN classes c ON s.class_id = c.id
            LEFT JOIN fees f ON s.id = f.student_id
            WHERE s.class_id = %s
            ORDER BY s.name ASC
        """, (class_id,))
        student_fees = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('admin/accounts.html',
                           classes=classes,
                           student_fees=student_fees,
                           selected_class_id=class_id)


@app.route('/admin/accounts/payments/<int:student_id>')
def admin_fee_payments(student_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT f.term, f.year, fp.amount, fp.payment_date, fp.payment_method, fp.receipt_no
        FROM fee_payments fp
        JOIN fees f ON f.id = fp.fee_id
        WHERE f.student_id = %s
        ORDER BY fp.payment_date DESC
    """, (student_id,))
    payments = cursor.fetchall()

    cursor.execute("SELECT name FROM students WHERE id = %s", (student_id,))
    student = cursor.fetchone()

    cursor.close()
    db.close()

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('admin_accounts'))

    return render_template('admin/fee_payments.html', payments=payments, student=student)


# ---------- STAFF ----------
@app.route('/admin/staff', methods=['GET', 'POST'])
def admin_staff():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Add staff
    if request.method == 'POST':
        name = request.form['name']
        staff_no = request.form['staff_no']
        position = request.form['position']
        contact = request.form['contact']
        cursor.execute("""
            INSERT INTO staff (name, staff_no, position, contact)
            VALUES (%s, %s, %s, %s)
        """, (name, staff_no, position, contact))
        conn.commit()

    # Fetch staff list
    cursor.execute("SELECT * FROM staff")
    staff_list = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('admin/staff.html', staff=staff_list)

@app.route('/admin/staff/delete/<int:id>', methods=['POST'])
def delete_staff(id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM staff WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/admin/staff')



# ---------- CLASSES ----------
# ---------------- CLASSES TAB ----------------
@app.route('/admin/classes', methods=['GET', 'POST'])
def admin_classes():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Add new class with teacher (if form submitted)
    if request.method == 'POST':
        name = request.form['name']
        stream = request.form['stream']
        teacher_id = request.form.get('class_teacher_id')
        teacher_id = teacher_id if teacher_id != 'none' else None

        cursor.execute(
            "INSERT INTO classes (name, stream, class_teacher_id) VALUES (%s, %s, %s)",
            (name, stream, teacher_id)
        )
        conn.commit()

    # Fetch all classes with teacher names
    cursor.execute("""
        SELECT c.*, t.name AS teacher_name 
        FROM classes c 
        LEFT JOIN teachers t ON c.class_teacher_id = t.id
    """)
    classes = cursor.fetchall()

    # Get all teachers for dropdown
    cursor.execute("SELECT id, name FROM teachers")
    teachers = cursor.fetchall()

    # Fetch all students grouped by class
    cursor.execute("""
        SELECT s.*, c.id AS class_id, c.name AS class_name, c.stream 
        FROM students s
        JOIN classes c ON s.class_id = c.id
    """)
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    # Group students by class_id
    student_map = {}
    for s in students:
        student_map.setdefault(s['class_id'], []).append(s)

    return render_template('admin/classes.html', classes=classes, teachers=teachers, student_map=student_map)


@app.route('/admin/classes/delete/<int:id>', methods=['POST'])
def delete_class(id):
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM classes WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/admin/classes')


@app.route('/admin/classes/update/<int:class_id>', methods=['POST'])
def update_class_teacher(class_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    # FIXED: get the correct field name from form
    new_teacher_id = request.form.get('class_teacher_id')
    if new_teacher_id == '' or new_teacher_id == 'none':
        new_teacher_id = None

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE classes SET class_teacher_id = %s WHERE id = %s", (new_teacher_id, class_id))
    conn.commit()
    flash("Class teacher updated successfully!")
    cursor.close()
    conn.close()

    return redirect('/admin/classes')


# ---------- EXAMS ----------
@app.route('/admin/exams', methods=['GET', 'POST'])
def admin_exams():
    if session.get('role') != 'admin':
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        term = request.form['term']
        year = request.form['year']
        class_id = request.form['class_id']
        exam_date = request.form['exam_date']

        cursor.execute("""
            INSERT INTO exams (name, term, year, class_id, exam_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, term, year, class_id, exam_date))
        conn.commit()

    # Fetch exams
    cursor.execute("""
        SELECT e.*, c.name AS class_name, c.stream
        FROM exams e
        JOIN classes c ON e.class_id = c.id
        ORDER BY e.exam_date DESC
    """)
    exams = cursor.fetchall()

    # Fetch results grouped by exam
    exam_results = {}
    for exam in exams:
        cursor.execute("""
            SELECT s.name AS student_name, r.score, sub.name AS subject
            FROM results r
            JOIN students s ON r.student_id = s.id
            JOIN subjects sub ON r.subject_id = sub.id
            WHERE r.exam_id = %s
        """, (exam['id'],))
        exam_results[exam['id']] = cursor.fetchall()

    # Fetch class list for form
    cursor.execute("SELECT * FROM classes")
    classes = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin/exams.html', exams=exams, classes=classes, exam_results=exam_results)


# ---------- RESULTS ----------
@app.route('/admin/results')
def admin_results():
    if session.get('role') != 'admin':
        return redirect('/login')

    import mysql.connector
    from flask import request

    connection = mysql.connector.connect(
        host='127.0.0.1',
        user='root',
        password='0795438822',
        database='school'
    )
    cursor = connection.cursor(dictionary=True)

    # Fetch all classes
    cursor.execute("SELECT id, name, stream FROM classes")
    classes = cursor.fetchall()

    selected_class_id = request.args.get('class_id')
    results = []

    if selected_class_id:
        query = """
        SELECT 
            s.name AS student_name,
            sub.name AS subject_name,
            e.name AS exam_name,
            e.term,
            e.year,
            r.score,
            r.remarks
        FROM results r
        JOIN students s ON r.student_id = s.id
        JOIN subjects sub ON r.subject_id = sub.id
        JOIN exams e ON r.exam_id = e.id
        WHERE s.class_id = %s
        ORDER BY s.name, e.year DESC, e.term, sub.name
        """
        cursor.execute(query, (selected_class_id,))
        results = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template('admin/results.html', classes=classes, results=results, selected_class_id=selected_class_id)


# ---------- STATS ----------
@app.route('/admin/stats')
def admin_stats():
    if session.get('role') != 'admin':
        return redirect('/login')

    connection = mysql.connector.connect(
        host='127.0.0.1',
        user='root',
        password='0795438822',
        database='school'
    )
    cursor = connection.cursor()

    # Get statistics
    cursor.execute("SELECT COUNT(*) FROM students")
    student_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM teachers")
    teacher_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM classes")
    class_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM subjects")
    subject_count = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        'admin/stats.html',
        student_count=student_count,
        teacher_count=teacher_count,
        class_count=class_count,
        subject_count=subject_count
    )

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(debug=True)
