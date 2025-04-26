import face_recognition
import cv2
import numpy as np
import os
import time

# --- Configuration ---
KNOWN_FACES_DIR = 'known_faces'
TOLERANCE = 0.6  # Lower tolerance means stricter matching (0.0 to 1.0)
FRAME_THICKNESS = 3
FONT_THICKNESS = 2
MODEL = 'hog'  # 'hog' is faster on CPU, 'cnn' is more accurate but requires GPU/CUDA
WINDOW_NAME = 'Face Recognition - Press Q to Quit'
WEBCAM_INDEX = 0 # 0 is usually the default built-in webcam

# --- Initialization ---
print("Loading known faces...")
known_face_encodings = []
known_face_names = []

# Load known faces and their encodings
if not os.path.exists(KNOWN_FACES_DIR):
    print(f"Error: Directory '{KNOWN_FACES_DIR}' not found.")
    print("Please create it and add subdirectories with images for each known person.")
    exit()

for name in os.listdir(KNOWN_FACES_DIR):
    person_dir = os.path.join(KNOWN_FACES_DIR, name)
    if os.path.isdir(person_dir):
        print(f"Processing images for: {name}")
        image_count = 0
        for filename in os.listdir(person_dir):
            filepath = os.path.join(person_dir, filename)
            try:
                # Check if it's an image file (basic check)
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                    print(f"  - Loading image: {filename}")
                    image = face_recognition.load_image_file(filepath)

                    # Find face encodings in the image
                    # Note: face_encodings returns a list of encodings for faces found.
                    # We assume one face per image for simplicity here.
                    encodings = face_recognition.face_encodings(image)

                    if len(encodings) > 0:
                        # Add the first found encoding to our known list
                        known_face_encodings.append(encodings[0])
                        known_face_names.append(name.replace("_", " ")) # Use directory name as person's name
                        image_count += 1
                        print(f"    Encoding found for {name}.")
                    else:
                        print(f"    Warning: No face found in {filename}.")
                else:
                     print(f"  - Skipping non-image file: {filename}")

            except Exception as e:
                print(f"    Error processing {filename}: {e}")
        if image_count == 0:
             print(f"Warning: No faces encoded for {name}. Check images in '{person_dir}'.")


if not known_face_encodings:
    print("Error: No known faces were loaded successfully. Exiting.")
    exit()

print(f"\n{len(known_face_names)} known individuals loaded.")
print("Starting video capture...")

# Initialize Webcam
video_capture = cv2.VideoCapture(WEBCAM_INDEX)
if not video_capture.isOpened():
    print(f"Error: Could not open video source (Webcam index: {WEBCAM_INDEX}).")
    exit()

# Variables for FPS calculation
prev_frame_time = 0
new_frame_time = 0

# --- Main Loop ---
while True:
    # Grab a single frame of video
    ret, frame = video_capture.read()
    if not ret:
        print("Error: Failed to capture frame. Exiting.")
        break

    # Resize frame for faster processing (optional)
    # small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    # Convert the image from BGR color (OpenCV) to RGB color (face_recognition)
    # rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # Use full frame if not resizing

    # Find all the faces and face encodings in the current frame of video
    # Using the chosen model ('hog' or 'cnn')
    face_locations = face_recognition.face_locations(rgb_frame, model=MODEL)
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

    face_names = []
    # Loop through each face found in the frame
    for face_encoding in face_encodings:
        # See if the face is a match for the known face(s)
        # compare_faces returns a list of True/False values for each known face
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=TOLERANCE)
        name = "Unknown" # Default name if no match found

        # Or instead, use the known face with the smallest distance to the new face
        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        best_match_index = np.argmin(face_distances) # Find the index of the known face with the smallest distance

        # Check if the best match distance is within tolerance and if matches[best_match_index] is True
        if matches[best_match_index] and face_distances[best_match_index] < TOLERANCE:
             name = known_face_names[best_match_index]

        face_names.append(name)

    # --- Display the results ---
    # Draw rectangles and labels on the original frame (BGR)
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        # Scale back up face locations if we resized the frame (not needed if using full frame)
        # top *= 4
        # right *= 4
        # bottom *= 4
        # left *= 4

        # Draw a box around the face
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), FRAME_THICKNESS) # Green box

        # Draw a label with a name below the face
        # Create a filled rectangle for the text background
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.8, (0, 0, 0), FONT_THICKNESS) # Black text

    # Calculate and display FPS (Frames Per Second)
    new_frame_time = time.time()
    fps = 1 / (new_frame_time - prev_frame_time)
    prev_frame_time = new_frame_time
    cv2.putText(frame, f"FPS: {int(fps)}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # Display the resulting image
    cv2.imshow(WINDOW_NAME, frame)

    # Hit 'q' on the keyboard to quit!
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Exit key pressed. Closing application.")
        break

# --- Cleanup ---
video_capture.release()
cv2.destroyAllWindows()
print("Application finished.")