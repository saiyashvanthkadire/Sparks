import os
import markdown
import base64
import json
import requests
import mysql.connector
from datetime import date as current_date
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
from openai import OpenAI
from dotenv import load_dotenv

try:
    import firebase_admin
    from firebase_admin import auth, credentials, firestore
    from google.cloud.firestore_v1 import FieldFilter
except ImportError:
    firebase_admin = None
    auth = None
    credentials = None
    firestore = None
    FieldFilter = None

load_dotenv()

app = Flask(__name__, template_folder='template')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'streak_spark_secret_key')

@app.after_request
def set_coop_header(response):
    response.headers['Cross-Origin-Opener-Policy'] = 'unsafe-none'
    return response

FIREBASE_WEB_API_KEY = os.environ.get('FIREBASE_WEB_API_KEY', '')
FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', '')
FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID', '')
FIREBASE_USE_APPLICATION_DEFAULT = os.environ.get('FIREBASE_USE_APPLICATION_DEFAULT', '').lower() == 'true'
firebase_db = None

# Initialize OpenAI Client
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY', 'dummy-key'))

def init_firebase():
    if firebase_admin is None:
        return None
    if not FIREBASE_SERVICE_ACCOUNT_PATH and not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') and not FIREBASE_USE_APPLICATION_DEFAULT:
        return None

    try:
        firebase_admin.get_app()
    except ValueError:
        options = {}
        if FIREBASE_PROJECT_ID:
            options['projectId'] = FIREBASE_PROJECT_ID

        if FIREBASE_SERVICE_ACCOUNT_PATH:
            cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred, options or None)
        else:
            firebase_admin.initialize_app(options=options or None)

    try:
        return firestore.client()
    except Exception as exc:
        print(f'Firebase is not ready yet: {exc}')
        return None

firebase_db = init_firebase()

def using_firebase():
    return firebase_db is not None

def serialize_daily_item(item):
    if isinstance(item.get('days'), str):
        item['days'] = json.loads(item['days'] or '[]')
    else:
        item['days'] = item.get('days') or []

    if isinstance(item.get('completed_dates'), str):
        item['completed_dates'] = json.loads(item['completed_dates'] or '[]')
    else:
        item['completed_dates'] = item.get('completed_dates') or []

    item['completed'] = bool(item['completed'])
    item['completedDates'] = item['completed_dates']
    return item

def firestore_item_from_doc(doc):
    item = doc.to_dict() or {}
    item['id'] = doc.id
    item.setdefault('completed', False)
    item.setdefault('completed_dates', [])
    item.setdefault('days', [])
    return serialize_daily_item(item)

def require_login_json():
    if 'loggedin' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return None

def split_saved_food_note(result_text):
    lines = (result_text or '').splitlines()
    title = lines[0].strip() if lines else 'Saved Food Recommendation'
    body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else result_text
    return title or 'Saved Food Recommendation', body or ''

# --- Authentication Routes ---

@app.route('/firebase-login', methods=['POST'])
def firebase_login():
    data = request.get_json()
    id_token = data.get('idToken')
    if not id_token:
        return jsonify({'error': 'Missing token'}), 400
    try:
        decoded = auth.verify_id_token(id_token)
        uid = decoded['uid']
        session['loggedin'] = True
        session['id'] = uid
        session['username'] = decoded.get('name') or decoded.get('email', '').split('@')[0]
        session['email'] = decoded.get('email', '')
        return jsonify({'success': True, 'redirect': '/index.html'})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 401

@app.route('/login.html', methods=['GET'])
@app.route('/login', methods=['GET'])
def login():
    return render_template('login.html')

@app.route('/signup.html', methods=['GET'])
@app.route('/signup', methods=['GET'])
def signup():
    return render_template('login.html', show_signup=True)

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

# --- Main Application Routes ---

@app.route('/')
@app.route('/home.html')
def home():
    return render_template('home.html')

@app.route('/index.html')
def index():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session.get('username'), email=session.get('email'))

@app.route('/index2.html')
def index2():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('index2.html')

@app.route('/medical.html', methods=['GET', 'POST'])
def medical():
    result, image_data, mime_type = "", None, None
    if request.method == 'POST' and 'image' in request.files:
        file = request.files['image']
        if file.filename != '':
            mime_type = file.mimetype
            image_bytes = file.read()
            image_data = base64.b64encode(image_bytes).decode('utf-8')
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe the contents of this image in detail. Please focus on visible features for educational purposes. Disclaimer: Do not provide a medical diagnosis or official medical advice."},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}
                        ]
                    }]
                )
                result = markdown.markdown(response.choices[0].message.content)
            except Exception as e:
                result = f"<p>Error processing image: {str(e)}</p>"
    return render_template('medical.html', result=result, image_data=image_data, mime_type=mime_type)

@app.route('/Food.html', methods=['GET', 'POST'])
def food():
    return render_template('Food.html', result="", image_data=None, mime_type=None)

