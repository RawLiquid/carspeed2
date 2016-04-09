# import the necessary packages
from picamera.array import PiRGBArray
from picamera import PiCamera
import time
import math
import datetime
import cv2
from statistics import median
from uuid import uuid4 as uuid
import os

from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker
from db import Speeders, Vehicles


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
        
# define somec constants
DISTANCE = 70  #<---- enter your distance-to-road value here
THRESHOLD = 15
SPEED_THRESHOLD = 40
MINIMUM_SPEED = 20  # Don't detect cars in parking lots, walkers, and slow drivers
MAXIMUM_SPEED = 70  # Anything higher than this is likely to be noise.
MIN_AREA = 225 #175  # TODO: Experiment with this - it may reduce the sensitivity
BLURSIZE = (15,15)
IMAGEWIDTH = 640
IMAGEHEIGHT = 480
RESOLUTION = [IMAGEWIDTH,IMAGEHEIGHT]
FOV = 53.5
FPS = 90

# the following enumerated values are used to make the program more readable
WAITING = 0
TRACKING = 1
SAVING = 2
UNKNOWN = 0
LEFT_TO_RIGHT = 1
RIGHT_TO_LEFT = 2

# calculate the the width of the image at the distance specified
frame_width_ft = 2*(math.tan(math.radians(FOV*0.5))*DISTANCE)
ftperpixel = frame_width_ft / float(IMAGEWIDTH)
print("Image width in feet {} at {} from camera".format("%.0f" % frame_width_ft,"%.0f" % DISTANCE))

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
show_bounds = True
showImage = True
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

rawCapture = PiRGBArray(camera, size=camera.resolution)
# allow the camera to warm up
time.sleep(0.9)

# create an image window and place it in the upper left corner of the screen
cv2.namedWindow("Speed Camera")
cv2.moveWindow("Speed Camera", 10, 40)

# call the draw_rectangle routines when the mouse is used
cv2.setMouseCallback('Speed Camera',draw_rectangle)
 
# grab a reference image to use for drawing the monitored area's boundry
camera.capture(rawCapture, format="bgr", use_video_port=True)
image = rawCapture.array
rawCapture.truncate(0)
org_image = image.copy()

prompt = "Define the monitored area - press 'c' to continue" 
prompt_on_image(prompt)
 
# wait while the user draws the monitored area's boundry
while not setup_complete:
    cv2.imshow("Speed Camera",image)
 
    #wait for for c to be pressed  
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
     
monitored_width = lower_right_x - upper_left_x
monitored_height = lower_right_y - upper_left_y
 
print("Monitored area:")
print(" upper_left_x {}".format(upper_left_x))
print(" upper_left_y {}".format(upper_left_y))
print(" lower_right_x {}".format(lower_right_x))
print(" lower_right_y {}".format(lower_right_y))
print(" monitored_width {}".format(monitored_width))
print(" monitored_height {}".format(monitored_height))
print(" monitored_area {}".format(monitored_width * monitored_height))
 
# capture frames from the camera (using capture_continuous.
#   This keeps the picamera in capture mode - it doesn't need
#   to prep for each frame's capture.
#   First, open up the PostgreSQL database.

engine = create_engine('postgresql://speedcam:Rward0232@localhost/speedcamdb')
DBSession = sessionmaker(bind=engine)
session = DBSession()


def create_base_image():
    """
    Creeate new base image for comparison.
    """

    base_image = image[upper_left_y:lower_right_y,upper_left_x:lower_right_x]
    base_image = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
    base_image = cv2.GaussianBlur(base_image, BLURSIZE, 0)
    rawCapture.truncate(0)
    cv2.imshow("Speed Camera", image)


mph_list = []
id = None
motion_loop_count = 0

