// --- Global Variables (Client-Side) ---
let socket = null;
let videoElement = null;
let canvasElement = null;
let context = null;
let streamInterval = null;
const FRAME_RATE = 10; // Send frames approx 10 times per second

// --- Utility Functions ---
function getElement(id) {
    return document.getElementById(id);
}

function showElement(id) {
    const el = getElement(id);
    if (el) el.style.display = 'block';
}

function hideElement(id) {
    const el = getElement(id);
    if (el) el.style.display = 'none';
}

function setText(id, text) {
    const el = getElement(id);
    if (el) el.textContent = text;
}

function setImageSrc(id, src) {
     const el = getElement(id);
    if (el) {
        el.src = src;
        el.style.display = 'block';
    }
}

function enableButton(id) {
    const btn = getElement(id);
    if(btn) btn.disabled = false;
}
function disableButton(id) {
    const btn = getElement(id);
    if(btn) btn.disabled = true;
}

// --- Webcam and Streaming ---
async function startWebcam() {
    videoElement = getElement('video');
    canvasElement = getElement('canvas');
    if (!videoElement || !canvasElement) {
        console.error("Video or Canvas element not found");
        setText('status-message', 'Error: Video elements missing.'); // User login feedback
        setText('capture-status', 'Error: Video elements missing.'); // Admin feedback
        return false;
    }
    context = canvasElement.getContext('2d');

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        videoElement.srcObject = stream;
        videoElement.onloadedmetadata = () => {
            videoElement.play();
            // Start sending frames
            if (streamInterval) clearInterval(streamInterval); // Clear previous interval if any
            streamInterval = setInterval(sendFrame, 1000 / FRAME_RATE);
            console.log("Webcam started and streaming.");
            return true;
        };
    } catch (err) {
        console.error("Error accessing webcam:", err);
        setText('status-message', 'Error: Could not access webcam. Please grant permission.');
        setText('capture-status', 'Error: Could not access webcam. Please grant permission.');
        return false;
    }
    return false; // Reaches here if metadata fails to load quickly
}

function sendFrame() {
    if (!context || !videoElement || !socket || !socket.connected) {
        // console.warn("Cannot send frame - context, video, or socket not ready.");
        return;
    }
    // Draw video frame to canvas
    context.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
    // Get canvas data as JPEG data URL
    const frameData = canvasElement.toDataURL('image/jpeg', 0.7); // Adjust quality (0.0-1.0)
    // Send frame to backend
    socket.emit('frame_data', frameData);
}

function stopWebcam() {
    if (streamInterval) {
        clearInterval(streamInterval);
        streamInterval = null;
    }
    if (videoElement && videoElement.srcObject) {
        videoElement.srcObject.getTracks().forEach(track => track.stop());
        videoElement.srcObject = null;
        console.log("Webcam stopped.");
    }
}

// --- SocketIO Connection ---
function connectSocketIO() {
    // Ensure connection is closed if existing
    if (socket && socket.connected) {
        socket.disconnect();
    }
    // Connect (Flask-SocketIO default path)
    socket = io(); // Assumes server is on the same host/port

    socket.on('connect', () => {
        console.log('Connected to backend via SocketIO:', socket.id);
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from backend.');
        stopWebcam(); // Stop streaming if disconnected
    });

    socket.on('connect_error', (err) => {
        console.error('Socket connection error:', err);
        setText('status-message', 'Error: Cannot connect to server.');
         setText('capture-status', 'Error: Cannot connect to server.');
    });

     // --- Specific Handlers for Admin Page ---
    socket.on('admin_capture_ready', () => {
        console.log("Backend ready for admin capture. Starting webcam...");
        setText('capture-status', 'Camera ready. Look at the camera.');
        startWebcam(); // Start webcam only when backend confirms
    });

    socket.on('admin_status', (data) => {
        console.log("Admin status:", data.message);
        setText('capture-status', data.message);
    });

    socket.on('admin_capture_success', (data) => {
        console.log("Admin capture success:", data.message);
        setText('capture-status', data.message);
        setImageSrc('captured-image', data.image_path + '?t=' + new Date().getTime()); // Add timestamp to avoid caching
        hideElement('video-container');
        stopWebcam();
        enableButton('add-user-btn'); // Enable Add User button after successful capture
        disableButton('capture-btn');
    });

     socket.on('admin_error', (data) => {
        console.error("Admin error:", data.message);
        setText('capture-status', `Error: ${data.message}`);
        stopWebcam();
        hideElement('video-container');
    });

    // --- Specific Handlers for User Login Page ---
    socket.on('login_status', (data) => {
        console.log("Login status update:", data);
        setText('status-message', data.message);
        if (data.status === 'pin_entry') {
            showElement('pin-entry-area');
            setText('pin-so-far', '*'.repeat(data.pin_so_far?.length || 0));
            setText('current-digit', data.current_digit);
        } else {
             hideElement('pin-entry-area');
        }
    });

     socket.on('pin_update', (data) => {
        // console.log("PIN Update:", data);
        setText('pin-so-far', data.pin_so_far);
        setText('current-digit', data.current_digit);
    });

    socket.on('login_result', (data) => {
        console.log("Login result:", data);
        stopWebcam(); // Stop camera on result
        if (data.success) {
            setText('status-message', 'Login Successful! Redirecting...');
            window.location.href = '/user_dashboard'; // Redirect on success
        } else {
            setText('status-message', 'Login Failed. Redirecting...');
             window.location.href = '/login_failed'; // Redirect on failure
        }
    });
}

