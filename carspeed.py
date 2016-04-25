# import the necessary packages

# TODO: Figure out logic to detect if two vehicles are in frame
# TODO: Figure out how to use background subtraction algos
# TODO: Add feature to detect pedestrians, and use this to temporarily disable detection as it will be inaccurate.

import argparse
import datetime
import math
import os
import statistics
import time
from uuid import uuid4 as uuid

import cv2
import numpy as np
from picamera import PiCamera
from picamera.array import PiRGBArray
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db import Vehicles, Log

parser = argparse.ArgumentParser()
parser.add_argument("-x", "--x", help="Use X-server.", action="store_true")

args = parser.parse_args()

if args.x:
    use_x = True
    show_bounds = True
    showImage = True
else:
    use_x = False
    show_bounds = False
    showImage = False

engine = create_engine('postgresql://speedcam:Rward0232@localhost/speedcamdb')
DBSession = sessionmaker(bind=engine)
session = DBSession()

# define some constants
save_photos = True
dropbox_upload = True
RTL_Distance = 85  # Right to left distance to median
LTR_Distance = 60  # Left to right distance to median
THRESHOLD = 15
SPEED_THRESHOLD = 35
MINIMUM_SPEED = 20  # # Don't detect cars in parking lots, walkers, and slow drivers
MAXIMUM_SPEED = 60  # 70  # Anything higher than this is likely to be noise.
MIN_AREA = 1500
blur_size = (15, 15)
image_width = 640
image_height = 480
image_resolution = [image_width, image_height]
field_of_view = 53.5
FPS = None
day_fps = 30
night_fps = 15
set_by_drawing = True  # Can either set bounding box manually, or by drawing rectangle on screen
rotation_degrees = 187  # Rotate image by this amount to create flat road
timeOn = datetime.datetime.now()  # This is used for the log
sessionID = uuid()
current_id = None
initial_time = None
last_mph = None
# the following enumerated values are used to make the program more readable
WAITING = 0
TRACKING = 1
SAVING = 2
STUCK = 3
NEW_BASE_IMG_NEEDED = 4
UNKNOWN = 0
LEFT_TO_RIGHT = 1
RIGHT_TO_LEFT = 2

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

# -- other values used in program
base_image = None
abs_chg = 0
mph = 0
secs = 0.0
ix, iy = -1, -1
fx, fy = -1, -1
drawing = False
setup_complete = False
tracking = False
text_on_image = 'No cars'
loop_count = 0
prompt = ''
last_vehicle_detected = 'N/A'
last_mph_detected = 'N/A'
last_db_commit = 'N/A'
display_counter = 0
motion_found = False
mph_list = []
id = None
motion_loop_count = 0
commit_counter = 0
nighttime = False
camera = None
rgb = None
time_base_image = None
time_last_detection = None

# Remove duplicate entries from table
clean = text("DELETE FROM vehicles\
  WHERE id IN (SELECT id\
  FROM (SELECT id,\
  ROW_NUMBER() OVER (partition BY speed ORDER BY id) AS rnum\
  FROM vehicles) t\
  WHERE t.rnum > 1);")


def is_nighttime():
    """
    Determines if hour falls within range of nighttime hours.
    :return:
    """

    now = datetime.datetime.now().time()

    if now >= datetime.time(20, 00) or now <= datetime.time(7, 00):
        return True

    else:
        return False


def set_framerate_by_time(FPS, now, camera):
    """
    Sets framerate based on time of day, using a lower value for night.
    :return: None - passes straight to camera
    """

    now = now.time()

    if is_nighttime():
        if FPS != night_fps:
            FPS = 15
            print("Setting FPS to {0}.".format(night_fps))
            camera.framerate = FPS

    else:
        if FPS != day_fps:
            FPS = day_fps
            print("Setting FPS to {0}.".format(day_fps))
            camera.framerate = FPS

    return FPS


def log_entry(in_out, uid):
    """
    Put usage in log table
    """

    if in_out == "in":
        new_entry = Log(
            sessionID=uid,
            timeOn=timeOn
        )

        session.add(new_entry)
        session.commit()

    elif in_out == "out":
        print("Writing exit time ({}) to log table and exiting program.".format(now))
        logEntry = session.query(Log).filter_by(sessionID=str(uid)).first()
        logEntry.timeOff = datetime.datetime.now()
        session.commit()


def clear_screen():
    """
    Clears the terminal window for cleaner output.
    :return:
    """
    os.system('cls' if os.name == 'nt' else 'clear')


