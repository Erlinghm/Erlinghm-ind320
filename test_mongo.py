import os
import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.environ["MONGODB_URI"]
client = MongoClient(uri, tlsCAFile=certifi.where())

# The ping command is the standard way to verify a connection works
client.admin.command("ping")
print("Connected to MongoDB successfully!")
print("Databases visible:", client.list_database_names())
