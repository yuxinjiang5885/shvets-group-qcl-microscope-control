'''
timer_test
Test the timer function for use in the mircat code
'''

from time import sleep
# from timeit import default_timer as timer
from time import perf_counter as timer

LIMIT = 200
SLEEP_INTERVAL = 0.1 # s

start = timer()
for x in range(0, LIMIT):
    print('Time: {:.3f} s'.format(timer()-start), end='\r') # overwriting
    sleep(SLEEP_INTERVAL)
print() # clear line