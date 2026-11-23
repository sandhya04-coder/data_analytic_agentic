
from tools.sql_tools import execute_sql, validate_sql

from sqlalchemy import text
from database.connection import get_engine


def test_sqlite_query_only():

    with get_engine().connect() as connection:

        connection.exec_driver_sql("PRAGMA query_only = ON")

        try:
            connection.execute(
                text("DELETE FROM Orders")
            )

            raise AssertionError("SQLite allowed a DELETE!")

        except Exception as error:
            if isinstance(error, AssertionError):
                raise

            print("\nSQLITE BLOCKED WRITE:", error)

    print("SQLITE READ-ONLY TEST PASSED!")


def test_sql_validation():

    safe_queries = [
        "SELECT * FROM Orders LIMIT 5",
        "SELECT COUNT(*) FROM Orders",
        "WITH recent_orders AS (SELECT * FROM Orders) SELECT * FROM recent_orders"
    ]

    unsafe_queries = [
        "DELETE FROM Orders",
        "UPDATE Orders SET ShipCity = 'Delhi'",
        "DROP TABLE Orders",
        "SELECT * FROM Orders; DELETE FROM Orders",
        "ALTER TABLE Orders ADD COLUMN test TEXT"
    ]

    for query in safe_queries:
        valid, message = validate_sql(query)
        print(f"SAFE: {query} -> {valid}")
        assert valid, message

    for query in unsafe_queries:
        valid, message = validate_sql(query)
        print(f"UNSAFE: {query} -> {valid}")
        assert not valid, f"Unsafe query accepted: {query}"


def test_sql_execution():

    result = execute_sql.invoke({
        "query": "SELECT COUNT(*) AS total_orders FROM Orders"
    })

    print("\nEXECUTION RESULT:", result)

    assert result["row_count"] == 1
    assert result["rows"][0]["total_orders"] == 830


def test_database_read_only():

    try:
        execute_sql.invoke({
            "query": "DELETE FROM Orders"
        })

        raise AssertionError("DELETE unexpectedly succeeded.")

    except Exception as error:
        print("\nREAD-ONLY PROTECTION:", error)
        print("DATABASE WRITE BLOCKED SUCCESSFULLY!")

    
def test_result_limit():

    result = execute_sql.invoke({
        "query": "SELECT * FROM Orders"
    })

    print("\nRESULT LIMIT TEST:")
    print("Rows returned:", result["row_count"])
    print("Truncated:", result["truncated"])
    print("Maximum rows:", result["max_rows"])

    assert result["row_count"] == 500
    assert result["truncated"] is True
    assert result["max_rows"] == 500

    print("RESULT LIMIT TEST PASSED!")




if __name__ == "__main__":
    test_sql_validation()
    test_sql_execution()
    test_database_read_only()
    test_sqlite_query_only()
    test_result_limit()
    print("\nALL SQL TOOL TESTS PASSED!")
