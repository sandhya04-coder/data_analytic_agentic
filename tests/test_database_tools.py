
from tools.database_tools import (
    get_database_overview,
    get_table_schema,
    get_table_relationships,
    profile_table
)


print("\n1. DATABASE OVERVIEW")
print(get_database_overview.invoke({}))


print("\n2. ORDERS TABLE SCHEMA")
print(get_table_schema.invoke({
    "table_name": "Orders"
}))


print("\n3. TABLE RELATIONSHIPS")
relationships = get_table_relationships.invoke({})

for relationship in relationships:
    print(relationship)


print("\n4. ORDERS TABLE PROFILE")
print(profile_table.invoke({
    "table_name": "Orders",
    "sample_size": 3
}))
