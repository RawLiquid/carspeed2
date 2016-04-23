"""
Tests camera output
"""

import time

import cv2
import picamera
from picamera.array import PiRGBArray

rotation_degrees = 187


def initialize_camera():
    """
    Initialize the camera using picamera library
    :return: rawCapture object
    """

    camera = picamera.PiCamera()
    camera.resolution = (640, 480)
    camera.framerate = 30
    rawCapture = PiRGBArray(camera, size=(640, 480))
    time.sleep(0.5)  # Let camera stabilize

    return camera, rawCapture


def rotate_image(frame):
    """
    Takes frame input and rotates it so that it is true-to-life
    :return: image frame
    """

    # Rotate image
    rows, cols, placeholder = frame.shape
    M = cv2.getRotationMatrix2D((cols / 2, rows / 2), rotation_degrees, 1)
    image = cv2.warpAffine(frame, M, (rows, cols))

    return image


def show_webcam(camera, capture):
    """
    Opens camera input and shows frame-by-frame
    :param capture: input from initialize camera
    :return: X window
    """

    while True:
        for frame in camera.capture_continuous(capture, format='bgr', use_video_port=True):
            image = frame.array
            image = rotate_image(image)  # Rotate the image

            cv2.imshow('Camera Output', image)  # Show the frame in a window
            capture.truncate(0)  # Then, clear the window in prep for next frame

            if cv2.waitKey(1) == 27:
                break  # esc to quit

    cv2.destroyAllWindows()


def main():
    camera, capture = initialize_camera()
    show_webcam(camera, capture)


if __name__ == '__main__':
    main()
