import sys
import os

# Ensure the root directory is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api import app

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()
