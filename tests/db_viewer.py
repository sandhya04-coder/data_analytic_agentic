import pandas as pd
from sqlalchemy import inspect
from database.connection import get_engine

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

engine = get_engine()
insp = inspect(engine)
quote = engine.dialect.identifier_preparer.quote

for table in insp.get_table_names():
    cols = insp.get_columns(table)
    blobs = {c["name"] for c in cols if "BLOB" in str(c["type"]).upper()}
    keep = [quote(c["name"]) for c in cols if c["name"] not in blobs]

    count = pd.read_sql(f"SELECT COUNT(*) AS n FROM {quote(table)}", engine)["n"][0]
    print("=" * 80)
    print(f"{table}  ({count} rows)")
    print("columns:", ", ".join(f'{c["name"]} {c["type"]}' for c in cols))
    print(pd.read_sql(f"SELECT {', '.join(keep)} FROM {quote(table)} LIMIT 3", engine))

print("=" * 80)
print(pd.read_sql(
    'SELECT MIN(OrderDate) AS first_order, MAX(OrderDate) AS last_order FROM "Orders"',
    engine))