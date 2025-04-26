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
import threading # Can remain, though eventlet handles concurrency

from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit

# --- Configuration ---
SECRET_KEY = 'your_very_secret_key_CHANGE_ME' # !! CHANGE THIS !!
KNOWN_FACES_DIR = 'static/known_faces'
USER_DATA_FILE = 'user_data.json'
DLIB_SHAPE_PREDICTOR = 'shape_predictor_68_face_landmarks.dat'

# Blink Detection Constants
# *** YOU WILL LIKELY NEED TO ADJUST BLINK_THRESH ***
# Add print(f" Avg EAR: {avgEAR:.4f}") in PIN mode to find your values
BLINK_THRESH = 0.45      # STARTING GUESS - Adjust based on your printed EAR values
BLINK_CONSEC_FRAMES = 3  # Require 3 consecutive frames below threshold for a blink

# Face Recognition Constants
FACE_REC_TOLERANCE = 0.55 # Stricter tolerance (adjust if needed, lower is stricter)

# PIN Entry Constants
PIN_LENGTH = 4
PIN_DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
PIN_CYCLE_DELAY = 1.5 # Seconds to highlight each digit

# --- Flask & SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
socketio = SocketIO(app, async_mode='eventlet') # Use eventlet

# --- Create Directories if Missing ---
if not os.path.exists(KNOWN_FACES_DIR):
    print(f"Creating known faces directory at: {KNOWN_FACES_DIR}")
    os.makedirs(KNOWN_FACES_DIR)

# --- Load Models ---
print("Loading dlib models...")
try:
    face_detector = dlib.get_frontal_face_detector()
    landmark_predictor = dlib.shape_predictor(DLIB_SHAPE_PREDICTOR)
    (L_start, L_end) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
    (R_start, R_end) = face_utils.FACIAL_LANDMARKS_IDXS['right_eye']
    print("Dlib models loaded successfully.")
except Exception as e:
    print(f"FATAL ERROR loading dlib models: {e}")
    print(f"Ensure '{DLIB_SHAPE_PREDICTOR}' is in the root project directory.")
    exit()

# --- Load User Data and Known Faces ---
print("Loading user data and known faces...")
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                # Handle empty file case
                content = f.read()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            print(f"Warning: {USER_DATA_FILE} contains invalid JSON. Starting fresh.")
            return {}
        except Exception as e:
            print(f"Error reading {USER_DATA_FILE}: {e}")
            return {}
    return {}

def save_user_data(data):
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving user data to {USER_DATA_FILE}: {e}")


def load_known_faces():
    """Loads face encodings and names from user_data.json and .npy files."""
    known_encodings_list = []
    known_names_list = []
    user_data = load_user_data()
    print(f"Attempting to load known faces based on {len(user_data)} user(s) in {USER_DATA_FILE}")

    if not os.path.exists(KNOWN_FACES_DIR):
        print(f"Error: Known faces directory '{KNOWN_FACES_DIR}' does not exist.")
        return [], []

    loaded_count = 0
    for username, data in user_data.items():
        encoding_path_server = data.get("encoding_path") # Path stored is for server use

        if not encoding_path_server:
            print(f"Warning: 'encoding_path' missing for user '{username}' in {USER_DATA_FILE}.")
            continue

        # Ensure path separators are correct for the OS (though forward slash usually works)
        encoding_path_server = os.path.normpath(encoding_path_server)

        # Double-check the path starts correctly (relative to app.py)
        # Example: should be like 'static/known_faces/username/username_encoding.npy'
        if not encoding_path_server.startswith(os.path.join('static', 'known_faces')):
             print(f"Warning: Encoding path for '{username}' seems incorrect: '{encoding_path_server}'. Skipping.")
             continue


        if os.path.exists(encoding_path_server):
            try:
                encoding = np.load(encoding_path_server)
                known_encodings_list.append(encoding)
                known_names_list.append(username)
                print(f"- Successfully loaded encoding for '{username}' from {encoding_path_server}")
                loaded_count += 1
            except Exception as e:
                print(f"- Error loading encoding file for '{username}' from {encoding_path_server}: {e}")
        else:
            print(f"- Warning: Encoding file not found for '{username}' at specified path: {encoding_path_server}")

    print(f"Finished loading. Total known faces loaded into memory: {loaded_count}")
    return known_encodings_list, known_names_list

