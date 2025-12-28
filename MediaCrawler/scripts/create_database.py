from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db_names = client.list_database_names()

if "media_crawler_db" not in db_names:
    db = client["media_crawler_db"]
    print("Database 'media_crawler_db' created.")
else:
    print("Database 'media_crawler_db' already exists.")


# 添加：创建集合（如果不存在
db = client["media_crawler_db"]
collection_names = db.list_collection_names()
collections_to_create = ["hot_trends", "posts", "laws"]

for col_name in collections_to_create:
    if col_name not in collection_names:
        db.create_collection(col_name)
        print(f"Collection '{col_name}' created.")
    else:
        print(f"Collection '{col_name}' already exists.")

