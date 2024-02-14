import os, sys

# Function to get the path of the resource
def getResourcePath(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, os.path.join("res", relative_path))
