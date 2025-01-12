import cv2
import time

camera = cv2.VideoCapture(0)
for i in range(10):
    time.sleep(1)
    return_value, image = camera.read()
    cv2.imwrite('opencv'+str(i)+'.png', image)
del(camera)