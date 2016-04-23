"""
Tests camera output
"""

import cv2


def show_webcam(mirror=False):
    cam = cv2.VideoCapture()  # Initialize camera

    while True:
        ret, img = cam.read()
        if mirror:
            img = cv2.flip(img, 1)

        if ret:
            cv2.imshow('Camera Output', img)
        else:
            print("No camera output!")

        if cv2.waitKey(1) == 27:
            break  # esc to quit

    cv2.destroyAllWindows()


def main():
    show_webcam(mirror=True)


if __name__ == '__main__':
    main()
