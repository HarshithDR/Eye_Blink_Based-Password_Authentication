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
# import threading # Not strictly needed with eventlet

from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit

# --- Configuration ---
SECRET_KEY = 'your_very_secret_key_CHANGE_ME_FINAL' # !! CHANGE THIS !!
KNOWN_FACES_DIR = 'static/known_faces'
USER_DATA_FILE = 'user_data.json'
DLIB_SHAPE_PREDICTOR = 'shape_predictor_68_face_landmarks.dat'
BLINK_THRESH = 0.25      # STARTING GUESS - Adjust based on your printed EAR values
BLINK_CONSEC_FRAMES = 1 # Require 1 frame for simplicity during debug (can change back to 3 later)
FACE_REC_TOLERANCE = 0.55
PIN_LENGTH = 4
PIN_DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
PIN_CYCLE_DELAY = 1.5 # Slightly faster cycle for testing?

# --- Flask & SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
# Ensure session cookie settings are reasonable (optional, defaults usually okay)
# app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
socketio = SocketIO(app, async_mode='eventlet')

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
    exit()

# --- Load User Data and Known Faces ---
print("Loading user data and known faces...")
def load_user_data():
    # ... (Keep exact same load_user_data function) ...
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                content = f.read(); return json.loads(content) if content else {}
        except Exception as e: print(f"Error reading {USER_DATA_FILE}: {e}"); return {}
    return {}

