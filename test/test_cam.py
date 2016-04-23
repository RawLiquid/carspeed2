"""
Tests camera output
"""

import time

import cv2
import picamera
from picamera.array import PiRGBArray

rotation_degrees = 187  # Rotate camera output

# Define bounding box
upper_left_x = 138
upper_left_y = 157
lower_right_x = 462
lower_right_y = 193  # 183

THRESHOLD = 15


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


def test_processing(base, frame):
    """
    Test openCV processing algorithms
    :param frame: frame input from camera
    :return: frame object post-processing
    """

    # crop the frame to the monitored area, convert it to grayscale, and blur it
    # crop area defined by [y1:y2,x1:x2]
    # gray = frame[upper_left_y:lower_right_y, upper_left_x:lower_right_x]
    gray = frame

    # convert it to grayscale, and blur it
    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    # Use median filter at night to get rid of graininess
    gray = cv2.medianBlur(gray, 3)  # TODO: Test this
    # gray = cv2.GaussianBlur(gray, blur_size, 0)

    if base is None:
        base = gray.copy().astype("float")  # create a base image if it doesn't yet exist

    # compute the absolute difference between the current image and
    # base image and then turn everything lighter than THRESHOLD into
    # white
    frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(base))
    thresh = cv2.threshold(frameDelta, THRESHOLD, 255, cv2.THRESH_BINARY)[1]

    # dilate the thresholded image to fill in any holes, then find contours
    # on thresholded image
    thresh = cv2.dilate(thresh, None, iterations=2)
    (_, cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    base = cv2.accumulateWeighted(base, base, 0.5)  # attempt background removal

    return base, gray, cnts


def show_webcam(camera, capture):
    """
    Opens camera input and shows frame-by-frame
    :param capture: input from initialize camera
    :return: X window
    """

    base_image = None

    while True:
        for frame in camera.capture_continuous(capture, format='bgr', use_video_port=True):
            image = frame.array
            image = rotate_image(image)  # Rotate the image
            base_image, blurred, contours = test_processing(base_image, image)  # Run openCV image processing

            cv2.namedWindow('Blurred')
            cv2.imshow('Blurred', base_image)  # Show the frame in a window

            cv2.namedWindow('Contours', cv2.WINDOW_AUTOSIZE)
            cv2.drawContours(blurred, contours, -1, (255, 0, 0), 3)
            cv2.imshow('Contours', blurred)
            capture.truncate(0)  # Then, clear the window in prep for next frame

            if cv2.waitKey(1) == 27:
                break  # esc to quit

    cv2.destroyAllWindows()


def main():
    camera, capture = initialize_camera()
    show_webcam(camera, capture)


if __name__ == '__main__':
    main()
