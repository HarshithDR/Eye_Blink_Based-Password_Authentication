import cv2  
import dlib  
import imutils 
from scipy.spatial import distance as dist 
from imutils import face_utils 

def calculate_EAR(eye): 
    y1 = dist.euclidean(eye[1], eye[5]) 
    y2 = dist.euclidean(eye[2], eye[4]) 
    x1 = dist.euclidean(eye[0], eye[3]) 
  
    EAR = (y1+y2) / x1 
    return EAR 

cam = cv2.VideoCapture(0) 

def 