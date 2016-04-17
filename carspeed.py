# import the necessary packages

# TODO: Figure out logic to detect if two vehicles are in frame

import math
import os
import time
import datetime
from statistics import median
from uuid import uuid4 as uuid

import cv2
import numpy as np
from collections import Counter
from picamera import PiCamera
from picamera.array import PiRGBArray
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db import Vehicles, Log

use_x = False
show_bounds = False
showImage = False

engine = create_engine('postgresql://speedcam:Rward0232@localhost/speedcamdb')
DBSession = sessionmaker(bind=engine)
session = DBSession()

# define some constants
RTL_Distance = 85  # Right to left distance to median
LTR_Distance = 50  # Left to right distance to median
THRESHOLD = 15
SPEED_THRESHOLD = 40
MINIMUM_SPEED = 20  # Don't detect cars in parking lots, walkers, and slow drivers
MAXIMUM_SPEED = 70  # Anything higher than this is likely to be noise.
MIN_AREA = 175
BLURSIZE = (15, 15)
IMAGEWIDTH = 640
IMAGEHEIGHT = 480
RESOLUTION = [IMAGEWIDTH, IMAGEHEIGHT]
FOV = 53.5
FPS = 15
set_by_drawing = False  # Can either set bounding box manually, or by drawing rectangle on screen
rotation_degrees = 187  # Rotate image by this amount to create flat road

#if not os.environ['DISPLAY']:  #If SSH'd in, just use the preset parameters and don't try to open images
#    use_x = False


timeOn = datetime.datetime.now()  # This is used for the log
sessionID = uuid()
current_id = None
initial_time = None
last_mph = None


def is_nighttime():
    now = datetime.datetime.now().time()

    if now >= datetime.time(20, 00) and now <= datetime.time(7, 00):
        return True

    else:
        return False


def set_framerate_by_time(FPS, now):
    """
    Sets framerate based on time of day, using a lower value for night.
    :return: None - passes straight to camera
    """

    now = now.time()

    if is_nighttime():
        if FPS != 15:
            FPS = 15
            print("Setting FPS to {0}.".format(FPS))
            camera.framerate = FPS
            time.sleep(3)

    else:
        if FPS != 30:
            FPS = 30
            print("Setting FPS to {0}.".format(FPS))
            FPS = 30
            camera.framerate = FPS


def log_entry(in_out, current_id):
    """
    Put usage in log table
    """

    if in_out == "in" and current_id == None:
        new_entry = Log(
            sessionID = sessionID,
            timeOn = timeOn
        )

        session.add(new_entry)
        session.commit()

        current_log_id = new_entry.id

        return current_log_id


    elif in_out == "out" and current_id:
        logEntry = Log.query.filter_by(sessionID=sessionID).first()
        logEntry.timeOff = datetime.datetime.now()
        session.commit()

        return None


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


# place a prompt on the displayed image
def prompt_on_image(txt):
    global image
    cv2.putText(image, txt, (10, 35),
    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)


# calculate speed from pixels and time
def get_speed(pixels, ftperpixel, secs):
    if secs > 0.0:
        return ((pixels * ftperpixel)/ secs) * 0.681818  
    else:
        return 0.0


# calculate elapsed seconds
def secs_diff(endTime, begTime):
    diff = (endTime - begTime).total_seconds()
    return diff    


# mouse callback function for drawing capture area
def draw_rectangle(event,x,y,flags,param):
    global ix,iy,fx,fy,drawing,setup_complete,image, org_image, prompt
 
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix,iy = x,y
 
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing == True:
            image = org_image.copy()
            prompt_on_image(prompt)
            cv2.rectangle(image,(ix,iy),(x,y),(0,255,0),2)
  
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        fx,fy = x,y
        image = org_image.copy()
        prompt_on_image(prompt)
        cv2.rectangle(image,(ix,iy),(fx,fy),(0,255,0),2)


# Log usage
current_id = log_entry("in", current_id)