def save_user_data(data):
    # ... (Keep exact same save_user_data function) ...
    try:
        with open(USER_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e: print(f"Error saving user data: {e}")

def load_known_faces():
    # ... (Keep exact same robust load_known_faces function) ...
    known_encodings_list = []; known_names_list = []; user_data = load_user_data()
    print(f"Attempting to load known faces based on {len(user_data)} user(s)")
    if not os.path.exists(KNOWN_FACES_DIR): print(f"Error: Dir '{KNOWN_FACES_DIR}' missing."); return [], []
    loaded_count = 0
    for username, data in user_data.items():
        encoding_path_server = data.get("encoding_path")
        if not encoding_path_server: print(f"Warn: path missing for '{username}'."); continue
        encoding_path_server = os.path.normpath(encoding_path_server)
        if not encoding_path_server.startswith(os.path.join('static', 'known_faces')): print(f"Warn: path incorrect '{encoding_path_server}'."); continue
        if os.path.exists(encoding_path_server):
            try:
                encoding = np.load(encoding_path_server); known_encodings_list.append(encoding); known_names_list.append(username); loaded_count += 1
            except Exception as e: print(f"- Err load encoding '{username}': {e}")
        else: print(f"- Warn: Enc file not found '{username}': {encoding_path_server}")
    print(f"Finished loading faces. Loaded: {loaded_count}")
    return known_encodings_list, known_names_list

known_face_encodings, known_face_names = load_known_faces()

# --- Global State Variable ---
client_states = {}

# --- Helper Functions ---
def calculate_EAR(eye):
    # ... (Keep exact same calculate_EAR) ...
    y1 = dist.euclidean(eye[1], eye[5]); y2 = dist.euclidean(eye[2], eye[4])
    x1 = dist.euclidean(eye[0], eye[3]); return (y1 + y2) / (2.0 * x1) if x1 != 0 else 100.0

def decode_image(dataURL):
    # ... (Keep exact same decode_image) ...
    try:
        encoded_data = dataURL.split(',')[1]; nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception: return None

# --- Flask Routes ---
@app.route('/')
def index(): session.clear(); return render_template('index.html')
@app.route('/admin')
def admin(): return render_template('admin.html')
@app.route('/user_login')
def user_login(): return render_template('user_login.html')

@app.route('/user_dashboard')
def user_dashboard():
    print("[Dashboard Route] Accessing dashboard...")
    # *** This is the critical read ***
    username = session.get('username')
    print(f"[Dashboard Route] Value of session.get('username'): {username}") # Log exactly what is read

    if not username:
        print("[Dashboard Route] ACCESS DENIED: 'username' not found in session.")
        return redirect(url_for('user_login')) # Redirect back to login is correct behavior here

    print(f"[Dashboard Route] User '{username}' OK in session. Loading data...")
    user_data = load_user_data()
    user_info = user_data.get(username)
    if not user_info:
         print(f"[Dashboard Route] Error: User '{username}' data missing.")
         session.clear(); return redirect(url_for('login_failed'))
    balance = user_info.get('balance', 0.0)
    try: balance_formatted = "${:,.2f}".format(float(balance))
    except Exception: balance_formatted = "$ N/A"
    print(f"[Dashboard Route] Rendering dashboard for '{username}'")
    return render_template('user_dashboard.html', username=username,
                           balance_formatted=balance_formatted, balance_raw=balance)

@app.route('/login_failed')
def login_failed(): return render_template('login_failed.html')

@app.route('/withdraw', methods=['POST'])
def withdraw():
    # ... (Keep exact same withdraw logic) ...
    print("[Withdraw Route] Request received.")
    username = session.get('username')
    if not username: print("[Withdraw Route] Err: No user in session."); return jsonify({"success": False, "message": "Session expired."}), 401
    try:
        amount = float(request.form.get('amount'))
        if amount <= 0: raise ValueError("Amount must be positive.")
    except Exception as e: print(f"[Withdraw Route] Invalid amount: {e}"); return jsonify({"success": False, "message": f"Invalid amount: {e}"}), 400
    print(f"[Withdraw Route] User '{username}' withdrawing ${amount:.2f}")
    user_data = load_user_data()
    user_info = user_data.get(username)
    if not user_info: print(f"[Withdraw Route] Err: User '{username}' data missing."); return jsonify({"success": False, "message": "User data error."}), 500
    current_balance = float(user_info.get('balance', 0.0))
    if amount > current_balance: print(f"[Withdraw Route] Insufficient funds for '{username}'."); return jsonify({"success": False, "message": "Insufficient funds."}), 400
    new_balance = current_balance - amount; user_data[username]['balance'] = new_balance; save_user_data(user_data)
    print(f"[Withdraw Route] Success for '{username}'. New balance: ${new_balance:.2f}")
    return jsonify({"success": True, "message": f"Withdrew ${amount:.2f}.", "new_balance_formatted": "${:,.2f}".format(new_balance)})


@app.route('/add_user', methods=['POST'])
def add_user():
    # ... (Keep exact same add_user logic) ...
    global known_face_encodings, known_face_names; username = request.form.get('username'); pin = request.form.get('pin'); balance = request.form.get('balance')
    if not username or not pin or not balance or not username.isidentifier(): return jsonify({"success": False, "message": "Invalid data."}), 400
    if len(pin) != PIN_LENGTH or not pin.isdigit(): return jsonify({"success": False, "message": f"PIN {PIN_LENGTH} digits."}), 400
    try: balance = float(balance)
    except ValueError: return jsonify({"success": False, "message": "Invalid balance."}), 400
    user_data = load_user_data();
    if username in user_data: return jsonify({"success": False, "message": "Username exists."}), 400
    user_dir_server = os.path.join(KNOWN_FACES_DIR, username); encoding_filename = f"{username}_encoding.npy"; encoding_path_server = os.path.join(user_dir_server, encoding_filename)
    face_image_filename = "face.jpg"; face_image_path_client = url_for('static', filename=f'known_faces/{username}/{face_image_filename}')
    if not os.path.exists(encoding_path_server): print(f"Add User Error: Encoding missing: {encoding_path_server}"); return jsonify({"success": False, "message": "Face encoding missing."}), 400
    print(f"Adding user '{username}'."); user_data[username] = {"pin": pin, "balance": balance, "encoding_path": encoding_path_server, "image_path": face_image_path_client}; save_user_data(user_data)
    print("Reloading faces after add..."); known_face_encodings, known_face_names = load_known_faces()
    if username in known_face_names: print(f"User '{username}' loaded.")
    else: print(f"WARN: User '{username}' added but failed load!")
    return jsonify({"success": True, "message": f"User {username} added."})

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect(): sid = request.sid; print(f'[Socket Connect] Client: {sid}'); client_states[sid] = {'mode': None}


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'[Socket Disconnect] Client disconnected event received for SID: {sid}')
    # State might have already been removed by delayed_cleanup on success
    removed_state = client_states.pop(sid, None)
    if removed_state:
        print(f"[Socket Disconnect] State removed for SID {sid} during disconnect event.")
    else:
        print(f"[Socket Disconnect] No state found or already removed for SID {sid}.")


@socketio.on('start_admin_capture')
def handle_start_admin_capture(data):
    # ... (Keep exact same start_admin_capture logic) ...
    sid = request.sid; username = data.get('username'); print(f"[Admin] Start capture user: {username} (SID: {sid})")
    if not username or not username.isidentifier(): emit('admin_error', {'message': 'Invalid username.'}, room=sid); return
    user_dir_server = os.path.join(KNOWN_FACES_DIR, username)
    try: os.makedirs(user_dir_server, exist_ok=True); client_states[sid] = {'mode': 'admin_capture', 'username': username, 'user_dir': user_dir_server}; print(f"[Admin] Set mode='admin_capture' SID: {sid}."); emit('admin_capture_ready', room=sid)
    except OSError as e: print(f"[Admin] Err mkdir {user_dir_server}: {e}"); emit('admin_error', {'message': f'Server error: {e}'}, room=sid)

