import inspect
import os

print(inspect.currentframe())
print(inspect.getfile(inspect.currentframe()))
print(os.path.split(inspect.getfile(inspect.currentframe()))[0])
print(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
print(os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0])))