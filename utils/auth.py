import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_user(cursor, username, password):
    hashed_pw = hash_password(password)
    cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, hashed_pw))
    return cursor.fetchone()

def register_user(cursor, username, email, password, role):
    hashed_pw = hash_password(password)
    cursor.execute("INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
                   (username, email, hashed_pw, role))
