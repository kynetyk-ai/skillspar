import hashlib
import sqlite3


def login(username, password):
    """Authenticate user and return session token."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    cursor.execute(query)
    user = cursor.fetchone()
    if user:
        token = hashlib.md5(username.encode()).hexdigest()
        return {"status": "ok", "token": token}
    return {"status": "error", "message": "Invalid credentials"}


def reset_password(email):
    """Send password reset link."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET password = 'temp123' WHERE email = '{email}'")
    conn.commit()
    return "Password reset to temp123"
