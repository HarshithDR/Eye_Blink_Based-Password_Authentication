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
import secrets # For generating secure tokens
import datetime

from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit

# --- Configuration ---
SECRET_KEY = 'your_very_secret_key_CHANGE_ME_TOKEN_FIX' # !! CHANGE THIS !!
KNOWN_FACES_DIR = 'static/known_faces'
USER_DATA_FILE = 'user_data.json'
DLIB_SHAPE_PREDICTOR = 'shape_predictor_68_face_landmarks.dat'
BLINK_THRESH = 0.25      # STARTING GUESS - Adjust based on your printed EAR values
BLINK_CONSEC_FRAMES = 1  # Require 1 frame for simplicity during debug (can change back to 3 later)
FACE_REC_TOLERANCE = 0.55
PIN_LENGTH = 4
PIN_DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
PIN_CYCLE_DELAY = 1.5
TOKEN_EXPIRY_SECONDS = 30 # Token is valid for 30 seconds

# --- Flask & SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
socketio = SocketIO(app, async_mode='eventlet')

# --- Temporary Token Store ---
# WARNING: In-memory store is simple but lost on restart and not suitable for multi-process servers.
# Use Redis or a database for production.
login_tokens = {} # { token: {'username': 'user', 'expires': datetime_obj} }

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
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                content = f.read(); return json.loads(content) if content else {}
        except Exception as e: print(f"Error reading {USER_DATA_FILE}: {e}"); return {}
    return {}

def save_user_data(data):
    try:
        with open(USER_DATA_FILE, 'w') as f: json.dump(data, f, indent=4)
    except Exception as e: print(f"Error saving user data: {e}")

def load_known_faces():
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
    y1 = dist.euclidean(eye[1], eye[5]); y2 = dist.euclidean(eye[2], eye[4])
    x1 = dist.euclidean(eye[0], eye[3]); return (y1 + y2) / (2.0 * x1) if x1 != 0 else 100.0

def decode_image(dataURL):
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

# *** NEW Intermediate Route for Token Confirmation ***
@app.route('/confirm_login/<token>')
def confirm_login(token):
    print(f"[Confirm Login Route] Received token: {token}")
    token_data = login_tokens.get(token) # Look up token

    if not token_data: # Validate token
        print("[Confirm Login Route] Error: Token not found.")
        return redirect(url_for('login_failed', reason='invalid_token'))
    if datetime.datetime.utcnow() > token_data['expires']: # Check expiry
        print("[Confirm Login Route] Error: Token expired.")
        login_tokens.pop(token, None); return redirect(url_for('login_failed', reason='token_expired'))

    username = token_data['username'] # Token is valid! Retrieve username
    print(f"[Confirm Login Route] Token valid for user: {username}")

    # *** Set the Flask session reliably HERE in standard HTTP context ***
    session['username'] = username
    session.modified = True
    print(f"[Confirm Login Route] Session username SET in HTTP context to: {session.get('username')}")

    login_tokens.pop(token, None) # Invalidate/Remove the used token
    print(f"[Confirm Login Route] Token invalidated and removed.")

    print("[Confirm Login Route] Redirecting to dashboard...") # Redirect to the actual dashboard
    return redirect(url_for('user_dashboard'))

@app.route('/user_dashboard')
def user_dashboard():
    print("[Dashboard Route] Accessing dashboard...")
    username = session.get('username') # Check session established by confirm_login
    print(f"[Dashboard Route] Value of session.get('username'): {username}")
    if not username:
        print("[Dashboard Route] ACCESS DENIED: 'username' not in session.")
        return redirect(url_for('user_login'))
    print(f"[Dashboard Route] User '{username}' OK in session. Loading data...")
    user_data = load_user_data(); user_info = user_data.get(username)
    if not user_info:
         print(f"[Dashboard Route] Error: User '{username}' data missing."); session.clear(); return redirect(url_for('login_failed'))
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
    # (Keep exact same withdraw logic)
    print("[Withdraw Route] Request received.")
    username = session.get('username')
    if not username: print("[Withdraw Route] Err: No user in session."); return jsonify({"success": False, "message": "Session expired."}), 401
    try:
        amount = float(request.form.get('amount'))
        if amount <= 0: raise ValueError("Amount must be positive.")
    except Exception as e: print(f"[Withdraw Route] Invalid amount: {e}"); return jsonify({"success": False, "message": f"Invalid amount: {e}"}), 400
    print(f"[Withdraw Route] User '{username}' withdrawing ${amount:.2f}")
    user_data = load_user_data(); user_info = user_data.get(username)
    if not user_info: print(f"[Withdraw Route] Err: User '{username}' data missing."); return jsonify({"success": False, "message": "User data error."}), 500
    current_balance = float(user_info.get('balance', 0.0))
    if amount > current_balance: print(f"[Withdraw Route] Insufficient funds for '{username}'."); return jsonify({"success": False, "message": "Insufficient funds."}), 400
    new_balance = current_balance - amount; user_data[username]['balance'] = new_balance; save_user_data(user_data)
    print(f"[Withdraw Route] Success for '{username}'. New balance: ${new_balance:.2f}")
    return jsonify({"success": True, "message": f"Withdrew ${amount:.2f}.", "new_balance_formatted": "${:,.2f}".format(new_balance)})