@app.route('/save_food', methods=['POST'])
def save_food():
    if not session.get('loggedin'):
        return redirect(url_for('index'))
    user_id = session['id']
    result_text = request.form.get('result', '')
    visibility = request.form.get('visibility', 'private')
    note_title, note_body = split_saved_food_note(result_text)
    today = current_date.today().isoformat()

    firebase_db.collection('food_entries').add({
        'user_id': user_id,
        'image_data': request.form.get('image_data', ''),
        'analysis_result': result_text,
        'visibility': visibility,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    firebase_db.collection('daily_items').add({
        'user_id': user_id,
        'type': 'note',
        'title': note_title,
        'content': json.dumps({'body': note_body, 'tags': 'Food, Health', 'visibility': visibility}),
        'date': today,
        'days': [],
        'completed': False,
        'completed_dates': [],
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return redirect(url_for('index'))

# --- Catch-All Route for all other HTML pages ---

@app.route('/<page>.html')
def serve_html_pages(page):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template(f'{page}.html')

# --- API Routes ---

@app.route('/api/items/<item_type>', methods=['GET'])
def api_get_items(item_type):
    if 'loggedin' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['id']

    docs = (
        firebase_db.collection('daily_items')
        .where(filter=FieldFilter('user_id', '==', user_id))
        .where(filter=FieldFilter('type', '==', item_type))
        .stream()
    )
    return jsonify([firestore_item_from_doc(doc) for doc in docs])

@app.route('/api/items/item/<item_id>', methods=['GET'])
def get_item(item_id):
    unauthorized = require_login_json()
    if unauthorized:
        return unauthorized

    user_id = session['id']
    doc = firebase_db.collection('daily_items').document(item_id).get()
    if not doc.exists:
        return jsonify({'error': 'Item not found'}), 404
    item = doc.to_dict() or {}
    if item.get('user_id') != user_id:
        return jsonify({'error': 'Item not found'}), 404
    return jsonify(firestore_item_from_doc(doc))

@app.route('/api/items/toggle/<item_id>', methods=['POST'])
def toggle_item(item_id):
    unauthorized = require_login_json()
    if unauthorized:
        return unauthorized

    user_id = session['id']
    data = request.json or {}
    target_date = data.get('date', '')

    doc_ref = firebase_db.collection('daily_items').document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        return jsonify({'error': 'Item not found'}), 404

    item = doc.to_dict() or {}
    if item.get('user_id') != user_id:
        return jsonify({'error': 'Item not found'}), 404

    if item.get('type') in ('habit', 'tracker') and target_date:
        completed_dates = item.get('completed_dates') or []
        if target_date in completed_dates:
            completed_dates.remove(target_date)
        else:
            completed_dates.append(target_date)
        doc_ref.update({'completed_dates': completed_dates})
    else:
        doc_ref.update({'completed': not bool(item.get('completed'))})
    return jsonify({'success': True})

@app.route('/api/items', methods=['POST'])
def create_item():
    unauthorized = require_login_json()
    if unauthorized:
        return unauthorized

    user_id = session['id']
    data = request.json
    doc_ref = firebase_db.collection('daily_items').document()
    doc_ref.set({
        'user_id': user_id,
        'type': data.get('type'),
        'title': data.get('title'),
        'content': data.get('content', ''),
        'date': data.get('date', ''),
        'days': data.get('days', []),
        'completed': False,
        'completed_dates': [],
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return jsonify({'success': True, 'id': doc_ref.id})

@app.route('/api/items/<item_id>', methods=['PUT'])
def update_item(item_id):
    unauthorized = require_login_json()
    if unauthorized:
        return unauthorized

    user_id = session['id']
    data = request.json or {}
    title = data.get('title')

    if not title:
        return jsonify({'error': 'Title is required'}), 400

    doc_ref = firebase_db.collection('daily_items').document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        return jsonify({'error': 'Item not found'}), 404
    if (doc.to_dict() or {}).get('user_id') != user_id:
        return jsonify({'error': 'Item not found'}), 404
    doc_ref.update({
        'title': title,
        'content': data.get('content', ''),
        'date': data.get('date', ''),
        'days': data.get('days', []),
        'updated_at': firestore.SERVER_TIMESTAMP
    })
    return jsonify({'success': True, 'id': item_id})

@app.route('/api/items/date/<date>', methods=['GET'])
def get_items_by_date(date):
    unauthorized = require_login_json()
    if unauthorized:
        return unauthorized
    user_id = session['id']

    docs = (
        firebase_db.collection('daily_items')
        .where(filter=FieldFilter('user_id', '==', user_id))
        .where(filter=FieldFilter('date', '==', date))
        .stream()
    )
    return jsonify([firestore_item_from_doc(doc) for doc in docs])

@app.route('/api/items/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    unauthorized = require_login_json()
    if unauthorized:
        return unauthorized

    user_id = session['id']
    doc_ref = firebase_db.collection('daily_items').document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        return jsonify({'error': 'Item not found'}), 404
    if (doc.to_dict() or {}).get('user_id') != user_id:
        return jsonify({'error': 'Item not found'}), 404
    doc_ref.delete()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
