
from database.schema_inspector import SchemaInspector

inspector = SchemaInspector()

print("\n========== DATABASE TABLES ==========")

for table in inspector.get_all_tables():
    print(table)

print("\n========== TABLE COLUMNS ==========")

table_name = "Orders"

for column in inspector.get_table_columns(table_name):
    print(column)

print("\n========== PRIMARY KEYS ==========")

print(inspector.get_primary_keys(table_name))

print("\n========== FOREIGN KEYS ==========")

for fk in inspector.get_foreign_keys(table_name):
    print(fk)

print("\n========== DATABASE RELATIONSHIPS ==========")

for relationship in inspector.get_table_relationships():
    print(relationship)
