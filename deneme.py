import os, pyodbc
from passlib.hash import bcrypt
from dotenv import load_dotenv

load_dotenv()

conn = pyodbc.connect(os.getenv("MSSQL_CONN"))
cur = conn.cursor()
cur.execute("""
    SELECT PasswordHash FROM dbo.Users
    WHERE LOWER(LTRIM(RTRIM(Email)))=LOWER(LTRIM(RTRIM(?)))
""", ('furkan.goz@kocaeli.edu.tr',))
row = cur.fetchone()
h = (row[0] or '').strip()

print("hash_len:", len(h))
print("verify(9851):", bcrypt.verify('9851', h))  # denediğin şifreyi buraya yaz
