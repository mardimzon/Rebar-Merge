from flask import Flask, render_template, Response, request, url_for, jsonify, send_from_directory, redirect, send_file
import cv2
import threading
import RPi.GPIO as GPIO
import time
import os
import datetime
import glob
import zipfile
import io

# Screen dimensions for the Pi 5 LCD
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480

# Ultrasonic sensor pins
TRIG = 23
ECHO = 24

# Directory to save captured images
CAPTURE_DIR = "captured_images"
os.makedirs(CAPTURE_DIR, exist_ok=True)

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

# Flask app setup
app = Flask(__name__, static_folder='static')

# Camera setup
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, SCREEN_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SCREEN_HEIGHT)

# Create variables to store the latest frame and distance
latest_frame = None
frame_lock = threading.Lock()
latest_distance = 0
distance_lock = threading.Lock()
running = True  # Flag to control the main loop

# Function to measure distance using ultrasonic sensor
def measure_distance():
    # Send a 10us pulse to trigger
    GPIO.output(TRIG, False)
    time.sleep(0.01)  # Reduced from 0.5 to make it more responsive
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)
    
    pulse_start = time.time()
    pulse_end = time.time()
    
    # Wait for echo to start (timeout after 1 second)
    timeout_start = time.time()
    while GPIO.input(ECHO) == 0:
        pulse_start = time.time()
        if time.time() - timeout_start > 1:
            return -1  # Timeout error
    
    # Wait for echo to end (timeout after 1 second)
    timeout_start = time.time()
    while GPIO.input(ECHO) == 1:
        pulse_end = time.time()
        if time.time() - timeout_start > 1:
            return -1  # Timeout error
    
    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150  # speed of sound / 2
    return round(distance, 2)

# Function to continuously update distance
def distance_monitor():
    global latest_distance, running
    
    while running:
        dist = measure_distance()
        if dist > 0:  # Only update if valid reading
            with distance_lock:
                latest_distance = dist
        time.sleep(0.1)  # Read distance 10 times per second

# Function to continuously capture frames
def capture_frames():
    global latest_frame, running
    
    # Borderless fullscreen window
    cv2.namedWindow("USB Camera", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("USB Camera", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    while running:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Resize frame to exactly 800x480
        frame = cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT), interpolation=cv2.INTER_LINEAR)
        
        # Display on the Pi's LCD (without distance text overlay)
        cv2.imshow("USB Camera", frame)
        
        # Store the latest frame for the web stream
        with frame_lock:
            latest_frame = frame.copy()
            
        # Process window events and check for ESC key (27)
        key = cv2.waitKey(1)
        if key == 27:  # ESC key
            running = False
            break

    # Clean up resources when loop exits
    cap.release()
    cv2.destroyAllWindows()

# Function to generate frames for the web stream
def generate_frames():
    global latest_frame, running
    
    while running:
        # Wait until we have a frame
        if latest_frame is None:
            time.sleep(0.1)
            continue
            
        # Get the latest frame with thread safety
        with frame_lock:
            if latest_frame is not None:
                frame = latest_frame.copy()
            else:
                time.sleep(0.1)
                continue
        
        # Encode the frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        
        # Yield the frame in the format expected by Flask
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# Function to save the current frame as an image
@app.route('/capture')
def capture_image():
    global latest_frame
    
    try:
        # Get the current timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get the current distance reading
        with distance_lock:
            dist = latest_distance
        
        # Get the latest frame with thread safety
        with frame_lock:
            if latest_frame is not None:
                frame = latest_frame.copy()
            else:
                return jsonify({"success": False, "message": "No frame available"})
        
        # Add distance text to the captured image
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, f"Distance: {dist} cm", (10, 30), font, 1, (0, 255, 0), 2, cv2.LINE_AA)
        
        # Save the image
        filename = f"capture_{timestamp}_{dist}cm.jpg"
        filepath = os.path.join(CAPTURE_DIR, filename)
        cv2.imwrite(filepath, frame)
        
        # Create download URL
        download_url = url_for('download_image', filename=filename)
        
        return jsonify({
            "success": True, 
            "message": f"Image saved as {filename}",
            "filepath": filepath,
            "download_url": download_url
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

# Route for video feed
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

# Function for distance data JSON endpoint
@app.route('/distance')
def get_distance():
    global latest_distance
    with distance_lock:
        dist = latest_distance
    return {"distance": dist}

# Route to serve captured images
@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(CAPTURE_DIR, filename)

# Route to download a specific image
@app.route('/download/<path:filename>')
def download_image(filename):
    return send_from_directory(CAPTURE_DIR, filename, as_attachment=True)

# Route to get a list of all captured images
@app.route('/image_list')
def image_list():
    images = []
    for file in sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")), reverse=True):
        filename = os.path.basename(file)
        images.append({
            "filename": filename,
            "url": url_for('serve_image', filename=filename),
            "download_url": url_for('download_image', filename=filename),
            "timestamp": os.path.getmtime(file)
        })
    return jsonify({"images": images})

# Route to download all images as a zip
@app.route('/download_all')
def download_all_images():
    # Create in-memory file for the ZIP
    memory_file = io.BytesIO()
    
    # Create ZIP file
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for file in glob.glob(os.path.join(CAPTURE_DIR, "*.jpg")):
            filename = os.path.basename(file)
            zf.write(file, filename)
    
    # Reset file pointer to start
    memory_file.seek(0)
    
    # Create a timestamp for the zip filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Return the zipped files as an attachment
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'captured_images_{timestamp}.zip'
    )

# Welcome page route
@app.route('/')
def welcome():
    return render_template('welcome.html')

# Main application route
@app.route('/app')
def main_app():
    return render_template('app.html')

# Route to handle shutdown
@app.route('/shutdown')
def shutdown():
    global running
    running = False
    func = request.environ.get('werkzeug.server.shutdown')
    if func is not None:
        func()
    return "Server shutting down..."

# Function to clean up resources when app exits
def cleanup():
    global running, cap
    running = False
    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    GPIO.cleanup()

if __name__ == '__main__':
    try:
        # Start the distance monitoring thread
        distance_thread = threading.Thread(target=distance_monitor)
        distance_thread.daemon = True
        distance_thread.start()
        
        # Start the frame capture thread
        capture_thread = threading.Thread(target=capture_frames)
        capture_thread.daemon = True
        capture_thread.start()
        
        # Run the Flask app
        app.run(host='0.0.0.0', port=5000, use_reloader=False)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Ensure cleanup happens when the app exits
        cleanup()
