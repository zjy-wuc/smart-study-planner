import mysql.connector

conn = None
cursor = None

try:
    conn = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root",
        password="1234567890",
        database="smart_study_planner",
    )

    cursor = conn.cursor()
    cursor.execute("SELECT DATABASE()")

    result = cursor.fetchone()
    print("当前使用的数据库：", result[0])

except mysql.connector.Error as err:
    print("数据库操作失败：", err)

finally:
    if cursor is not None:
        cursor.close()

    if conn is not None and conn.is_connected():
        conn.close()

    print("数据库资源清理完成。")