# Load faces on startup
known_face_encodings, known_face_names = load_known_faces()

# --- Global State Variable ---
client_states = {} # Manages state per client connection {sid: state_dict}

# --- Helper Functions ---
def calculate_EAR(eye):
    # ... (Keep calculate_EAR as before) ...
    y1 = dist.euclidean(eye[1], eye[5])
    y2 = dist.euclidean(eye[2], eye[4])
    x1 = dist.euclidean(eye[0], eye[3])
    if x1 == 0: return 100.0 # Avoid division by zero
    EAR = (y1 + y2) / (2.0 * x1)
    return EAR

def decode_image(dataURL):
    # ... (Keep decode_image as before) ...
    try:
        encoded_data = dataURL.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"Error decoding image: {e}")
        return None

# --- Flask Routes ---
@app.route('/')
def index():
    session.clear()
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/user_login')
def user_login():
    # No request.sid access here
    return render_template('user_login.html')

@app.route('/user_dashboard')
def user_dashboard():
    # ... (Keep user_dashboard logic as before, ensure session check) ...
    username = session.get('username')
    if not username:
        print("Dashboard Access Denied: Username not in session.")
        return redirect(url_for('index'))
    user_data = load_user_data()
    user_info = user_data.get(username)
    if not user_info:
         print(f"Dashboard Error: User '{username}' found in session but not in user_data.json.")
         session.clear() # Clear bad session
         return redirect(url_for('login_failed'))
    balance = user_info.get('balance', 'N/A')
    return render_template('user_dashboard.html', username=username, balance=balance)


@app.route('/login_failed')
def login_failed():
    return render_template('login_failed.html')

@app.route('/add_user', methods=['POST'])
def add_user():
    global known_face_encodings, known_face_names # Allow modification
    # ... (Keep validation logic for username, pin, balance) ...
    username = request.form.get('username')
    pin = request.form.get('pin')
    balance = request.form.get('balance')

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

    # Construct paths relative to the app's execution directory
    user_dir_server = os.path.join(KNOWN_FACES_DIR, username) # Server path: static/known_faces/username
    encoding_filename = f"{username}_encoding.npy"
    encoding_path_server = os.path.join(user_dir_server, encoding_filename) # Server path for .npy
    face_image_filename = "face.jpg"
    face_image_path_client = url_for('static', filename=f'known_faces/{username}/{face_image_filename}') # URL path for browser

    if not os.path.exists(encoding_path_server):
         print(f"Add User Error: Encoding file check failed for: {encoding_path_server}")
         return jsonify({"success": False, "message": "Face encoding file not found. Please capture face again before adding."}), 400

    print(f"Adding user '{username}'. Data: PIN=****, Balance={balance}, Encoding={encoding_path_server}")
    user_data[username] = {
        "pin": pin, # HASH THE PIN in a real app!
        "balance": balance,
        "encoding_path": encoding_path_server, # Store server path for loading
        "image_path": face_image_path_client   # Store URL path for potential future use (not currently used after add)
    }
    save_user_data(user_data)

    # Reload known faces in memory immediately
    print("Reloading known faces after adding new user...")
    known_face_encodings, known_face_names = load_known_faces()
    # Verify reload
    if username not in known_face_names:
        print(f"CRITICAL WARNING: User '{username}' was added to JSON but failed to load into memory!")
    else:
         print(f"User '{username}' successfully loaded into memory.")


    return jsonify({"success": True, "message": f"User {username} added successfully."})


# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f'[Socket Connect] Client connected: {sid}')
    client_states[sid] = {'mode': None} # Initialize blank state

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'[Socket Disconnect] Client disconnected: {sid}')
    if sid in client_states:
        del client_states[sid] # Clean up state

@socketio.on('start_admin_capture')
def handle_start_admin_capture(data):
    sid = request.sid
    username = data.get('username')
    print(f"[Admin Capture] Received 'start_admin_capture' for user: {username} (SID: {sid})")
    if not username or not username.isidentifier():
        emit('admin_error', {'message': 'Invalid username format.'}, room=sid)
        return

    user_dir_server = os.path.join(KNOWN_FACES_DIR, username) # static/known_faces/username
    try:
        os.makedirs(user_dir_server, exist_ok=True)
        client_states[sid] = {'mode': 'admin_capture', 'username': username, 'user_dir': user_dir_server}
        print(f"[Admin Capture] Set mode='admin_capture' for SID: {sid}. User dir: {user_dir_server}")
        emit('admin_capture_ready', room=sid) # Tell frontend backend is ready for frames
    except OSError as e:
         print(f"[Admin Capture] Error creating directory {user_dir_server}: {e}")
         emit('admin_error', {'message': f'Server error: Could not create directory for user: {e}'}, room=sid)


