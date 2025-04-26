// --- Global Variables (Client-Side) ---
let socket = null;
let videoElement = null;
let canvasElement = null;
let context = null;
let streamInterval = null;
const FRAME_RATE = 10; // Send frames approx 10 times per second

// --- Utility Functions ---
function getElement(id) { return document.getElementById(id); }
function showElement(id) { const el = getElement(id); if (el) el.style.display = 'block'; }
function hideElement(id) { const el = getElement(id); if (el) el.style.display = 'none'; }
function setText(id, text) { const el = getElement(id); if (el) el.textContent = text; }
function setImageSrc(id, src) { const el = getElement(id); if (el) { el.src = src; el.style.display = 'block'; } }
function enableButton(id) { const btn = getElement(id); if(btn) btn.disabled = false; }
function disableButton(id) { const btn = getElement(id); if(btn) btn.disabled = true; }

// --- Webcam and Streaming ---
async function startWebcam() {
    console.log("[Webcam] Attempting to start webcam...");
    videoElement = getElement('video');
    canvasElement = getElement('canvas');
    if (!videoElement || !canvasElement) {
        console.error("[Webcam] Video or Canvas element not found.");
        setText('status-message', 'Error: Required HTML elements missing.');
        setText('capture-status', 'Error: Required HTML elements missing.');
        return false; // Indicate failure
    }
    context = canvasElement.getContext('2d');

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        console.log("[Webcam] Media stream acquired.");
        videoElement.srcObject = stream;
        // Use a promise to wait for the video to be ready
        await new Promise((resolve, reject) => {
             videoElement.onloadedmetadata = () => {
                console.log("[Webcam] Video metadata loaded.");
                videoElement.play().then(resolve).catch(reject); // Play and resolve promise
             };
             videoElement.onerror = (e) => { // Handle potential video errors
                  console.error("[Webcam] Video element error:", e);
                  reject(new Error("Video element error"));
             };
        });
        console.log("[Webcam] Video playing.");

        // Start sending frames ONLY if the socket is connected
        if (socket && socket.connected) {
             if (streamInterval) clearInterval(streamInterval);
             streamInterval = setInterval(sendFrame, 1000 / FRAME_RATE);
             console.log("[Webcam] Streaming frames started.");
             return true; // Indicate success
        } else {
             console.warn("[Webcam] Webcam started but socket not ready. Stopping stream.");
             stream.getTracks().forEach(track => track.stop());
             videoElement.srcObject = null;
             return false;
        }

    } catch (err) {
        console.error("[Webcam] Error accessing or starting webcam:", err.name, err.message);
        let errorMsg = 'Error: Could not access webcam.';
        if (err.name === "NotAllowedError") { errorMsg = 'Error: Webcam permission denied.'; }
        else if (err.name === "NotFoundError") { errorMsg = 'Error: No webcam found.'; }
        else if (err.name === "NotReadableError") { errorMsg = 'Error: Webcam is already in use.'; }
        setText('status-message', errorMsg);
        setText('capture-status', errorMsg);
        return false; // Indicate failure
    }
}

function sendFrame() {
    if (!context || !videoElement || videoElement.paused || videoElement.ended || !socket || !socket.connected) { return; }
    try {
        context.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
        const frameData = canvasElement.toDataURL('image/jpeg', 0.7);
        socket.emit('frame_data', frameData);
    } catch (e) { console.error("[Webcam] Error sending frame:", e); }
}

function stopWebcam() {
    console.log("[Webcam] Executing stopWebcam()...");
    if (streamInterval) {
        clearInterval(streamInterval);
        streamInterval = null;
        console.log("[Webcam] Streaming interval cleared.");
    } else {
        console.log("[Webcam] No streaming interval found to clear.");
    }
    if (videoElement && videoElement.srcObject) {
        videoElement.srcObject.getTracks().forEach(track => {
            console.log(`[Webcam] Stopping track: ${track.label} (${track.id})`);
            track.stop();
        });
        videoElement.srcObject = null; // Release object
        console.log("[Webcam] Media tracks stopped.");
    } else {
        console.log("[Webcam] No active stream/srcObject found on video element.");
    }
}