# the following enumerated values are used to make the program more readable
WAITING = 0
TRACKING = 1
SAVING = 2
UNKNOWN = 0
LEFT_TO_RIGHT = 1
RIGHT_TO_LEFT = 2

# calculate the the width of the image at the distance specified

def calculate_ftperpixel(DISTANCE, IMAGEWIDTH):
    frame_width_ft = 2 * (math.tan(math.radians(FOV * 0.5)) * DISTANCE)
    ftperpixel = frame_width_ft / float(IMAGEWIDTH)

    return ftperpixel


def grab_rgb(image, c):
    pixels = []

    # TODO: Convert to real code
    # Detect pixel values (RGB)
    mask = np.zeros_like(image)
    cv2.drawContours(mask, c, -1, color=255, thickness=-1)

    points = np.where(mask == 255)

    for point in points:
        pixel = (image[point[1], point[0]])
        pixel = pixel.tolist()
        pixels.append(pixel)

    pixels = [tuple(l) for l in pixels]
    car_color = (pixels[1])

    r = car_color[0]
    g = car_color[1]
    b = car_color[2]

    pixel_string = '{0},{1},{2}'.format(r, g, b)

    print("Car RGB: {0}".format(pixel_string))

    return pixel_string


def display(mode):
    """
    Prints a status display to screen
    :param mode: which info should be displayed: tracking, car added, etc.
    :return: stdout.
    """

    # TODO: Finish this function and use it.

    print("====================")
    print("Car Speed Detector")
    print("====================")
    print("Last car detected: {}")
    print("Last database commit: {}")

    if mode == 'waiting':
        print("No vehicle within bounding box.")
        pass
    elif mode == 'tracking':
        print("Tracking vehicle.")
        pass
    elif mode == 'stuckinloop':
        print("Got caught in tracking loop. Capturing new base image.")
        pass
    elif mode == 'startup':
        pass


# state maintains the state of the speed computation process
# if starts as WAITING
# the first motion detected sets it to TRACKING
 
# if it is tracking and no motion is found or the x value moves
# out of bounds, state is set to SAVING and the speed of the object
# is calculated
# initial_x holds the x value when motion was first detected
# last_x holds the last x value before tracking was was halted
# depending upon the direction of travel, the front of the
# vehicle is either at x, or at x+w 
# (tracking_end_time - tracking_start_time) is the elapsed time
# from these the speed is calculated and displayed
 
state = WAITING
direction = UNKNOWN
initial_x = 0
last_x = 0
 
#-- other values used in program
base_image = None
abs_chg = 0
mph = 0
secs = 0.0
ix,iy = -1,-1
fx,fy = -1,-1
drawing = False
setup_complete = False
tracking = False
text_on_image = 'No cars'
loop_count = 0
prompt = ''

# initialize the camera 
camera = PiCamera()
camera.resolution = RESOLUTION
camera.framerate = FPS
camera.vflip = False
camera.hflip = False
camera.rotate = 90

rawCapture = PiRGBArray(camera, size=camera.resolution)
# allow the camera to warm up
time.sleep(0.9)

# Set up the bounding box for speed detection
# create an image window and place it in the upper left corner of the screen
if use_x:
    cv2.namedWindow("Speed Camera")
    cv2.moveWindow("Speed Camera", 10, 40)

    # call the draw_rectangle routines when the mouse is used
    cv2.setMouseCallback('Speed Camera', draw_rectangle)

    # grab a reference image to use for drawing the monitored area's boundary
    camera.capture(rawCapture, format="bgr", use_video_port=True)
    image = rawCapture.array
    rows, cols, placeholder = image.shape
    M = cv2.getRotationMatrix2D((cols / 2, rows / 2), rotation_degrees, 1)
    image = cv2.warpAffine(image, M, (cols, rows))
    rawCapture.truncate(0)
    org_image = image.copy()

    prompt = "Define the monitored area - press 'c' to continue"
    prompt_on_image(prompt)

    # wait while the user draws the monitored area's boundry
    while not setup_complete:
        cv2.imshow("Speed Camera", image)

        # wait for for c to be pressed
        key = cv2.waitKey(1) & 0xFF

        # if the `c` key is pressed, break from the loop
        if key == ord("c"):
            break

    # the monitored area is defined, time to move on
    prompt = "Press 'q' to quit"

    # since the monitored area's bounding box could be drawn starting
    # from any corner, normalize the coordinates

    if fx > ix:
        upper_left_x = ix
        lower_right_x = fx
    else:
        upper_left_x = fx
        lower_right_x = ix

    if fy > iy:
        upper_left_y = iy
        lower_right_y = fy
    else:
        upper_left_y = fy
        lower_right_y = iy
