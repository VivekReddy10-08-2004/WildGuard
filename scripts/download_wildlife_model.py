"""Download the North American wildlife model into project-local storage."""

from model_services.image.wildlife_detector import download_weights

if __name__ == "__main__":
    print(download_weights())