// --- Keypad Highlight Helper ---
function updateKeypadHighlight(currentDigit) {
    const previousHighlight = document.querySelector('.keypad-button.highlighted');
    if (previousHighlight) { previousHighlight.classList.remove('highlighted'); }
    const newHighlightButton = document.getElementById(`keypad-${currentDigit}`);
    if (newHighlightButton) { newHighlightButton.classList.add('highlighted'); }
    // else { console.warn(`Keypad button for digit ${currentDigit} not found.`); } // Reduce noise
}

// --- SocketIO Connection ---
function connectSocketIO(pageType) { // pageType: 'admin' or 'user_login'
    if (socket && socket.connected) {
        console.log("[SocketIO] Disconnecting existing socket before reconnecting.");
        socket.disconnect();
    }
    console.log(`[SocketIO] Attempting connection for page: ${pageType}...`);
    socket = io();

    // --- Standard Socket Event Handlers ---
    socket.on('connect', () => {
        console.log('[SocketIO] Connected successfully:', socket.id);
        if (pageType === 'user_login') {
            console.log("[SocketIO] Handling post-connect for user_login page.");
            hideElement('pin-entry-area');
            hideElement('welcome-message');
            setText('status-message', 'Connected. Starting camera...'); // Update status
            startWebcam().then(success => {
                if (success && socket && socket.connected) {
                    console.log("[SocketIO] Webcam ok. Emitting 'start_user_login'.");
                    socket.emit('start_user_login');
                    // Status message will be updated by backend via 'login_status'
                } else {
                    console.error("[SocketIO] Failed post-connect: Webcam start failed or socket disconnected.");
                    // Error message should be set by startWebcam() if it failed
                }
            });
        } else if (pageType === 'admin') {
             console.log("[SocketIO] Handling post-connect for admin page.");
             // Enable capture button now that socket is ready
             enableButton('capture-btn');
             disableButton('add-user-btn'); // Ensure add starts disabled
             setText('capture-status', 'Ready to capture. Enter user details.'); // Set initial admin status
        }
    });

    socket.on('disconnect', (reason) => {
        console.warn('[SocketIO] Disconnected:', reason);
        stopWebcam();
        setText('status-message', 'Disconnected. Please refresh.');
        setText('capture-status', 'Disconnected. Please refresh.');
        hideElement('pin-entry-area'); hideElement('welcome-message');
        disableButton('capture-btn'); disableButton('add-user-btn');
     });
    socket.on('connect_error', (err) => {
        console.error('[SocketIO] Connection error:', err);
        setText('status-message', 'Connection Error. Refresh page.');
        setText('capture-status', 'Connection Error. Refresh page.');
    });

    // --- Specific Backend Message Handlers ---

    // -- Admin Page Handlers --
    socket.on('admin_capture_ready', () => {
        console.log("[SocketIO] Received 'admin_capture_ready'. Backend waiting for frames.");
        setText('capture-status', 'Camera active. Look directly at the camera.');
    });
    socket.on('admin_status', (data) => {
        console.log("[SocketIO] Received 'admin_status':", data.message);
        setText('capture-status', data.message);
    });
    socket.on('admin_capture_success', (data) => {
        console.log("[SocketIO] Received 'admin_capture_success':", data.message);
        setText('capture-status', data.message);
        setImageSrc('captured-image', data.image_path + '?t=' + new Date().getTime()); // Add timestamp
        hideElement('video-container');
        stopWebcam();
        enableButton('add-user-btn'); // Enable Add User button
        // Optionally re-enable capture btn here or wait until user added? Let's wait.
        // enableButton('capture-btn');
    });
    socket.on('admin_error', (data) => {
        console.error("[SocketIO] Received 'admin_error':", data.message);
        setText('capture-status', `Error: ${data.message}`);
        stopWebcam();
        hideElement('video-container');
        enableButton('capture-btn'); // Allow retry
        disableButton('add-user-btn');
    });

    // -- User Login Page Handlers --
    socket.on('login_status', (data) => {
        console.log("[SocketIO] Received 'login_status':", data);
        setText('status-message', data.message);

        const liveVideo = getElement('video');
        const processedFeed = getElement('processed_feed');

        if (data.status === 'pin_entry') {
            setText('recognized-user-name', data.user || 'User');
            showElement('welcome-message');
            showElement('pin-entry-area');
            // *** Switch to processed feed view ***
            hideElement('video'); // Hide live feed
            showElement('processed_feed'); // Show image tag for processed frames
            // Set initial PIN display and highlight
            const pinLength = (typeof data.pin_so_far === 'string') ? data.pin_so_far.length : 0;
            setText('pin-so-far', '*'.repeat(pinLength));
            updateKeypadHighlight(data.current_digit);
            setText('status-message', 'Face recognized! Blink on highlighted digit.');
        } else {
            // If status is not pin_entry (e.g., recognizing, verifying, error), hide PIN elements
            hideElement('pin-entry-area');
            hideElement('welcome-message');
            // *** Switch back to live feed view ***
            showElement('video'); // Show live feed
            hideElement('processed_feed'); // Hide processed image tag
            processedFeed.src = ""; // Clear old image src
        }
        if (data.status === 'error') {
            console.error("[SocketIO] Backend login error:", data.message);
            stopWebcam();
            // Ensure UI is reset
             hideElement('pin-entry-area'); hideElement('welcome-message');
             showElement('video'); hideElement('processed_feed');
        }
    });

    socket.on('pin_frame_update', (data) => {
        // This message arrives continuously during PIN mode
        const processedFeed = getElement('processed_feed');
        if (processedFeed && data.image_data) {
            processedFeed.src = data.image_data; // Update the displayed image
        }
        // Update PIN display and highlight based on data in this message
        const pinLength = (typeof data.pin_so_far === 'string') ? data.pin_so_far.length : 0;
        setText('pin-so-far', '*'.repeat(pinLength));
        updateKeypadHighlight(data.current_digit);
    });

    socket.on('pin_update', (data) => {
        console.log("[SocketIO] Received 'pin_update' (likely after blink):", data);
        const pinLength = (typeof data.pin_so_far === 'string') ? data.pin_so_far.length : 0;
        setText('pin-so-far', '*'.repeat(pinLength));
        updateKeypadHighlight(data.current_digit);
    });

    socket.on('login_result', (data) => {
        console.log("[SocketIO] Received 'login_result':", data); // Log reception
        const statusMsgElement = getElement('status-message');

        console.log("[SocketIO] Stopping webcam before handling result...");
        stopWebcam();

        hideElement('pin-entry-area'); hideElement('welcome-message');
        showElement('video'); hideElement('processed_feed'); getElement('processed_feed').src="";

        if (data.success && data.token) { // Check for success AND token
            statusMsgElement.textContent = 'Login Successful! Completing login...';
            console.log(`[SocketIO] Login successful. Got token: ${data.token}. Redirecting via token.`);
            try {
                // *** Redirect to the token confirmation route ***
                window.location.replace(`/confirm_login/${data.token}`);
            } catch (e) {
                console.error("[SocketIO] Error during token redirect attempt:", e);
                // Provide fallback link to general login (token cannot be easily put in link)
                statusMsgElement.innerHTML = 'Login Success! Redirect failed. Please <a href="/user_login">try logging in again</a>.';
            }
        } else if (data.success && !data.token) {
             // Handle case where backend reported success but didn't send token (error)
             console.error("[SocketIO] Login reported success, but NO token received!");
             statusMsgElement.textContent = 'Login Error: Verification incomplete. Please try again.';
        }
        else { // Handle explicit failure (data.success is false)
            statusMsgElement.textContent = 'Login Failed. Redirecting...';
            console.log("[SocketIO] Login failed. Attempting redirect (replace) to /login_failed");
             try {
                window.location.replace('/login_failed');
             } catch (e) {
                console.error("[SocketIO] Error during failed redirect attempt:", e);
                 statusMsgElement.innerHTML = 'Login Failed. <a href="/login_failed">Click here</a>.';
             }
        }
    });


} // End of connectSocketIO

