from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import uuid
import json
import google.generativeai as genai
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import firebase_admin
from firebase_admin import credentials, firestore
from gtts import gTTS
import os

# Initialize Flask app
app = Flask(__name__)

# Configure CORS to allow all origins
CORS(app)

# Initialize Firebase
cred = credentials.Certificate("serviceAccountKey.json")  # Replace with the actual path
firebase_admin.initialize_app(cred)
db = firestore.client()

# Configure Gemini API
genai.configure(api_key="AIzaSyDM2f7EoQ4-MlTyt-cxNITUMWrZxE9aoZ8")  # Replace with your Gemini API key
model = genai.GenerativeModel(model_name='gemini-1.5-flash-latest')

# Configure Selenium with webdriver-manager
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Automatically download and configure ChromeDriver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# Function to extract product details using Gemini API
def extract_product_details_with_gemini(body_content):
    try:
        prompt = (
            "Extract medicine details from the following text. "
            "Include fields like 'Product Name', 'Generic Name', 'Brand Name', "
            "'Manufacturer', 'Date of Manufacturing', 'Date of Expiry'."
            "Return the result in strict JSON format without extra text. "
            "Here is the text: " + body_content
        )

        response = model.generate_content([prompt, body_content])

        if response.candidates and len(response.candidates) > 0:
            generated_text = response.candidates[0].content.parts[0].text.strip()

            # Ensure proper JSON extraction
            generated_text = generated_text.replace("```json", "").replace("```", "").strip()
            extracted_data = json.loads(generated_text)

            return extracted_data

        return None
    except json.JSONDecodeError as e:
        print(f"JSON Parsing Error: {e}")
        return None
    except Exception as e:
        print(f"Error extracting product details: {e}")
        return None

# Function to generate a brief description and uses of the product
def generate_product_description(product_data):
    try:
        prompt = (
            f"Summarize the following product details in a simple and user-friendly way: {product_data}. "
            "Briefly mention the product name, its key ingredients, manufacturer, and expiry details in two short sentences. "
            "End with a friendly note explaining its main use in an easy-to-understand manner."
        )

        response = model.generate_content(prompt)

        if response.candidates and len(response.candidates) > 0:
            description = response.candidates[0].content.parts[0].text.strip()
            return description

        return None
    except Exception as e:
        print(f"Error generating product description: {e}")
        return None

# Store product details in Firebase
def store_in_firebase(product_data):
    try:
        uid = str(uuid.uuid4())  # Generate unique ID
        product_data["UID"] = uid
        db.collection("products").document(uid).set(product_data)
        return uid
    except Exception as e:
        print(f"Error storing in Firebase: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_qr', methods=['POST'])
def process_qr():
    try:
        qr_data = request.form.get('qr_data')

        if not qr_data:
            return jsonify({"status": "error", "message": "Missing QR data."}), 400

        # Fetch the HTML content of the link using Selenium
        print(f"Fetching content from: {qr_data}")
        driver.get(qr_data)

        # Wait for the page to load and handle dynamic content
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div, table, span'))
            )
        except Exception as e:
            print(f"Error waiting for page to load: {e}")
            return jsonify({"status": "error", "message": "Failed to load page content."}), 500

        # Get the page source
        page_source = driver.page_source

        # Parse the page source with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')

        # Remove unnecessary tags
        for tag in soup(['script', 'style', 'nav', 'footer', 'head', 'meta', 'link']):
            tag.decompose()

        # Extract text from the body
        body_content = soup.get_text(separator='\n')

        # Clean the text
        cleaned_content = "\n".join([line.strip() for line in body_content.splitlines() if line.strip()])

        print("Cleaned body content extracted successfully.")

        # Extract medicine details using Gemini API
        print("Extracting product details with Gemini API...")
        product_data = extract_product_details_with_gemini(cleaned_content)

        if not product_data:
            print("Failed to extract product details.")
            return jsonify({"status": "error", "message": "Failed to extract product details."}), 500

        # Generate a brief description and uses of the product
        print("Generating product description...")
        description = generate_product_description(product_data)

        if not description:
            print("Failed to generate product description.")
            return jsonify({"status": "error", "message": "Failed to generate product description."}), 500

        # Store the extracted data in Firebase
        print("Storing data in Firebase...")
        uid = store_in_firebase(product_data)

        if uid is None:
            print("Failed to store product data in Firebase.")
            return jsonify({"status": "error", "message": "Failed to store product data in Firebase."}), 500

        # Return success response with extracted data and description
        print("Successfully processed QR code.")
        return render_template('results.html', data=product_data, description=description)

    except Exception as e:
        print(f"Error in process_qr: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/translate', methods=['POST'])
def translate():
    data = request.json
    text = data.get('text')
    lang = data.get('lang')

    if not text or not lang:
        return jsonify({"error": "Missing text or language."}), 400

    # Ensure the static folder exists
    if not os.path.exists('static'):
        os.makedirs('static')

    # Define a prompt for Gemini to translate the text
    prompt = (
        f"Translate the following text into {lang}. "
        f"If the text is already in {lang}, return it as is. "
        f"Do not add any extra explanations or notes. "
        f"Here is the text: {text}"
    )

    # Use Gemini API to translate the text
    try:
        response = model.generate_content(prompt)
        if response.candidates and len(response.candidates) > 0:
            translated_text = response.candidates[0].content.parts[0].text.strip()
        else:
            return jsonify({"error": "Failed to translate text."}), 500
    except Exception as e:
        print(f"Error translating text: {e}")
        return jsonify({"error": "Failed to translate text."}), 500

    # Convert the translated text to audio using gTTS
    try:
        tts = gTTS(translated_text, lang=lang)
        audio_file = f"static/translated_{lang}.mp3"  # Save in the static folder
        tts.save(audio_file)
    except Exception as e:
        print(f"Error generating audio: {e}")
        return jsonify({"error": "Failed to generate audio."}), 500

    # Return the translated text and audio file path
    return jsonify({
        "translatedText": translated_text,
        "audioFile": audio_file
    })

if __name__ == '__main__':
    app.run(debug=True)