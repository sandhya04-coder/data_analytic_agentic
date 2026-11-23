
from database.connection import test_connection, get_table_names

if test_connection():
    print("Database connected successfully!")

    tables = get_table_names()

    print(f"\nTotal tables found: {len(tables)}")

    for table in tables:
        print("-", table)

else:
    print("Database connection unsuccessful.")