@socketio.on('start_user_login')
def handle_start_user_login():
    sid = request.sid
    print(f"[User Login] Received 'start_user_login' event (SID: {sid})")
    client_states[sid] = {
        'mode': 'recog',
        'user': None,
        'pin_entered': '',
        'blink_counter': 0,
        'pin_index': 0,
        'last_blink_time': 0,
        'pin_last_cycle_time': time.time(),
        'recognition_attempts': 0,
        'last_recog_emit_time': 0 # For throttling status messages
    }
    print(f"[User Login] Set mode to 'recog' for SID: {sid}")
    # Check if known faces exist before starting
    global known_face_encodings
    if not known_face_encodings:
        print(f"[User Login] Error for SID {sid}: No known faces loaded in memory.")
        emit('login_status', {'status': 'error', 'message': 'Cannot start login: No user faces loaded.'}, room=sid)
        client_states[sid]['mode'] = None # Prevent processing frames
    else:
        emit('login_status', {'status': 'recognizing', 'message': 'Look at the camera...'}, room=sid)


@socketio.on('frame_data')
def handle_frame(dataURL):
    sid = request.sid
    if sid not in client_states or not client_states[sid].get('mode'): return # Ignore if no active mode

    state = client_states[sid]
    mode = state['mode']
    # print(f"Frame from {sid} in mode: {mode}") # Very verbose log

    frame = decode_image(dataURL)
    if frame is None: return

    # --- Admin Face Capture Mode ---
    if mode == 'admin_capture':
        print(f"[Admin Capture] Processing frame for SID: {sid}")
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model='hog') # Faster 'hog' model

        status_msg = 'No face detected. Position yourself clearly.'
        capture_success = False

        if len(face_locations) == 1:
            print(f"[Admin Capture] Found 1 face for SID: {sid}. Encoding...")
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            if face_encodings:
                encoding = face_encodings[0]
                username = state['username']
                user_dir_server = state['user_dir'] # Server path: static/known_faces/username

                img_filename = "face.jpg"
                img_path_server = os.path.join(user_dir_server, img_filename)
                encoding_filename = f"{username}_encoding.npy"
                encoding_path_server = os.path.join(user_dir_server, encoding_filename)
                img_path_client = url_for('static', filename=f'known_faces/{username}/{img_filename}') # URL path for browser

                try:
                    cv2.imwrite(img_path_server, frame)
                    np.save(encoding_path_server, encoding)
                    print(f"[Admin Capture] SUCCESS: Captured face for '{username}' (SID: {sid}). Encoding saved to {encoding_path_server}")
                    status_msg = f'Face captured successfully for {username}!'
                    capture_success = True
                    state['mode'] = None # Stop processing frames for admin capture

                    emit('admin_capture_success', {
                        'message': status_msg,
                        'image_path': img_path_client # Send the URL path
                        }, room=sid)

                except Exception as e:
                    print(f"[Admin Capture] Error saving image/encoding for {username}: {e}")
                    status_msg = f'Error saving file: {e}'
                    emit('admin_error', {'message': status_msg}, room=sid)
            else:
                status_msg = 'Face detected, but could not create encoding.'
                print(f"[Admin Capture] Failed encoding face for SID: {sid}")

        elif len(face_locations) > 1:
             status_msg = 'Multiple faces detected. Only one person please.'
             print(f"[Admin Capture] Multiple faces detected for SID: {sid}")

        # Emit status only if capture wasn't successful (success emits its own event)
        if not capture_success:
            emit('admin_status', {'message': status_msg}, room=sid)


    # --- User Face Recognition Mode ---
    elif mode == 'recog':
        # print(f"[User Login] SID: {sid} - Processing frame in 'recog' mode.") # Verbose
        global known_face_encodings, known_face_names # Ensure using latest
        if not known_face_encodings: return # Should have been checked in start_user_login

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model='hog')

        recognized_name = None
        if face_locations:
            # print(f"[User Login] SID: {sid} - Found {len(face_locations)} face(s). Encoding first one...") # Verbose
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations) # Can encode multiple if needed later
            if face_encodings:
                encoding_to_check = face_encodings[0] # Use first detected face

                matches = face_recognition.compare_faces(known_face_encodings, encoding_to_check, tolerance=FACE_REC_TOLERANCE)
                face_distances = face_recognition.face_distance(known_face_encodings, encoding_to_check)
                # print(f"[User Login] SID: {sid} - Comparing. Distances: {[f'{d:.4f}' for d in face_distances]}") # Verbose Log

                best_match_index = np.argmin(face_distances)
                min_distance = face_distances[best_match_index]

                # Refined Check: Ensure the *closest* match is within tolerance *and* compare_faces agreed
                if matches[best_match_index] and min_distance < FACE_REC_TOLERANCE:
                    recognized_name = known_face_names[best_match_index]
                    print(f"[User Login] SID: {sid} - >>> MATCH FOUND: '{recognized_name}' (Index: {best_match_index}, Dist: {min_distance:.4f}) <<<")
                else:
                    # Log why it failed (only if face detected)
                    print(f"[User Login] SID: {sid} - No match. Closest: '{known_face_names[best_match_index]}' (Dist: {min_distance:.4f}, Tolerance: {FACE_REC_TOLERANCE}, Match Flag: {matches[best_match_index]})")
            #else: print(f"[User Login] SID: {sid} - Face locations found, but encoding failed.") # Verbose
        #else: print(f"[User Login] SID: {sid} - No faces found in frame.") # Verbose

        # --- Handle Recognition Result ---
        if recognized_name:
            print(f"[User Login] SID: {sid} - Switching to PIN mode for '{recognized_name}'.")
            state['mode'] = 'pin'
            state['user'] = recognized_name
            state['pin_last_cycle_time'] = time.time()
            session['username'] = recognized_name # Set session for dashboard
            session.modified = True
            emit('login_status', {
                'status': 'pin_entry',
                'message': f'Welcome {recognized_name}! Blink on highlighted digit.',
                'user': recognized_name,
                'current_digit': PIN_DIGITS[state['pin_index']],
                'pin_so_far': '*' * len(state['pin_entered'])
            }, room=sid)
        else:
            # Throttle status updates to frontend
            now = time.time()
            if now - state.get('last_recog_emit_time', 0) > 1.0: # Max 1 status update per second
                state['recognition_attempts'] = state.get('recognition_attempts', 0) + 1
                msg = 'Looking for face...'
                if face_locations: msg = 'Face detected, but not recognized.'
                # print(f"[User Login] SID: {sid} - Still recognizing. Attempt: {state['recognition_attempts']}") # Verbose
                emit('login_status', {'status': 'recognizing', 'message': msg}, room=sid)
                state['last_recog_emit_time'] = now


    # --- PIN Entry via Blink Mode ---
    elif mode == 'pin':
        # print(f"[User Login] SID: {sid} - Processing frame in 'pin' mode.") # Verbose
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector(gray_frame)

        # --- PIN Digit Cycling ---
        current_time = time.time()
        if current_time - state.get('pin_last_cycle_time', 0) > PIN_CYCLE_DELAY:
            state['pin_index'] = (state['pin_index'] + 1) % len(PIN_DIGITS)
            state['pin_last_cycle_time'] = current_time
            # print(f"[User Login] SID: {sid} - Highlighting digit: {PIN_DIGITS[state['pin_index']]}") # Verbose
            emit('pin_update', {
                 'current_digit': PIN_DIGITS[state['pin_index']],
                 'pin_so_far': '*' * len(state['pin_entered'])
            }, room=sid)

        if not faces:
            # print(f"[User Login] SID: {sid} - No face detected during PIN entry.") # Verbose
            return # Skip blink detection if no face

        # --- Blink Detection ---
        face = faces[0] # Assume first face is the user
        shape = landmark_predictor(gray_frame, face)
        shape = face_utils.shape_to_np(shape)

        try:
            leftEye = shape[L_start:L_end]
            rightEye = shape[R_start:R_end]
            leftEAR = calculate_EAR(leftEye)
            rightEAR = calculate_EAR(rightEye)
            avgEAR = (leftEAR + rightEAR) / 2.0
            # *** PRINT EAR FOR DEBUGGING ***
            print(f"[User Login] SID: {sid} - Avg EAR: {avgEAR:.4f} (Thresh: {BLINK_THRESH})")
        except Exception as e:
             print(f"Error calculating EAR for SID {sid}: {e}")
             avgEAR = 1.0 # Assume eyes open on error

        # Check if eyes are closed
        if avgEAR < BLINK_THRESH:
            state['blink_counter'] = state.get('blink_counter', 0) + 1
            # print(f"[User Login] SID: {sid} - Blink counter: {state['blink_counter']}") # Verbose
        else:
            # Eyes are open, check if a blink *just finished*
            if state.get('blink_counter', 0) >= BLINK_CONSEC_FRAMES:
                debounce_time = 0.7 # Time required between blinks
                if current_time - state.get('last_blink_time', 0) > debounce_time:
                    # --- BLINK REGISTERED ---
                    selected_digit = PIN_DIGITS[state['pin_index']]
                    state['pin_entered'] += selected_digit
                    state['last_blink_time'] = current_time # Update time of this successful blink
                    print(f"[User Login] SID: {sid} - **** BLINK REGISTERED! Digit: {selected_digit}, PIN: {'*' * len(state['pin_entered'])} ****")

                    # Reset cycle timer and index immediately after selection
                    state['pin_index'] = 0
                    state['pin_last_cycle_time'] = current_time # Start next cycle timer now

                    # --- Check PIN completion ---
                    if len(state['pin_entered']) == PIN_LENGTH:
                        print(f"[User Login] SID: {sid} - PIN entry complete. Verifying...")
                        state['mode'] = 'verifying' # Prevent further processing
                        emit('login_status', {'status': 'verifying', 'message': 'Verifying PIN...'}, room=sid)

                        # --- Verification Logic ---
                        user_data = load_user_data()
                        correct_pin = user_data.get(state.get('user'), {}).get('pin')
                        entered_pin = state.get('pin_entered')

                        # Use a slight delay for feedback
                        socketio.sleep(0.5) # Use socketio.sleep for async delay

                        if correct_pin and entered_pin == correct_pin:
                            print(f"[User Login] SID: {sid} - PIN CORRECT for '{state.get('user')}'!")
                            # Session should already be set from recognition phase
                            print(f"[User Login] SID: {sid} - Session username before emit: {session.get('username')}")
                            emit('login_result', {'success': True}, room=sid)
                        else:
                            print(f"[User Login] SID: {sid} - !!! PIN INCORRECT for '{state.get('user')}' !!! (Entered: {'*' * len(entered_pin)}, Expected: {'*' * len(correct_pin if correct_pin else '')})")
                            emit('login_result', {'success': False}, room=sid)
                        # Important: Stop processing after verification attempt
                        state['mode'] = None
                        return

                    else:
                        # Update UI with new PIN state and reset highlight to first digit
                        emit('pin_update', {
                            'current_digit': PIN_DIGITS[state['pin_index']], # Should be '1' now
                            'pin_so_far': '*' * len(state['pin_entered'])
                        }, room=sid)
                # else: print(f"[User Login] SID: {sid} - Blink detected, but debounced.") # Verbose

            # *** Reset blink counter whenever eyes are open ***
            state['blink_counter'] = 0


# --- Main Execution ---
if __name__ == '__main__':
    print("--- Starting ATM Simulation Server ---")
    print(f"Known faces directory: {os.path.abspath(KNOWN_FACES_DIR)}")
    print(f"User data file: {os.path.abspath(USER_DATA_FILE)}")
    print(f"Shape predictor: {os.path.abspath(DLIB_SHAPE_PREDICTOR)}")
    print(f"Initial known faces loaded: {len(known_face_names)}")
    print("Starting Flask-SocketIO server using eventlet...")
    import eventlet
    try:
        # Bind to 0.0.0.0 to be accessible on network, use port 5000
        # Use log_output=False to reduce console noise from eventlet itself
        eventlet.wsgi.server(eventlet.listen(('', 5000)), app, log_output=False)
    except Exception as e:
        print(f"\n!!! Failed to start server: {e} !!!")
        print("Common issues: Port 5000 already in use, permissions error.")