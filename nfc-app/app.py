from flask import Flask, render_template, request, jsonify
import nfc
import ndef
import time
import threading

app = Flask(__name__)

# Configuration
BASE_URL = "http://10.207.24.120/test"
SERIAL_PREFIX = "A451"  # Default prefix
current_number = 0

nfc_thread = None
nfc_reader = None

def generate_serial_number():
    global current_number
    current_number += 1
    return f"{SERIAL_PREFIX}{current_number:06d}"  # Pad with zeros to 6 digits

def on_connect(tag):
    print("Tag Detected:")
    print(tag)

    if tag.ndef:
        try:
            # Generate new serial number
            serial = generate_serial_number()
            url = f"{BASE_URL}?serialnumber={serial}"
            
            # Create NDEF message with both URL and serial number
            tag.ndef.records = [
                ndef.UriRecord(url),
                ndef.TextRecord(f"Serial: {serial}")
            ]
            print(f"Writing to tag - Serial: {serial}, URL: {url}")
            return True
        except Exception as e:
            print("Failed to write to tag:", e)
            return False
    else:
        print("Tag is not NDEF formatted or not writable.")
        return False

def nfc_reader_thread():
    global nfc_reader
    try:
        print("Looking for NFC reader...")
        nfc_reader = nfc.ContactlessFrontend('usb')
        if not nfc_reader:
            print("No NFC reader found.")
            return

        print("NFC reader connected. Ready to scan and write tags.")

        while True:
            try:
                nfc_reader.connect(rdwr={'on-connect': on_connect})
                print("Tag removed. Waiting for next tag...\n")
                time.sleep(0.5)
            except Exception as e:
                print("Error during tag scan:", e)
                break

    except Exception as e:
        print("Error:", e)
    finally:
        if nfc_reader is not None:
            print("Closing NFC reader...")
            nfc_reader.close()
            print("NFC reader closed.")

@app.route('/')
def index():
    return render_template('index.html', 
                         current_number=current_number,
                         serial_prefix=SERIAL_PREFIX,
                         base_url=BASE_URL)

@app.route('/get-current-serial', methods=['GET'])
def get_current_serial():
    return jsonify({
        "serial": f"{SERIAL_PREFIX}{current_number:06d}",
        "number": current_number
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