// --- Page Specific Setup Functions ---

function setupAdminPage() {
    console.log("Setting up Admin Page");
    connectSocketIO();

    const captureBtn = getElement('capture-btn');
    const addUserBtn = getElement('add-user-btn');
    const usernameInput = getElement('username');

    captureBtn.addEventListener('click', () => {
        const username = usernameInput.value.trim();
        if (!username) {
            alert("Please enter a username first.");
            return;
        }
        if (!/^[a-zA-Z0-9_]+$/.test(username)){
             alert("Username can only contain letters, numbers, and underscores.");
             return;
        }

        console.log("Capture button clicked for username:", username);
        setText('capture-status', 'Initializing capture...');
        showElement('video-container');
        disableButton('capture-btn'); // Disable while attempting capture
        disableButton('add-user-btn'); // Disable add user until capture is done
        hideElement('captured-image'); // Hide previous image

        // Tell backend to prepare for capture
        socket.emit('start_admin_capture', { username: username });
    });

    addUserBtn.addEventListener('click', async () => {
        const username = usernameInput.value.trim();
        const pin = getElement('pin').value;
        const balance = getElement('balance').value;

        if (!username || !pin || !balance) {
             setText('add-user-status', 'Error: All fields are required.');
             return;
        }
         if (!/^\d{4}$/.test(pin)) {
             setText('add-user-status', 'Error: PIN must be exactly 4 digits.');
            return;
        }

        disableButton('add-user-btn'); // Prevent double clicks
        setText('add-user-status', 'Adding user...');

        // Send data using fetch API (standard form submission alternative)
        const formData = new FormData();
        formData.append('username', username);
        formData.append('pin', pin);
        formData.append('balance', balance);

        try {
            const response = await fetch('/add_user', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.success) {
                setText('add-user-status', `Success: ${result.message}`);
                // Optionally clear form or redirect
                getElement('admin-form').reset(); // Reset form fields
                hideElement('captured-image');
                enableButton('capture-btn'); // Re-enable capture for next user
                 disableButton('add-user-btn'); // Keep add disabled until next capture
                 setText('capture-status', ''); // Clear capture status
            } else {
                setText('add-user-status', `Error: ${result.message}`);
                enableButton('add-user-btn'); // Re-enable on failure
            }
        } catch (error) {
            console.error("Error adding user:", error);
             setText('add-user-status', 'Error: Could not connect to server to add user.');
             enableButton('add-user-btn'); // Re-enable on failure
        }
    });
}

function setupUserLoginPage() {
    console.log("Setting up User Login Page");
    connectSocketIO();

    // Immediately try to start webcam and tell backend to begin recognition
    startWebcam().then(success => {
         if (success && socket && socket.connected) {
              console.log("Webcam started, sending start signal to backend.");
              socket.emit('start_user_login');
              setText('status-message', 'Webcam active. Looking for face...');
         } else if (socket && socket.connected) {
             // If webcam failed but socket ok, inform backend is possible (though unlikely useful)
              console.log("Webcam failed, but informing backend.");
              // socket.emit('webcam_failed'); // Optional: inform backend
         } else {
              console.log("Webcam or Socket failed to initialize.");
         }
    });
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    stopWebcam();
    if (socket && socket.connected) {
        socket.disconnect();
    }
});