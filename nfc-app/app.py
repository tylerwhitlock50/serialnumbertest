from flask import Flask, render_template, request, jsonify
import nfc
import ndef
import time
import threading
import json
from datetime import datetime

app = Flask(__name__)

# Configuration
BASE_URL = "http://10.207.24.120/product"
SERIAL_PREFIX = "A451"  # Default prefix
current_number = 0

nfc_thread = None
nfc_reader = None
is_reading = False

def generate_serial_number():
    global current_number
    current_number += 1
    return f"{SERIAL_PREFIX}{current_number:06d}"  # Pad with zeros to 6 digits

def create_product_data(serial, work_order=None, batch=None):
    """Create a product data structure with all relevant information"""
    return {
        "serial_number": serial,
        "manufacture_date": datetime.now().strftime("%Y-%m-%d"),
        "work_order": work_order or f"WO-{datetime.now().strftime('%Y%m%d')}",
        "batch": batch or f"B{datetime.now().strftime('%Y%m%d')}",
        "scan_timestamp": datetime.now().isoformat(),
        "product_type": "Paddle",  # This could be configurable
        "version": "1.0"  # This could be configurable
    }

def on_connect(tag):
    global is_reading
    if is_reading:
        return False
    
    is_reading = True
    print("Tag Detected:")
    print(tag)

    try:
        if tag.ndef:
            # Generate new serial number
            serial = generate_serial_number()
            
            # Create product data
            product_data = create_product_data(serial)
            
            # Create the URL with query parameters
            url = f"{BASE_URL}?serial={serial}&wo={product_data['work_order']}&batch={product_data['batch']}"
            
            # Create NDEF message with URL, serial number, and JSON data
            tag.ndef.records = [
                ndef.UriRecord(url),
                ndef.TextRecord(f"Serial: {serial}"),
                ndef.TextRecord(json.dumps(product_data))  # Store full product data as JSON
            ]
            
            print(f"Writing to tag - Serial: {serial}")
            print(f"Product Data: {json.dumps(product_data, indent=2)}")
            return True
        else:
            print("Tag is not NDEF formatted or not writable.")
            return False
    except Exception as e:
        print("Failed to write to tag:", e)
        return False
    finally:
        is_reading = False

def nfc_reader_thread():
    global nfc_reader, is_reading
    while True:
        try:
            if nfc_reader is None:
                print("Looking for NFC reader...")
                nfc_reader = nfc.ContactlessFrontend('usb')
                if not nfc_reader:
                    print("No NFC reader found.")
                    time.sleep(5)  # Wait before retrying
                    continue

                print("NFC reader connected. Ready to scan and write tags.")

            # Set up connection parameters
            rdwr_options = {
                'on-connect': on_connect,
                'beep-on-connect': True,
                'terminate-after': 1  # Terminate after 1 second of no activity
            }

            # Connect to reader
            nfc_reader.connect(rdwr=rdwr_options)
            
            # Small delay to prevent CPU overuse
            time.sleep(0.1)

        except nfc.clf.NoSuchDeviceError:
            print("NFC reader disconnected. Attempting to reconnect...")
            if nfc_reader:
                nfc_reader.close()
            nfc_reader = None
            time.sleep(1)
        except Exception as e:
            print("Error during NFC operation:", e)
            if nfc_reader:
                nfc_reader.close()
            nfc_reader = None
            time.sleep(1)

@app.route('/')
def index():
    return render_template('index.html', 
                         current_number=current_number,
                         serial_prefix=SERIAL_PREFIX,
                         base_url=BASE_URL)

@app.route('/get-current-serial', methods=['GET'])
def get_current_serial():
    serial = f"{SERIAL_PREFIX}{current_number:06d}"
    product_data = create_product_data(serial)
    return jsonify({
        "serial": serial,
        "number": current_number,
        "product_data": product_data
    })

@app.route('/update-prefix', methods=['POST'])
def update_prefix():
    global SERIAL_PREFIX, current_number
    data = request.get_json()
    new_prefix = data.get('prefix', SERIAL_PREFIX)
    new_number = data.get('number', 0)
    
    SERIAL_PREFIX = new_prefix
    current_number = new_number
    
    return jsonify({
        "status": "success",
        "prefix": SERIAL_PREFIX,
        "number": current_number
    })

if __name__ == '__main__':
    # Start NFC reader thread
    nfc_thread = threading.Thread(target=nfc_reader_thread, daemon=True)
    nfc_thread.start()
    
    print("\nYour app is available at: http://0.0.0.0:5000")
    print("Open this URL in your browser to monitor NFC writes.")
    app.run(debug=True, host='0.0.0.0', port=5000) 