def prompt_on_image(txt):
    """
    Places prompt on image.
    :param txt:
    :return:
    """
    global image
    cv2.putText(image, txt, (10, 35),
    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)


def get_speed(pixels, feet_per_pixel, secs):
    """
    Calculates the speed of a vehicle using pixels, and time.
    :param pixels:
    :param feet_per_pixel:
    :param secs:
    :return:
    """
    if secs > 0.0:
        return ((pixels * feet_per_pixel) / secs) * 0.681818
    else:
        return 0.0


def secs_diff(endTime, begTime):
    """
    Calculates how many seconds have elapsed.
    :param endTime:
    :param begTime:
    :return:
    """
    diff = (endTime - begTime).total_seconds()
    return diff


def draw_rectangle(event, x, y):
    """
    Allows user to draw rectangle on screen to select bounding area.
    :param event:
    :param x:
    :param y:
    :param flags:
    :param param:
    :return:
    """
    global ix, iy, fx, fy, drawing, setup_complete, image, org_image, prompt  #TODO: No global variables

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


def calculate_ftperpixel(distance, imagewidth):
    """
    Calculates the number of feet a single pixel represents.
    :param distance:
    :param imagewidth:
    :return:
    """
    frame_width_ft = 2 * (math.tan(math.radians(field_of_view * 0.5)) * distance)
    ftperpixel = frame_width_ft / float(imagewidth)

    return ftperpixel


def grab_rgb(image, c):
    """
    Determines values of pixels that fall within a contour provided by OpenCV.
    :param image: an image object
    :param c: a contour
    :return: a string value representing the most common rgb value found within a contour.
    """
    pixels = []

    # TODO: Finish fixing this function
    # Detect pixel values (RGB)
    mask = np.zeros_like(image)
    cv2.drawContours(mask, c, -1, color=255, thickness=-1)

    points = zip(*np.where(mask == 255))

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

    return pixel_string


def create_base():
    """
    Creates a base image using background subtraction.
    :return:
    """
    mask = None

    cv2.VideoCapture.set(CV_CAP_PROP_FRAME_COUNT=100)  # Capture 100 frames
    cap = cv2.VideoCapture(0)  # Open the videocapture device
    subtractor = cv2.createBackgroundSubtractorMOG2()
    ret, frames = cap.read()

    for frame in frames:
        mask = subtractor.apply(frame)

    return mask


def display(mode, ccounter, last_db_commit, last_vehicle_detected, last_mph_detected):
    """
    Prints a status display to screen
    :param mode: which info should be displayed: tracking, car added, etc.
    :return: stdout.
    """

    # TODO: Finish this function and use it.

    clear_screen()
    now = datetime.datetime.now()
    now = now.strftime('%Y-%m-%d %H:%M')

    print("=========================================================")
    print("                 Car Speed Detector")
    print("=========================================================")

    if mode == 'waiting':
        print("\nStatus:                No vehicle within bounding box")
        print("Last vehicle detected:   {0} at {1} MPH".format(last_vehicle_detected, last_mph_detected))
        print("Last database commit:    {0}".format(last_db_commit))
        print("Time:                    {0}".format(now))
        pass
    elif mode == 'tracking':
        print("Tracking vehicle.")
        pass
    elif mode == 'stuckinloop':
        print("Got caught in tracking loop. Capturing new base image.")
        pass
    elif mode == 'startup':
        pass
    else:
        print("Error in display function.")


def initialize_camera(camera, res):
    """
    Initializes this camera using current time to set framerate
    :param res: image resolution to use
    :return: None
    """

    try:  # Release the camera resources if already exist
        camera.close()
    except AttributeError:  # Camera doesn't already exist
        pass

    camera = PiCamera()
    camera.resolution = res
    set_framerate_by_time(FPS, timeOn, camera)  # Set initial frame rate.
    camera.vflip = False
    camera.hflip = False
    camera.rotate = 90

    rawCapture = PiRGBArray(camera, size=camera.resolution)
    time.sleep(0.9)  # allow the camera to warm up

    print("Camera initialized")

    return camera, rawCapture


