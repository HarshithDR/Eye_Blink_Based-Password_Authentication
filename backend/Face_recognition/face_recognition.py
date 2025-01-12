import pickle
from pathlib import Path
from collections import Counter
import face_recognition
import time
import cv2
    
Encodings_path = Path("encodings_output/encodings.pkl")

def save_pkl(encodings, Encodings_path) -> None:
    with Encodings_path.open(mode="wb") as f:
        pickle.dump(encodings, f)

def add_face_encodings(person_name, face_encodings, Encodings_path) -> None:
    with Encodings_path.open(mode="rb") as f:
        loaded_encodings = pickle.load(f)
        
    loaded_encodings["names"].append(person_name)
    loaded_encodings["encodings"].append(face_encodings)
    
    save_pkl(loaded_encodings, Encodings_path)
    

def encode_face(Encodings_path = Encodings_path, 
                person_name : str, 
                train_folder_path: Path, 
                model: str = "hog") -> None:
    image = face_recognition.load_image_file(train_folder_path)

    face_locations = face_recognition.face_locations(image, model=model)
    face_encodings = face_recognition.face_encodings(image, face_locations)

    add_face_encodings(person_name, face_encodings, Encodings_path)
    
def _recognize_face(unknown_encoding, loaded_encodings) -> None:
    """
    Given an unknown encoding and all known encodings, find the known
    encoding with the most matches.
    """
    boolean_matches = face_recognition.compare_faces(
        loaded_encodings["encodings"], unknown_encoding
    )
    votes = Counter(
        name
        for match, name in zip(boolean_matches, loaded_encodings["names"])
        if match
    )
    if votes:
        return votes.most_common(1)[0][0]
    
def recognize_faces(
    image_location: str,
    model: str = "hog",
    encodings_location: Path = Encodings_path) -> list:

    with encodings_location.open(mode="rb") as f:
        loaded_encodings = pickle.load(f)

    input_image = face_recognition.load_image_file(image_location)

    input_face_locations = face_recognition.face_locations(input_image, model=model)
    input_face_encodings = face_recognition.face_encodings(input_image, input_face_locations)

    faces_n_image_names = []

    for bounding_box, unknown_encoding in zip(input_face_locations, input_face_encodings):
        person_name = _recognize_face(unknown_encoding, loaded_encodings)
        if not person_name:
            person_name = "Unknown"
        faces_n_image_names.append[person_name]
        
    return faces_n_image_names

def capture_img():
    camera = cv2.VideoCapture(0)
    for i in range(10):
        time.sleep(1)
        return_value, image = camera.read()
        cv2.imwrite("\\backend\\Face_recognition\\temp_imgs\\",'temp'+str(i)+'.png', image)
    del(camera)