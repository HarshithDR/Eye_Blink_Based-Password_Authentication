import face_recognition
import cv2
import numpy as np
import os
import pickle

# Path for saving known face encodings
ENCODINGS_PATH = "backend/known_faces.pkl"

def train_face(video_path, user_id):
    """
    Train a face recognition model from a video file.
    """
    video_capture = cv2.VideoCapture(video_path)
    known_faces = []
    known_ids = []

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break
        rgb_frame = frame[:, :, ::-1]  # Convert BGR to RGB
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        if face_encodings:
            known_faces.append(face_encodings[0])
            known_ids.append(user_id)

    video_capture.release()

    # Save face encodings
    if os.path.exists(ENCODINGS_PATH):
        with open(ENCODINGS_PATH, 'rb') as f:
            data = pickle.load(f)
    else:
        data = {"encodings": [], "ids": []}

    data["encodings"].extend(known_faces)
    data["ids"].extend(known_ids)

    with open(ENCODINGS_PATH, 'wb') as f:
        pickle.dump(data, f)

def recognize_face(frame):
    """
    Recognize a face in a given frame.
    """
    if not os.path.exists(ENCODINGS_PATH):
        return None

    with open(ENCODINGS_PATH, 'rb') as f:
        data = pickle.load(f)

    rgb_frame = frame[:, :, ::-1]
    face_locations = face_recognition.face_locations(rgb_frame)
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(data["encodings"], face_encoding)
        if True in matches:
            first_match_index = matches.index(True)
            return data["ids"][first_match_index]
    return None
