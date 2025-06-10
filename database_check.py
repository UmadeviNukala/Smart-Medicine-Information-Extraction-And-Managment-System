import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")  # Use the downloaded file
firebase_admin.initialize_app(cred)

# Get Firestore database reference
db = firestore.client()
print("Firebase Initialized Successfully!")