for frame in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
    #initialize the timestamp
    timestamp = datetime.datetime.now()
 
    # grab the raw NumPy array representing the image 
    image = frame.array
 
    # crop the frame to the monitored area, convert it to grayscale, and blur it
    # crop area defined by [y1:y2,x1:x2]
    gray = image[upper_left_y:lower_right_y,upper_left_x:lower_right_x]
 
    # convert it to grayscale, and blur it
    gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, BLURSIZE, 0)
 
    # if the base image has not been defined, initialize it
    #if base_image is None:
    #    base_image = gray.copy().astype("float")
    #    lastTime = timestamp
    #    rawCapture.truncate(0)
    #    cv2.imshow("Speed Camera", image)
    #    continue

    if base_image is None:
        create_base_image()
 
    # compute the absolute difference between the current image and
    # base image and then turn eveything lighter than THRESHOLD into
    # white
    frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(base_image))
    thresh = cv2.threshold(frameDelta, THRESHOLD, 255, cv2.THRESH_BINARY)[1]
  
    # dilate the thresholded image to fill in any holes, then find contours
    # on thresholded image
    thresh = cv2.dilate(thresh, None, iterations=2)
    (_, cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)

    # look for motion 
    motion_found = False
    biggest_area = 0
 
    # examine the contours, looking for the largest one
    for c in cnts:
        (x, y, w, h) = cv2.boundingRect(c)
        # get an approximate area of the contour
        found_area = w*h
        # find the largest bounding rectangle
        if (found_area > MIN_AREA) and (found_area > biggest_area):  
            biggest_area = found_area
            motion_found = True

    if motion_found and motion_loop_count < 10:
        if state == WAITING:
            id = uuid()  # give same ID to all detections. This will help find errors
            clear_screen()
            # intialize tracking
            state = TRACKING
            initial_x = x
            last_x = x
            initial_time = timestamp
            last_mph = 0
            text_on_image = 'Tracking'
            print(text_on_image)
        else:

            if state == TRACKING:
                clear_screen()
                if x >= last_x:
                    direction = LEFT_TO_RIGHT
                    abs_chg = x + w - initial_x
                else:
                    direction = RIGHT_TO_LEFT
                    abs_chg = initial_x - x
                secs = secs_diff(timestamp,initial_time)
                mph = get_speed(abs_chg,ftperpixel,secs)
                if mph > MINIMUM_SPEED and mph <= MAXIMUM_SPEED:  # Filter out cars in parking lot behind road and crazy-high readings
                   mph_list.append(mph)

                if len(mph_list) >= 3:
                    if mph > SPEED_THRESHOLD and mph <= MAXIMUM_SPEED:  # Don't want all drivers, and want a reasonable
                        # number of frames captured
                        print("--> chg={}  secs={}  mph={} this_x={} w={} ".format(abs_chg,secs,"%.0f" % mph,x,w))
                        real_y = upper_left_y + y
                        real_x = upper_left_x + x
                        # is front of object outside the monitored boundary? Then write date, time and speed on image
                        # and save it
                        if ((x <= 2) and (direction == RIGHT_TO_LEFT)) and last_mph > SPEED_THRESHOLD\
                                or ((x+w >= monitored_width - 2) \
                                and (direction == LEFT_TO_RIGHT))\
                                and last_mph > SPEED_THRESHOLD:  # Prevent writing of speeds less than realistic min.
                            # timestamp the image
                            cv2.putText(image, datetime.datetime.now().strftime("%A %d %B %Y %I:%M:%S%p"),
                                (10, image.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 1)
                            # write the speed: first get the size of the text
                            size, base = cv2.getTextSize( "%.0f mph" % last_mph, cv2.FONT_HERSHEY_SIMPLEX, 2, 3)
                            # then center it horizontally on the image
                            cntr_x = int((IMAGEWIDTH - size[0]) / 2)
                            cv2.putText(image, "%.0f mph" % last_mph,
                                (cntr_x , int(IMAGEHEIGHT * 0.2)), cv2.FONT_HERSHEY_SIMPLEX, 2.00, (0, 255, 0), 3)
                            # and save the image to disk
                            cv2.imwrite("speed_tracking_images/car_at_"+datetime.datetime.now().strftime("%Y%m%d_%H%M%S")+".jpg",
                                image)
                            state = SAVING

                            if id:
                                median_speed = median(mph_list)

                                new_speeder = Speeders(
                                    uniqueID = uuid(),
                                    datetime = datetime.datetime.now(),
                                    speed = median_speed,
                                    rating = (median_speed / len(mph_list))
                                )

                                session.add(new_speeder)
                                session.commit()

                                clear_screen()
                                print("Added new speeder to database")

                        # if the object hasn't reached the end of the monitored area, just remember the speed
                        # and its last position
                        last_mph = mph

                    if ((x <= 2) and (direction == RIGHT_TO_LEFT)) and id\
                            or ((x + w >= monitored_width - 2) and (direction == LEFT_TO_RIGHT)) and id:

                        median_speed = median(mph_list)

                        new_vehicle = Vehicles(  # Table for statistics calculations
                            uniqueID = uuid(),
                            datetime = datetime.datetime.now(),
                            speed = median_speed,
                            rating = (median_speed / len(mph_list))
                        )
                        session.add(new_vehicle)
                        session.commit()
                        id = None

                        clear_screen()
                        print("Added new vehicle to database")

                else:
                    clear_screen()
                    print("Not enough frames captured ({})".format(len(mph_list)))

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
            cv2.FONT_HERSHEY_SIMPLEX,0.35, (0, 0, 255), 1)
     
        if show_bounds:
            #define the monitored area right and left boundary
            cv2.line(image,(upper_left_x,upper_left_y),(upper_left_x,lower_right_y),(0, 255, 0))
            cv2.line(image,(lower_right_x,upper_left_y),(lower_right_x,lower_right_y),(0, 255, 0))
       
        # show the frame and check for a keypress
        if showImage:
            prompt_on_image(prompt)
            cv2.imshow("Speed Camera", image)
        if state == WAITING:
            last_x = 0
            cv2.accumulateWeighted(gray, base_image, 0.25)
 
        state=WAITING;
        key = cv2.waitKey(1) & 0xFF
      
        # if the `q` key is pressed, break from the loop and terminate processing
        if key == ord("q"):
            break
        loop_count = 0
         
    # clear the stream in preparation for the next frame
    rawCapture.truncate(0)
    loop_count = loop_count + 1
  
# cleanup the camera and close any open windows
cv2.destroyAllWindows()