@socketio.on('start_user_login')
def handle_start_user_login():
    # ... (Keep exact same start_user_login logic) ...
    sid = request.sid; print(f"[Login] Start event SID: {sid}")
    client_states[sid] = { 'mode': 'recog', 'user': None, 'pin_entered': '', 'blink_counter': 0, 'pin_index': 0, 'last_blink_time': 0, 'pin_last_cycle_time': time.time(), 'recognition_attempts': 0, 'last_recog_emit_time': 0 }
    print(f"[Login] Set mode='recog' SID: {sid}"); global known_face_encodings
    if not known_face_encodings: print(f"[Login] Err SID {sid}: No faces loaded."); emit('login_status', {'status': 'error', 'message': 'No users loaded.'}, room=sid); client_states[sid]['mode'] = None
    else: emit('login_status', {'status': 'recognizing', 'message': 'Look at camera...'}, room=sid)

# ==============================================================================
# ================== FRAME PROCESSING HANDLER (handle_frame) ==================
# ==============================================================================
@socketio.on('frame_data')
def handle_frame(dataURL):
    sid = request.sid
    if sid not in client_states or not client_states[sid].get('mode'): return

    state = client_states[sid]
    mode = state['mode']
    frame = decode_image(dataURL)
    if frame is None: return

    processed_frame_data_url = None

    # --- Mode: Admin Face Capture ---
    if mode == 'admin_capture':
        # (Keep exact admin logic)
        # ...
        pass # Logic is self-contained and doesn't affect user login session

    # --- Mode: User Face Recognition ---
    elif mode == 'recog':
        global known_face_encodings, known_face_names
        if not known_face_encodings: return

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model='hog')
        recognized_name = None
        if face_locations:
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            if face_encodings:
                encoding_to_check = face_encodings[0]
                matches = face_recognition.compare_faces(known_face_encodings, encoding_to_check, tolerance=FACE_REC_TOLERANCE)
                face_distances = face_recognition.face_distance(known_face_encodings, encoding_to_check)
                best_match_index = np.argmin(face_distances)
                min_distance = face_distances[best_match_index]
                if matches[best_match_index] and min_distance < FACE_REC_TOLERANCE:
                    recognized_name = known_face_names[best_match_index]
                    print(f"[Login] SID: {sid} - >>> Face MATCH FOUND: '{recognized_name}' <<<")
                # else: print(f"[Login] SID: {sid} - No face match.") # Reduce noise

        if recognized_name:
            print(f"[Login] SID: {sid} - Setting session and switching to PIN for '{recognized_name}'.")
            state['mode'] = 'pin'; state['user'] = recognized_name; state['pin_last_cycle_time'] = time.time()
            # *** SET SESSION HERE - THIS IS THE CRITICAL POINT ***
            session['username'] = recognized_name
            session.modified = True # Mark as modified immediately
            print(f"[Login] SID: {sid} - Session username SET to: {session.get('username')}")
            emit('login_status', { 'status': 'pin_entry', 'message': f'Welcome {recognized_name}! Blink...',
                'user': recognized_name, 'current_digit': PIN_DIGITS[state['pin_index']],
                'pin_so_far': '*' * len(state['pin_entered']) }, room=sid)
        else: # Throttle 'recognizing' status updates
            now = time.time()
            if now - state.get('last_recog_emit_time', 0) > 1.0:
                msg = 'Looking for face...'
                if face_locations: msg = 'Face detected, not recognized.'
                emit('login_status', {'status': 'recognizing', 'message': msg}, room=sid)
                state['last_recog_emit_time'] = now


    # --- Mode: PIN Entry (Blink Detection & Visualization) ---
    elif mode == 'pin':
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector(gray_frame)
        current_time = time.time()

        # --- PIN Digit Cycling Logic ---
        if current_time - state.get('pin_last_cycle_time', 0) > PIN_CYCLE_DELAY:
            state['pin_index'] = (state['pin_index'] + 1) % len(PIN_DIGITS)
            state['pin_last_cycle_time'] = current_time
            socketio.emit('pin_update', { 'current_digit': PIN_DIGITS[state['pin_index']],
                 'pin_so_far': '*' * len(state['pin_entered']) }, room=sid)

        avgEAR = -1.0
        if faces:
            face = faces[0]; shape = landmark_predictor(gray_frame, face); shape = face_utils.shape_to_np(shape)
            try: # Calculate EAR & Draw Landmarks
                leftEye = shape[L_start:L_end]; rightEye = shape[R_start:R_end]
                leftEAR = calculate_EAR(leftEye); rightEAR = calculate_EAR(rightEye)
                avgEAR = (leftEAR + rightEAR) / 2.0
                for (x, y) in np.concatenate((leftEye, rightEye)): cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)
            except Exception: avgEAR = -2.0

            # --- Blink Detection Logic ---
            if avgEAR >= 0 and avgEAR < BLINK_THRESH: state['blink_counter'] = state.get('blink_counter', 0) + 1
            else: # Eyes are open or EAR error
                if state.get('blink_counter', 0) >= BLINK_CONSEC_FRAMES:
                    debounce_time = 0.7
                    if current_time - state.get('last_blink_time', 0) > debounce_time:
                        # === BLINK REGISTERED ===
                        selected_digit = PIN_DIGITS[state['pin_index']]
                        state['pin_entered'] += selected_digit
                        state['last_blink_time'] = current_time
                        print(f"[Login] SID: {sid} - **** BLINK REGISTERED! Digit: {selected_digit}, PIN: {'*' * len(state['pin_entered'])} ****")
                        state['pin_index'] = 0; state['pin_last_cycle_time'] = current_time

                        # === Check PIN completion ===
                        if len(state['pin_entered']) == PIN_LENGTH:
                            print(f"[Login] SID: {sid} - PIN complete. Verifying...")
                            state['mode'] = 'verifying'; emit('login_status', {'status': 'verifying', 'message': 'Verifying...'}, room=sid)
                            # --- Verification ---
                            user_data = load_user_data(); username_from_state = state.get('user')
                            correct_pin = user_data.get(username_from_state, {}).get('pin'); entered_pin = state.get('pin_entered')
                            socketio.sleep(0.5) # Simulated delay
                            login_success = bool(username_from_state and correct_pin and entered_pin == correct_pin)
                            print(f"[Login] SID: {sid} - Verification Result: {'Success' if login_success else 'FAILED'}")

                            # Emit result FIRST
                            emit('login_result', {'success': login_success}, room=sid)

                            # *** DELAY State Cleanup Slightly ***
                            if login_success:
                                # Define a function to remove state after a delay
                                def delayed_cleanup(client_sid):
                                    socketio.sleep(2.0) # Wait 2 seconds
                                    print(f"[Login Cleanup] Removing state for SID: {client_sid} after successful login.")
                                    client_states.pop(client_sid, None)

                                # Start the delayed cleanup in a background task
                                print(f"[Login Cleanup] Scheduling delayed state removal for SID: {sid}")
                                socketio.start_background_task(delayed_cleanup, sid)
                                # Return immediately - don't set mode=None here yet
                                # The background task will clean up later.
                                return
                            else:
                                # On failure, can probably clean up state immediately
                                print(f"[Login Cleanup] Removing state for SID: {sid} after failed login.")
                                state['mode'] = None # Stop processing immediately on failure
                                client_states.pop(sid, None) # Clean up immediately on failure
                                return
                state['blink_counter'] = 0 # Reset counter if eyes open or blink debounced
        else: state['blink_counter'] = 0 # Reset counter if face lost

        # --- Draw EAR & Threshold Text ---
        cv2.putText(frame, f"EAR: {avgEAR:.3f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Thresh: {BLINK_THRESH:.3f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # --- Encode & Emit Processed Frame ---
        try:
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret: processed_frame_data_url = "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode('utf-8')
        except Exception as e: print(f"Exception encoding frame SID {sid}: {e}")
        if processed_frame_data_url:
            emit('pin_frame_update', { 'image_data': processed_frame_data_url,
                'current_digit': PIN_DIGITS[state['pin_index']], 'pin_so_far': '*' * len(state['pin_entered']) }, room=sid)

# ==============================================================================
# ========================== END OF handle_frame ===============================
# ==============================================================================

# --- Main Execution ---
if __name__ == '__main__':
    print("--- Starting ATM Simulation Server ---")
    # ... (Keep print statements for paths and loaded faces) ...
    print(f"Known faces dir: {os.path.abspath(KNOWN_FACES_DIR)}")
    print(f"User data file: {os.path.abspath(USER_DATA_FILE)}")
    print(f"Shape predictor: {os.path.abspath(DLIB_SHAPE_PREDICTOR)}")
    print(f"Initial known faces loaded: {len(known_face_names)}")
    print("Starting server on http://0.0.0.0:5000 ...")
    import eventlet
    try: eventlet.wsgi.server(eventlet.listen(('', 5000)), app, log_output=False)
    except Exception as e: print(f"\n!!! Failed to start server: {e} !!!")