import cv2
import dlib
import numpy as np
import face_recognition
import imutils
from scipy.spatial import distance as dist
from imutils import face_utils
import os
import json
import base64
import time
import threading

from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit

# --- Configuration ---
SECRET_KEY = 'your_very_secret_key' # Change this!
KNOWN_FACES_DIR = 'known_faces'
USER_DATA_FILE = 'user_data.json'
DLIB_SHAPE_PREDICTOR = 'shape_predictor_68_face_landmarks.dat'

# Blink Detection Constants
BLINK_THRESH = 0.35 # Adjust this threshold based on your camera/lighting
BLINK_CONSEC_FRAMES = 2 # How many consecutive frames below threshold == blink

# Face Recognition Constants
FACE_REC_TOLERANCE = 0.6 # Lower is stricter

# PIN Entry Constants
PIN_LENGTH = 4
PIN_DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
PIN_CYCLE_DELAY = 1.5 # Seconds to highlight each digit

# --- Flask & SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
# Use eventlet for better concurrency with CV tasks
socketio = SocketIO(app, async_mode='eventlet')

# --- Load Models and Data ---
print("Loading dlib models...")
try:
    face_detector = dlib.get_frontal_face_detector()
    landmark_predictor = dlib.shape_predictor(DLIB_SHAPE_PREDICTOR)
    (L_start, L_end) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
    (R_start, R_end) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']
except Exception as e:
    print(f"Error loading dlib models: {e}")
    print(f"Ensure '{DLIB_SHAPE_PREDICTOR}' is in the correct directory.")
    exit()

print("Loading user data...")
if not os.path.exists(KNOWN_FACES_DIR):
    os.makedirs(KNOWN_FACES_DIR)

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Return empty dict if file is corrupt/empty
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_known_faces():
    known_encodings = []
    known_names = []
    user_data = load_user_data()
    print("Loading known face encodings...")
    for username, data in user_data.items():
        encoding_path = data.get("encoding_path")
        if encoding_path and os.path.exists(encoding_path):
            try:
                # Load encoding directly (assuming saved as numpy array)
                encoding = np.load(encoding_path)
                known_encodings.append(encoding)
                known_names.append(username)
                print(f"- Loaded encoding for {username}")
            except Exception as e:
                print(f"Error loading encoding for {username} from {encoding_path}: {e}")
        else:
            print(f"Warning: Encoding path not found or invalid for user {username}")
    print(f"Loaded {len(known_names)} known faces.")
    return known_encodings, known_names

known_face_encodings, known_face_names = load_known_faces()

# --- Global State Variables ---
# These store state PER client connection, managed via SocketIO SIDs
client_states = {} # {sid: {'mode': 'admin_capture'/'recog'/'pin', 'user': None, 'pin_entered': '', 'blink_counter': 0, 'pin_index': 0, etc.}}

# --- Helper Functions ---
def calculate_EAR(eye):
    y1 = dist.euclidean(eye[1], eye[5])
    y2 = dist.euclidean(eye[2], eye[4])
    x1 = dist.euclidean(eye[0], eye[3])
    if x1 == 0: return 100.0 # Avoid division by zero
    EAR = (y1 + y2) / (2.0 * x1)
    return EAR

def decode_image(dataURL):
    encoded_data = dataURL.split(',')[1]
    nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

# --- Flask Routes ---
@app.route('/')
def index():
    # Clear any previous session state
    session.clear()
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/user_login')
def user_login():
     # Clear state when starting login
    if request.sid in client_states:
        del client_states[request.sid]
    return render_template('user_login.html')

@app.route('/user_dashboard')
def user_dashboard():
    username = session.get('username')
    if not username:
        return redirect(url_for('index'))
    user_data = load_user_data()
    balance = user_data.get(username, {}).get('balance', 'N/A')
    return render_template('user_dashboard.html', username=username, balance=balance)

@app.route('/login_failed')
def login_failed():
    return render_template('login_failed.html')

