import sys
import traceback
import tellopy
import av
import cv2.cv2 as cv2  # for avoidance of pylint error
import numpy
import time
import datetime

from swarm_manager import TelloDrone, SwarmManager
from typing import List

ROUTER_SSID_PASSWORD = "U+Net2AE6", "1C4C024328"

def main():
    manager = SwarmManager(*ROUTER_SSID_PASSWORD)
    manager.find_drones_on_network(1)
    drones: List[TelloDrone] = manager.get_connected_drones()
    drone = drones[0]

    try:
        n=0
        retry = 3
        container = None
        while container is None and 0 < retry:
            retry -= 1
            try:
                container = av.open(drone.get_video_stream())
            except av.AVError as ave:
                print(ave)
                print('retry...')

        # skip first 300 frames
        frame_skip = 300
        while True:
            for frame in container.decode(video=0):
                if 0 < frame_skip:
                    frame_skip = frame_skip - 1
                    continue
                start_time = time.time()
                image = cv2.cvtColor(numpy.array(frame.to_image()), cv2.COLOR_RGB2BGR)
                cv2.imshow('Original', image)

      #  resize = cv2.resize(frame, (new_w, new_h)) # <- resize for improved performance
        # Display the resulting frame
       
                if cv2.waitKey(1) & 0xFF == ord('s'):
                    cv2.imwrite(now.strftime("%S.jpg"),image) # writes image test.bmp to disk
                    print("Take Picture")
                    n=n+1
       
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except Exception as ex:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        print(ex)
    finally:
        drone.quit()
        cv2.destroyAllWindows()

if __name__=='__main__':
    main()