else:
    # Define manually because my camera is mounted
    upper_left_x = 140
    upper_left_y = 173
    lower_right_x = 311
    lower_right_y = 205
     
monitored_width = lower_right_x - upper_left_x
monitored_height = lower_right_y - upper_left_y

print("Initial Parameters:")
print(" Upper left_x:               {}".format(upper_left_x))
print(" Upper left_y:               {}".format(upper_left_y))
print(" Lower right_x:              {}".format(lower_right_x))
print(" Lower right_y:              {}".format(lower_right_y))
print(" Monitored width:            {}".format(monitored_width))
print(" Monitored height:           {}".format(monitored_height))
print(" Monitored area:             {}".format(monitored_width * monitored_height))
print(" FPS:                        {}".format(FPS))

# Remove duplicate entries from table
clean = text("DELETE FROM vehicles\
  WHERE id IN (SELECT id\
  FROM (SELECT id,\
  ROW_NUMBER() OVER (partition BY speed ORDER BY id) AS rnum\
  FROM vehicles) t\
  WHERE t.rnum > 1);")

# capture frames from the camera (using capture_continuous.
#   This keeps the picamera in capture mode - it doesn't need
#   to prep for each frame's capture.
#   First, open up the PostgreSQL database.

mph_list = []
id = None
motion_loop_count = 0
tracking_start = None
commit_counter = 0