@app.route('/add_user', methods=['POST'])
def add_user():
    global known_face_encodings, known_face_names
    username = request.form.get('username')
    pin = request.form.get('pin')
    balance = request.form.get('balance')
    # Basic validation
    if not username or not pin or not balance or not username.isidentifier():
         return jsonify({"success": False, "message": "Invalid data provided."}), 400
    if len(pin) != PIN_LENGTH or not pin.isdigit():
        return jsonify({"success": False, "message": f"PIN must be {PIN_LENGTH} digits."}), 400
    try:
        balance = float(balance)
    except ValueError:
        return jsonify({"success": False, "message": "Invalid balance amount."}), 400

    user_data = load_user_data()
    if username in user_data:
        return jsonify({"success": False, "message": "Username already exists."}), 400

    # Check if face encoding exists (should have been captured via SocketIO)
    encoding_filename = f"{username}_encoding.npy"
    encoding_path = os.path.join(KNOWN_FACES_DIR, username, encoding_filename)
    face_image_path = os.path.join(KNOWN_FACES_DIR, username, "face.jpg") # Path to saved image

    if not os.path.exists(encoding_path):
         return jsonify({"success": False, "message": "Face not captured or encoding not saved."}), 400

    user_data[username] = {
        "pin": pin, # In reality, HASH THE PIN!
        "balance": balance,
        "encoding_path": encoding_path,
        "image_path": face_image_path
    }
    save_user_data(user_data)

    # Reload known faces in memory
    known_face_encodings, known_face_names = load_known_faces()

    return jsonify({"success": True, "message": f"User {username} added successfully."})


# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    # Initialize state for this client
    client_states[request.sid] = {'mode': None} # Mode set by client action

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')
    # Clean up state for this client
    if request.sid in client_states:
        del client_states[request.sid]

@socketio.on('start_admin_capture')
def handle_start_admin_capture(data):
    sid = request.sid
    username = data.get('username')
    if not username or not username.isidentifier():
        emit('admin_error', {'message': 'Invalid username format.'}, room=sid)
        return
    user_dir = os.path.join(KNOWN_FACES_DIR, username)
    os.makedirs(user_dir, exist_ok=True) # Create directory if it doesn't exist
    client_states[sid] = {'mode': 'admin_capture', 'username': username, 'user_dir': user_dir}
    print(f"Admin capture mode started for {username} (SID: {sid})")
    emit('admin_capture_ready', room=sid) # Tell client backend is ready

@socketio.on('start_user_login')
def handle_start_user_login():
    sid = request.sid
    client_states[sid] = {
        'mode': 'recog',
        'user': None,
        'pin_entered': '',
        'blink_counter': 0,
        'pin_index': 0,
        'last_blink_time': 0,
        'pin_last_cycle_time': time.time()
    }
    print(f"User login mode started (SID: {sid})")
    emit('login_status', {'status': 'recognizing', 'message': 'Look at the camera...'}, room=sid)