@app.route('/add_user', methods=['POST'])
def add_user():
    # (Keep exact same add_user logic)
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
def handle_disconnect(): sid = request.sid; print(f'[Socket Disconnect] Client: {sid}'); client_states.pop(sid, None)

@socketio.on('start_admin_capture')
def handle_start_admin_capture(data):
    # (Keep exact same start_admin_capture logic)
    sid = request.sid; username = data.get('username'); print(f"[Admin] Start capture user: {username} (SID: {sid})")
    if not username or not username.isidentifier(): emit('admin_error', {'message': 'Invalid username.'}, room=sid); return
    user_dir_server = os.path.join(KNOWN_FACES_DIR, username)
    try: os.makedirs(user_dir_server, exist_ok=True); client_states[sid] = {'mode': 'admin_capture', 'username': username, 'user_dir': user_dir_server}; print(f"[Admin] Set mode='admin_capture' SID: {sid}."); emit('admin_capture_ready', room=sid)
    except OSError as e: print(f"[Admin] Err mkdir {user_dir_server}: {e}"); emit('admin_error', {'message': f'Server error: {e}'}, room=sid)

@socketio.on('start_user_login')
def handle_start_user_login():
    # (Keep exact same start_user_login logic)
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
        # *** START ADMIN DEBUG LOGGING ***
        print(f"[Admin Capture DBG] SID: {sid} - Processing frame...")
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame, model='hog')
        num_faces = len(face_locations)
        print(f"[Admin Capture DBG] SID: {sid} - Found {num_faces} face(s).")
        # *** END ADMIN DEBUG LOGGING ***

        capture_success = False
        status_msg = 'No face detected. Position yourself clearly.' # Default status

        if num_faces == 1: # Check for exactly one face
            print(f"[Admin Capture DBG] SID: {sid} - Exactly 1 face found. Attempting encoding...")
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            if face_encodings:
                print(f"[Admin Capture DBG] SID: {sid} - Encoding successful. Preparing to save...")
                encoding = face_encodings[0]
                username = state['username']; user_dir_server = state['user_dir']
                img_filename = "face.jpg"; img_path_server = os.path.join(user_dir_server, img_filename)
                encoding_filename = f"{username}_encoding.npy"; encoding_path_server = os.path.join(user_dir_server, encoding_filename)
                img_path_client = url_for('static', filename=f'known_faces/{username}/{img_filename}') # Generate client URL

                try:
                    # Save files
                    print(f"[Admin Capture DBG] SID: {sid} - Saving image to: {img_path_server}")
                    cv2.imwrite(img_path_server, frame)
                    print(f"[Admin Capture DBG] SID: {sid} - Saving encoding to: {encoding_path_server}")
                    np.save(encoding_path_server, encoding)

                    # Log success and emit
                    print(f"[Admin Capture] SUCCESS: Captured '{username}' (SID: {sid}).")
                    status_msg = f'Face captured for {username}!'; capture_success = True; state['mode'] = None
                    emit('admin_capture_success', {'message': status_msg, 'image_path': img_path_client }, room=sid)
                    print(f"[Admin Capture DBG] SID: {sid} - Emitted admin_capture_success.")

                except Exception as e:
                    # Log saving error
                    print(f"[Admin Capture] !!! ERROR saving files for SID {sid}: {e} !!!")
                    status_msg = f'Error saving capture data: {e}'
                    # Emit an error status back to the user
                    emit('admin_error', {'message': status_msg}, room=sid) # Use admin_error for clarity

            else: # Encoding failed
                status_msg = 'Face detected, but could not create encoding.';
                print(f"[Admin Capture DBG] SID: {sid} - Encoding failed.")

        elif num_faces > 1: # Multiple faces detected
             status_msg = 'Multiple faces detected. Only one person please.'
             print(f"[Admin Capture DBG] SID: {sid} - Multiple faces detected.")
        # else: num_faces == 0, status_msg remains 'No face detected.'

        # Emit status update only if capture wasn't successful OR if it's still trying
        if not capture_success and state.get('mode') == 'admin_capture':
            # Optional: Throttle status messages if needed, but likely okay for admin
            # print(f"[Admin Capture DBG] SID: {sid} - Emitting admin_status: {status_msg}") # Verify status emit
            emit('admin_status', {'message': status_msg}, room=sid)

    # --- Mode: User Face Recognition ---
    elif mode == 'recog':
        # (Recognition logic - sets user in state, DOES NOT set session)
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

        if recognized_name:
            print(f"[Login] SID: {sid} - Switching to PIN mode for '{recognized_name}'. Storing in state.")
            state['mode'] = 'pin'; state['user'] = recognized_name # Store user in state
            state['pin_last_cycle_time'] = time.time()
            # *** NO SESSION SETTING HERE ***
            print(f"[Login] SID: {sid} - User '{recognized_name}' stored in state.")
            emit('login_status', { 'status': 'pin_entry', 'message': f'Welcome {recognized_name}! Blink...',
                'user': recognized_name, 'current_digit': PIN_DIGITS[state['pin_index']],
                'pin_so_far': '*' * len(state['pin_entered']) }, room=sid)
        else: # Throttle 'recognizing' status updates
             now = time.time()
             if now - state.get('last_recog_emit_time', 0) > 1.0:
                 msg = 'Looking for face...';
                 if face_locations: msg = 'Face detected, not recognized.'
                 emit('login_status', {'status': 'recognizing', 'message': msg}, room=sid); state['last_recog_emit_time'] = now


    # --- Mode: PIN Entry (Blink Detection & Visualization) ---
    elif mode == 'pin':
        # (Keep PIN digit cycling, EAR calculation, drawing logic)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY); faces = face_detector(gray_frame); current_time = time.time()
        if current_time - state.get('pin_last_cycle_time', 0) > PIN_CYCLE_DELAY: # Cycle digit
            state['pin_index'] = (state['pin_index'] + 1) % len(PIN_DIGITS); state['pin_last_cycle_time'] = current_time
            socketio.emit('pin_update', { 'current_digit': PIN_DIGITS[state['pin_index']], 'pin_so_far': '*' * len(state['pin_entered']) }, room=sid)

        avgEAR = -1.0
        if faces: # Calculate EAR and draw landmarks
            face = faces[0]; shape = landmark_predictor(gray_frame, face); shape = face_utils.shape_to_np(shape)
            try:
                leftEye = shape[L_start:L_end]; rightEye = shape[R_start:R_end]; leftEAR = calculate_EAR(leftEye); rightEAR = calculate_EAR(rightEye)
                avgEAR = (leftEAR + rightEAR) / 2.0
                for (x, y) in np.concatenate((leftEye, rightEye)): cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)
            except Exception: avgEAR = -2.0

            # Blink Detection Logic
            if avgEAR >= 0 and avgEAR < BLINK_THRESH: state['blink_counter'] = state.get('blink_counter', 0) + 1
            else:
                if state.get('blink_counter', 0) >= BLINK_CONSEC_FRAMES:
                    debounce_time = 0.7
                    if current_time - state.get('last_blink_time', 0) > debounce_time:
                        # === BLINK REGISTERED ===
                        selected_digit = PIN_DIGITS[state['pin_index']]; state['pin_entered'] += selected_digit
                        state['last_blink_time'] = current_time
                        print(f"[Login] SID: {sid} - **** BLINK REGISTERED! Digit: {selected_digit}, PIN: {'*' * len(state['pin_entered'])} ****")
                        state['pin_index'] = 0; state['pin_last_cycle_time'] = current_time

                        # === Check PIN completion ===
                        if len(state['pin_entered']) == PIN_LENGTH:
                            print(f"[Login] SID: {sid} - PIN complete. Verifying...")
                            state['mode'] = 'verifying'; emit('login_status', {'status': 'verifying', 'message': 'Verifying...'}, room=sid)
                            # Verification Logic
                            user_data = load_user_data(); username_from_state = state.get('user')
                            correct_pin = user_data.get(username_from_state, {}).get('pin'); entered_pin = state.get('pin_entered')
                            socketio.sleep(0.5)
                            login_success = bool(username_from_state and correct_pin and entered_pin == correct_pin)
                            print(f"[Login] SID: {sid} - Verification Result: {'Success' if login_success else 'FAILED'}")

                            if login_success: # Generate and emit token
                                token = secrets.token_urlsafe(16)
                                expiry_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=TOKEN_EXPIRY_SECONDS)
                                login_tokens[token] = {'username': username_from_state, 'expires': expiry_time}
                                print(f"[Login] SID: {sid} - Generated token: {token} for '{username_from_state}'")
                                emit('login_result', {'success': True, 'token': token}, room=sid)
                            else: # Emit failure
                                emit('login_result', {'success': False}, room=sid)

                            # Clean up state immediately (no delay needed)
                            print(f"[Login Cleanup] Removing state for SID: {sid} after verify.")
                            state['mode'] = None; client_states.pop(sid, None); return
                        else: # PIN not complete, emit update
                             emit('pin_update', { 'current_digit': PIN_DIGITS[state['pin_index']], 'pin_so_far': '*' * len(state['pin_entered']) }, room=sid)
                state['blink_counter'] = 0
        else: state['blink_counter'] = 0

        # Draw EAR & Threshold Text
        cv2.putText(frame, f"EAR: {avgEAR:.3f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(frame, f"Thresh: {BLINK_THRESH:.3f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # Encode & Emit Processed Frame
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
    print(f"Known faces dir: {os.path.abspath(KNOWN_FACES_DIR)}")
    print(f"User data file: {os.path.abspath(USER_DATA_FILE)}")
    print(f"Shape predictor: {os.path.abspath(DLIB_SHAPE_PREDICTOR)}")
    print(f"Initial known faces loaded: {len(known_face_names)}")
    print("Starting server on http://0.0.0.0:5000 ...")
    import eventlet
    try: eventlet.wsgi.server(eventlet.listen(('', 5000)), app, log_output=False)
    except Exception as e: print(f"\n!!! Failed to start server: {e} !!!")