try:
    for frame in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):

        # initialize the timestamp
        timestamp = datetime.datetime.now()

        # Set frame rate based on time
        # set_framerate_by_time(FPS, timestamp)

        # grab the raw NumPy array representing the image, and rotate it so that it's flat
        image = frame.array
        rows, cols, placeholder = image.shape
        M = cv2.getRotationMatrix2D((cols / 2, rows / 2), rotation_degrees, 1)
        image = cv2.warpAffine(image, M, (rows, cols))

        # crop the frame to the monitored area, convert it to grayscale, and blur it
        # crop area defined by [y1:y2,x1:x2]
        gray = image[upper_left_y:lower_right_y, upper_left_x:lower_right_x]

        # convert it to grayscale, and blur it
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, BLURSIZE, 0)

        if base_image is None or motion_loop_count >= 50 and motion_found == False:
            if motion_loop_count >= 50 and motion_found == False:
                print("Caught motion loop. Creating new base snapshot")
                motion_loop_count = 0
            base_image = gray.copy().astype("float")
            lastTime = timestamp
            rawCapture.truncate(0)

            if use_x:
                cv2.imshow("Speed Camera", image)
            continue

        # compute the absolute difference between the current image and
        # base image and then turn eveything lighter than THRESHOLD into
        # white
        frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(base_image))
        thresh = cv2.threshold(frameDelta, THRESHOLD, 255, cv2.THRESH_BINARY)[1]

        # dilate the thresholded image to fill in any holes, then find contours
        # on thresholded image
        thresh = cv2.dilate(thresh, None, iterations=2)
        (_, cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # look for motion
        motion_found = False
        biggest_area = 0

        # examine the contours, looking for the largest one
        for c in cnts:
            (x, y, w, h) = cv2.boundingRect(c)
            # get an approximate area of the contour
            found_area = w * h
            # find the largest bounding rectangle
            if (found_area > MIN_AREA) and (found_area > biggest_area):
                biggest_area = found_area
                motion_found = True

                # if not is_nighttime():
                #    rgb = grab_rgb(image, c)
                # else:
                #    rgb = 'nighttime'

        if motion_found and motion_loop_count < 50:
            committed = False
            if state == WAITING:
                clear_screen()
                # intialize tracking
                state = TRACKING
                tracking_start = datetime.datetime.now()
                initial_x = x
                last_x = x
                initial_time = timestamp
                last_mph = 0
                text_on_image = 'Tracking'
                print(text_on_image)
                motion_loop_count = 0

            else:

                if state == TRACKING:
                    if x >= last_x:
                        direction = LEFT_TO_RIGHT
                        ftperpixel = calculate_ftperpixel(LTR_Distance, IMAGEWIDTH)
                        abs_chg = x + w - initial_x
                        dir = "North"

                    else:
                        direction = RIGHT_TO_LEFT
                        dir = "South"
                        abs_chg = initial_x - x
                        ftperpixel = calculate_ftperpixel(RTL_Distance, IMAGEWIDTH)
                    secs = secs_diff(timestamp, initial_time)
                    mph = get_speed(abs_chg, ftperpixel, secs)

                    if mph >= MINIMUM_SPEED and mph < MAXIMUM_SPEED:
                        mph_list.append(mph)

                    if len(mph_list) >= 3:

                        if ((x <= 2) and (direction == RIGHT_TO_LEFT)) and committed == False \
                                or ((x + w >= monitored_width - 2) and (
                                            direction == LEFT_TO_RIGHT)) and committed == False:
                            state = SAVING

                            new_vehicle = Vehicles(  # Table for statistics calculations
                                sessionID=sessionID,
                                datetime=datetime.datetime.now(),
                                speed=median(mph_list),
                                direction=dir,
                                #color=rgb,
                                rating=motion_loop_count
                            )
                            session.add(new_vehicle)
                            id = None
                            committed = True
                            clear_screen()
                            print("Added new vehicle: {0} MPH".format(round(median(mph_list), 2)))

                            mph_list = []

                    last_x = x

            motion_loop_count += 1

        else:
            if state != WAITING:
                state = WAITING
                direction = UNKNOWN
                text_on_image = 'No Car Detected'
                print(text_on_image)
                mph_list = []
                id = None
                motion_loop_count = 0

        # only update image and wait for a keypress when waiting for a car
        # or if 50 frames have been processed in the WAITING state.
        # This is required since waitkey slows processing.
        if (state == WAITING) or (loop_count > 50):

            # draw the text and timestamp on the frame
            cv2.putText(image, datetime.datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
                        (10, image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 1)
            cv2.putText(image, "Road Status: {}".format(text_on_image), (10, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

            if use_x:
                # define the monitored area right and left boundary
                cv2.line(image, (upper_left_x, upper_left_y), (upper_left_x, lower_right_y), (0, 255, 0))
                cv2.line(image, (lower_right_x, upper_left_y), (lower_right_x, lower_right_y), (0, 255, 0))

            # show the frame and check for a keypress
            if use_x:
                prompt_on_image(prompt)
                cv2.imshow("Speed Camera", image)

            if state == WAITING:
                last_x = 0
                cv2.accumulateWeighted(gray, base_image, 0.25)

            state = WAITING
            key = cv2.waitKey(1) & 0xFF

            # if the `q` key is pressed, break from the loop and terminate processing
            if key == ord("q"):
                log_entry("out", sessionID)
                break
            loop_count = 0

        # clear the stream in preparation for the next frame
        rawCapture.truncate(0)
        loop_count = loop_count + 1

        if commit_counter >= FPS * 60:
            print("Adding vehicles to database.")
            commit_counter = 0
            session.commit()
            session.execute(clean)
        else:
            commit_counter += 1


except KeyboardInterrupt:  # Catch a CTRL+C interrupt as program exit
    now = datetime.datetime.now()
    print("Writing exit time ({}) to log table and exiting program.".format(now))
    log_entry("out", sessionID)

# cleanup the camera and close any open windows
cv2.destroyAllWindows()