@socketio.on('frame_data')
def handle_frame(dataURL):
    sid = request.sid
    if sid not in client_states or client_states[sid].get('mode') is None:
        # print(f"Ignoring frame from {sid} - no active mode.")
        return # Ignore if client state isn't set up

    frame = decode_image(dataURL)
    if frame is None:
        print(f"Could not decode frame from {sid}")
        return

    state = client_states[sid]
    mode = state['mode']

    # --- Admin Face Capture Mode ---
    if mode == 'admin_capture':
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model='hog') # Use 'hog' for speed

        if len(face_locations) == 1: # Capture only if exactly one face is found
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            if face_encodings:
                encoding = face_encodings[0]
                username = state['username']
                user_dir = state['user_dir']

                # Save the captured frame
                img_path = os.path.join(user_dir, "face.jpg")
                cv2.imwrite(img_path, frame)

                # Save the encoding as a numpy file
                encoding_filename = f"{username}_encoding.npy"
                encoding_path = os.path.join(user_dir, encoding_filename)
                np.save(encoding_path, encoding)

                print(f"Captured face for {username} (SID: {sid}). Encoding saved to {encoding_path}")
                state['mode'] = None # Stop processing frames for admin after capture
                emit('admin_capture_success', {'message': f'Face captured for {username}!', 'image_path': f'/static/known_faces/{username}/face.jpg'}, room=sid) # Send relative path
        elif len(face_locations) > 1:
             emit('admin_status', {'message': 'Multiple faces detected. Please ensure only one person is visible.'}, room=sid)
        else:
             emit('admin_status', {'message': 'No face detected. Please look at the camera.'}, room=sid)


    # --- User Face Recognition Mode ---
    elif mode == 'recog':
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model='hog')
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        recognized_name = None
        if face_encodings and known_face_encodings: # Check if known faces exist
            # Compare found faces with known faces
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=FACE_REC_TOLERANCE)
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                if True in matches:
                    best_match_index = np.argmin(face_distances)
                    if matches[best_match_index]:
                        recognized_name = known_face_names[best_match_index]
                        break # Recognize the first match

        if recognized_name:
            print(f"User recognized: {recognized_name} (SID: {sid})")
            state['mode'] = 'pin'
            state['user'] = recognized_name
            state['pin_last_cycle_time'] = time.time() # Reset timer for PIN cycle
            session['username'] = recognized_name # Store username in session for dashboard access
            emit('login_status', {
                'status': 'pin_entry',
                'message': f'Welcome {recognized_name}! Prepare for PIN entry.',
                'user': recognized_name,
                'current_digit': PIN_DIGITS[state['pin_index']],
                'pin_so_far': '*' * len(state['pin_entered'])
            }, room=sid)
        else:
            # Optional: Send feedback if face detected but not recognized
            if face_locations:
                 emit('login_status', {'status': 'recognizing', 'message': 'Face detected, but not recognized.'}, room=sid)
            else:
                 emit('login_status', {'status': 'recognizing', 'message': 'Looking for face...'}, room=sid)


    # --- PIN Entry via Blink Mode ---
    elif mode == 'pin':
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector(gray_frame) # Use dlib detector here for landmarks

        # Check if it's time to cycle the PIN digit
        current_time = time.time()
        if current_time - state['pin_last_cycle_time'] > PIN_CYCLE_DELAY:
            state['pin_index'] = (state['pin_index'] + 1) % len(PIN_DIGITS)
            state['pin_last_cycle_time'] = current_time
            # Send update of highlighted digit
            emit('pin_update', {
                 'current_digit': PIN_DIGITS[state['pin_index']],
                 'pin_so_far': '*' * len(state['pin_entered'])
            }, room=sid)

        found_correct_user = False
        for face in faces:
            # Optional: Add check here to ensure the detected face is the *same* user recognized earlier
            # This requires running recognition again or tracking the bounding box.
            # For simplicity, we assume the single face present is the logged-in user.
            # If you implement this check, set found_correct_user = True if match

            shape = landmark_predictor(gray_frame, face)
            shape = face_utils.shape_to_np(shape)

            leftEye = shape[L_start:L_end]
            rightEye = shape[R_start:R_end]
            leftEAR = calculate_EAR(leftEye)
            rightEAR = calculate_EAR(rightEye)

            avgEAR = (leftEAR + rightEAR) / 2.0

            # --- Blink Detection Logic ---
            if avgEAR < BLINK_THRESH:
                state['blink_counter'] += 1
            else:
                # If eyes were closed for sufficient frames, register blink
                if state['blink_counter'] >= BLINK_CONSEC_FRAMES:
                    # Debounce blinks - require some time between blinks
                    if current_time - state.get('last_blink_time', 0) > 0.5: # At least 0.5s between blinks
                        print(f"Blink detected! (SID: {sid})")
                        selected_digit = PIN_DIGITS[state['pin_index']]
                        state['pin_entered'] += selected_digit
                        state['last_blink_time'] = current_time # Update last blink time
                        print(f"PIN entered so far: {state['pin_entered']}")

                        # Reset cycle timer and index after selection
                        state['pin_index'] = 0
                        state['pin_last_cycle_time'] = current_time

                        # Check if PIN is complete
                        if len(state['pin_entered']) == PIN_LENGTH:
                            state['mode'] = 'verifying' # Change mode
                            emit('login_status', {'status': 'verifying', 'message': 'Verifying PIN...'}, room=sid)
                            # Perform verification in a separate step/handler or immediately
                            user_data = load_user_data()
                            correct_pin = user_data.get(state['user'], {}).get('pin')

                            if state['pin_entered'] == correct_pin:
                                print(f"PIN correct for {state['user']} (SID: {sid})")
                                state['mode'] = None # End processing
                                emit('login_result', {'success': True}, room=sid)
                            else:
                                print(f"PIN incorrect for {state['user']} (SID: {sid})")
                                state['mode'] = None # End processing
                                emit('login_result', {'success': False}, room=sid)
                            # No more processing needed for this client in this state
                            return # Exit handler early after verification attempt

                        else:
                            # Update UI with new PIN state if not complete yet
                             emit('pin_update', {
                                 'current_digit': PIN_DIGITS[state['pin_index']],
                                 'pin_so_far': '*' * len(state['pin_entered'])
                             }, room=sid)

                # Reset blink counter if eyes are open
                state['blink_counter'] = 0
            # Break after processing the first face (assuming only user is present)
            break # Process only the first detected face in PIN mode

# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Flask-SocketIO server...")
    # Use eventlet for SocketIO background tasks
    import eventlet
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)
    # socketio.run(app, debug=True) # Use this for simpler debugging, might be less performant