// --- Page Specific Setup Functions ---
function setupAdminPage() {
    console.log("Setting up Admin Page...");
    connectSocketIO('admin'); // Connect socket

    const captureBtn = getElement('capture-btn');
    const addUserBtn = getElement('add-user-btn');
    const usernameInput = getElement('username');

    // Initial button states set after socket connect now
    // disableButton('capture-btn'); // Initially disabled
    // disableButton('add-user-btn');

    captureBtn.addEventListener('click', () => {
        const username = usernameInput.value.trim();
        if (!username || !/^[a-zA-Z0-9_]+$/.test(username)) {
            alert("Valid username required (letters, numbers, underscores)."); return;
        }
        if (!socket || !socket.connected) { alert("Not connected. Please wait."); return; }

        console.log("[Admin] Capture button clicked for:", username);
        setText('capture-status', 'Starting camera...');
        showElement('video-container');
        disableButton('capture-btn'); disableButton('add-user-btn');
        hideElement('captured-image');

        // Start webcam ON DEMAND
        startWebcam().then(success => {
            if (success && socket && socket.connected) {
                // Only emit start_admin_capture AFTER webcam is confirmed running
                console.log("[Admin] Webcam ok. Emitting 'start_admin_capture'.");
                socket.emit('start_admin_capture', { username: username });
            } else {
                 console.error("[Admin] Failed to start webcam for capture.");
                 setText('capture-status', 'Error: Failed to start camera.');
                 enableButton('capture-btn'); // Allow retry
                 hideElement('video-container');
            }
        });
    });

    addUserBtn.addEventListener('click', async () => {
        console.log("[Admin] Add User button clicked.");
        // ... (Keep validation logic for fields) ...
        const username = usernameInput.value.trim();
        const pin = getElement('pin').value;
        const balance = getElement('balance').value;
        if (!username || !pin || !balance) { setText('add-user-status', 'Error: All fields required.'); return; }
        if (!/^\d{4}$/.test(pin)) { setText('add-user-status', 'Error: PIN must be 4 digits.'); return; }
        const capturedImg = getElement('captured-image');
        if (!capturedImg || !capturedImg.src || capturedImg.style.display === 'none') {
             setText('add-user-status', 'Error: Face capture required first.'); return;
        }

        disableButton('add-user-btn');
        setText('add-user-status', 'Adding user...');

        const formData = new FormData();
        formData.append('username', username); formData.append('pin', pin); formData.append('balance', balance);

        try {
            const response = await fetch('/add_user', { method: 'POST', body: formData });
            const result = await response.json();
            if (response.ok && result.success) {
                setText('add-user-status', `Success: ${result.message}`);
                getElement('admin-form').reset();
                hideElement('captured-image');
                enableButton('capture-btn'); // Re-enable capture for next
                disableButton('add-user-btn'); // Keep add disabled
                setText('capture-status', 'User added. Ready for next capture.');
            } else {
                const errorMsg = result.message || `Error ${response.status}`;
                setText('add-user-status', `Error: ${errorMsg}`);
                enableButton('add-user-btn'); // Allow retry
            }
        } catch (error) {
            console.error("[Admin] Network error during add user:", error);
            setText('add-user-status', 'Network Error. Could not add user.');
            enableButton('add-user-btn');
        }
    }); // End addUserBtn listener
} // End setupAdminPage

function setupUserLoginPage() {
    console.log("Setting up User Login Page...");
    setText('status-message', 'Connecting...'); // Initial status
    connectSocketIO('user_login'); // Connect socket, which then handles webcam+emit
} // End setupUserLoginPage

// --- Global Cleanup ---
window.addEventListener('beforeunload', (event) => {
    console.log("Page unloading. Stopping webcam and disconnecting socket.");
    stopWebcam();
    if (socket && socket.connected) { socket.disconnect(); }
});

// --- Ensure the correct setup function is called in HTML ---
// Add this to admin.html: <script>setupAdminPage();</script>
// Add this to user_login.html: <script>setupUserLoginPage();</script>