def create_image(save_photos, speed_threshold, speed, image, rectangle, image_width, image_height):
    if save_photos and speed >= SPEED_THRESHOLD:  # Write out an image of the speeder
        _x = rectangle[0]
        _y = rectangle[1]
        _w = rectangle[2]
        _h = rectangle[3]

        rectangle = cv2.rectangle(image, (_x, _y), (_x + _w, _y + _h), (0, 255, 0), 2)

        # timestamp the image
        cv2.putText(image, datetime.datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
                    (10, image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.75, (0, 255, 0), 1)

        # write the speed: first get the size of the text
        size, base = cv2.getTextSize("%.0f mph" % speed, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)

        # then center it horizontally on the image
        cntr_x = int((w - size[0]) / 2)
        cv2.putText(image, "%.0f mph" % speed,
                    (cntr_x, int(h * 0.2)), cv2.FONT_HERSHEY_SIMPLEX,
                    1.00, (0, 255, 0), 2)

        # and save the image to disk
        path = None
        filename = "images/car_at_" + datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S") + ".jpg"
        cv2.imwrite(filename, image)

        if dropbox_upload:
            dropbox_path = 'carspeed.py/{0}'.format(filename)
            os.system('./dropbox_uploader.sh upload {0} {1}'.format(filename, dropbox_path))


camera, rawCapture = initialize_camera(camera, image_resolution)

# Set up the bounding box for speed detection
# create an image window and place it in the upper left corner of the screen
if use_x:
    cv2.namedWindow("Speed Camera", cv2.WINDOW_AUTOSIZE)
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
    # Define bounding box
    upper_left_x = 138
    upper_left_y = 100
    lower_right_x = 462
    lower_right_y = 193  # 183

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

fps_is_set = True
need_to_reset = False
rectangle = []
log_entry("in", sessionID)  # Log usage

while fps_is_set:  # Run loop while FPS is set. Should restart when nighttime threshold is crossed.
    if need_to_reset:
        camera, rawCapture = initialize_camera(camera, image_resolution)  # Fire up camera!
        need_to_reset = False

    try:
        fps_is_set = False
        for frame in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):

            if commit_counter % 10 == 0:
                #    display_counter = commit_counter
                pass

            # initialize the timestamp
            timestamp = datetime.datetime.now()

            # grab the raw NumPy array representing the image, and rotate it so that it's flat
            image = frame.array
            rows, cols, placeholder = image.shape
            M = cv2.getRotationMatrix2D((cols / 2, rows / 2), rotation_degrees, 1)
            image = cv2.warpAffine(image, M, (rows, cols))

            # crop the frame to the monitored area, convert it to grayscale, and blur it
            # crop area defined by [y1:y2,x1:x2]
            gray = image[upper_left_y:lower_right_y, upper_left_x:lower_right_x]
            image_orig = gray

            # convert it to grayscale, and blur it
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

            # Use median filter at night to get rid of graininess
            gray = cv2.medianBlur(gray, 15)  # TODO: Test this
            # gray = cv2.GaussianBlur(gray, blur_size, 0)

            if base_image is None or state == STUCK or state == NEW_BASE_IMG_NEEDED:
                if state == STUCK:
                    print("Caught motion loop. Creating new base snapshot")
                    motion_loop_count = 0
                    state = UNKNOWN

                elif state == NEW_BASE_IMG_NEEDED:
                    print("Creating new base image")
                    motion_loop_count = 0
                    state = UNKNOWN

                base_image = gray.copy().astype("float")
                lastTime = timestamp
                rawCapture.truncate(0)
                time_base_image = datetime.datetime.now()

                if use_x:
                    cv2.imshow("Speed Camera", image)
                continue

            # compute the absolute difference between the current image and
            # base image and then turn everything lighter than THRESHOLD into
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

            if len(cnts) > 0:
                areas = [cv2.contourArea(c) for c in cnts]  # Get contour areas
                max_index = np.argmax(areas)  # Find maximum value in list of areas
                cnt = cnts[max_index]  # return contour with maximum area

                x, y, w, h = cv2.boundingRect(
                    cnt)  # Get x,y, width and height of bounding rectangle of maximum area contour.

                rectangle = [x, y, w, h]

                found_area = w * h

            # examine the contours, looking for the largest one
            # for c in cnts:
            #    (x, y, w, h) = cv2.boundingRect(c)
            #    # get an approximate area of the contour
            #    found_area = w * h
            #    # find the largest bounding rectangle

                if (found_area > MIN_AREA) and state != STUCK:
                    motion_found = True

                    if not is_nighttime():
                        rgb = grab_rgb(image, cnt)
                    else:
                        rgb = 'nighttime'

            if motion_found:
                committed = False
                if state == WAITING:
                    # intialize tracking
                    state = TRACKING
                    initial_x = x
                    last_x = x
                    initial_time = timestamp
                    last_mph = 0
                    motion_loop_count = 0

                else:

                    if state == TRACKING:
                        if x >= last_x:
                            direction = LEFT_TO_RIGHT
                            ftperpixel = calculate_ftperpixel(LTR_Distance, image_width)
                            abs_chg = x + w - initial_x
                            dir = "North"

                        else:
                            direction = RIGHT_TO_LEFT
                            dir = "South"
                            abs_chg = initial_x - x
                            ftperpixel = calculate_ftperpixel(RTL_Distance, image_width)

                        secs = secs_diff(timestamp, initial_time)
                        mph = get_speed(abs_chg, ftperpixel, secs)

                        if MINIMUM_SPEED <= mph < MAXIMUM_SPEED:
                            text_on_image = 'Tracking'
                            print(text_on_image)
                            mph_list.append(mph)

                        if len(mph_list) >= 3 and motion_loop_count > 1:
                            if ((x <= 2) and (direction == RIGHT_TO_LEFT)) and not committed \
                                    or ((x + w >= monitored_width - 2) and (
                                                direction == LEFT_TO_RIGHT)) and not committed:
                                state = SAVING
                                timestamp = datetime.datetime.now()
                                speed = statistics.median(mph_list)
                                new_vehicle = Vehicles(  # Table for statistics calculations
                                    sessionID=sessionID,
                                    datetime=timestamp,
                                    speed=speed,
                                    direction=dir,
                                    color=rgb,
                                    rating=motion_loop_count
                                )

                                session.add(new_vehicle)
                                commit_counter += 1
                                id = None
                                committed = True
                                clear_screen()
                                print("Added new vehicle: {0} MPH".format(round(speed, 2)))
                                last_vehicle_detected = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                                time_last_detection = timestamp
                                last_mph_detected = round(speed, 2)
                                mph_list = []

                                create_image(save_photos, SPEED_THRESHOLD, speed, image_orig, rectangle, image_width,
                                             image_height)

                        last_x = x
                        last_mph = mph

                motion_loop_count += 1

            else:
                if state != WAITING and state != STUCK:
                    state = WAITING
                    direction = UNKNOWN
                    text_on_image = 'No Car Detected'
                    print(text_on_image)
                    mph_list = []
                    id = None
                    motion_loop_count = 0

            if state == WAITING and loop_count % 10 == 0:
                display('waiting', display_counter, last_db_commit, last_vehicle_detected, last_mph_detected)
            elif state == TRACKING:
                pass

            if motion_loop_count >= 50:
                state = STUCK

            # if time_base_image - timestamp > 3600 and time_last_detection - timestamp > 120:
            #    state = NEW_BASE_IMG_NEEDED
            #    print("Creating new base image")

            # only update image and wait for a keypress when waiting for a car
            # or if 50 frames have been processed in the WAITING state.
            # This is required since waitkey slows processing.
            if (state == WAITING) or (loop_count > 50):

                if use_x:
                    # draw the text and timestamp on the frame
                    cv2.putText(image, datetime.datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
                                (10, image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 1)
                    cv2.putText(image, "Road Status: {}".format(text_on_image), (10, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

                    # define the monitored area right and left boundary
                    cv2.line(image, (upper_left_x, upper_left_y), (upper_left_x, lower_right_y), (0, 255, 0))
                    cv2.line(image, (lower_right_x, upper_left_y), (lower_right_x, lower_right_y), (0, 255, 0))

                    prompt_on_image(prompt)
                    cv2.imshow("Speed Camera", image)

                if state == WAITING:
                    last_x = 0
                    if is_nighttime():
                        base_image = cv2.accumulateWeighted(gray, base_image, 0.01)  # original is 0.25
                    else:
                        base_image = cv2.accumulateWeighted(gray, base_image, 0.01)  # original is 0.25

                state = WAITING
                key = cv2.waitKey(1) & 0xFF

                # if the `q` key is pressed, break from the loop and terminate processing
                if key == ord("q"):
                    log_entry("out", sessionID)
                    break
                loop_count = 0

            # clear the stream in preparation for the next frame
            rawCapture.truncate(0)
            loop_count += 1

            if commit_counter >= 5:
                clear_screen()
                print("***Adding vehicles to database.***")
                commit_counter = 0
                session.commit()
                session.execute(clean)
                last_db_commit = timestamp.strftime('%Y-%m-%d %H:%M:%S')

            if not nighttime and is_nighttime():  # reset loop so camera FPS can be changed.
                nighttime = True
                fps_is_set = True
                need_to_reset = True
                session.commit()
                break

    except KeyboardInterrupt:  # Catch a CTRL+C interrupt as program exit and close gracefully
        now = datetime.datetime.now()
        log_entry("out", sessionID)
        session.commit()
        camera.close()

# cleanup the camera and close any open windows
cv2.destroyAllWindows()
