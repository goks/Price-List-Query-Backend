import pyodbc

SERVERNAME = r"GASERVER\BUSYSTDSQL"
DATABASENAME = "BusyComp0004_db12025"

def test_connection():
    try:
        conn_str = f"Driver={{SQL Server}};Server={SERVERNAME};Database={DATABASENAME};Trusted_Connection=yes;"
        conn = pyodbc.connect(conn_str)
        print("✅ Database connection successful!")
        conn.close()
        return True
    except pyodbc.OperationalError as e:
        if "Login timeout expired" in str(e) or "Named Pipes Provider" in str(e) or "Cannot open database" in str(e):
            print(f"❌ Database connection failed. Please check if the server '{SERVERNAME}' is accessible and the database '{DATABASENAME}' exists.")
            print(f"   Detailed error: {str(e)}")
        else:
            print(f"❌ Database connection error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unexpected database error: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing database connection...")
    test_connection()
