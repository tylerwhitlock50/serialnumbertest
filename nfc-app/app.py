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

def generate_serial_number():
    global current_number
    current_number += 1
    return f"{SERIAL_PREFIX}{current_number:06d}"  # Pad with zeros to 6 digits

def create_product_data(serial, work_order=None, batch=None):
    """Build the JSON payload for this product."""
    return {
        "serial_number": serial,
        "manufacture_date": datetime.now().strftime("%Y-%m-%d"),
        "work_order": work_order or f"WO-{datetime.now().strftime('%Y%m%d')}",
        "batch": batch or f"B{datetime.now().strftime('%Y%m%d')}",
        "scan_timestamp": datetime.now().isoformat(),
        "product_type": "Paddle",
        "version": "1.0"
    }

def on_connect(tag):
    """Called once per tap; return True to end this connect() call."""
    print("Tag Detected:", tag)
    if not tag.ndef:
        print("→ Not NDEF or not writable.")
        return False

    try:
        serial = generate_serial_number()
        data = create_product_data(serial)
        url = (
            f"{BASE_URL}"
            f"?serial={serial}"
            f"&wo={data['work_order']}"
            f"&batch={data['batch']}"
        )

        tag.ndef.records = [
            ndef.UriRecord(url),
            ndef.TextRecord(f"Serial: {serial}"),
            ndef.TextRecord(json.dumps(data))
        ]

        print(f"✓ Written Serial: {serial}")
        print("  Payload:\n", json.dumps(data, indent=2))
        return True
    except Exception as e:
        print("✗ Write failed:", e)
        return False

def nfc_reader_thread():
    """Continuously open/close the reader; write one tag per session."""
    while True:
        try:
            print("Looking for NFC reader…")
            with nfc.ContactlessFrontend('usb') as clf:
                print("Reader connected! Tap a tag to write.")
                while True:
                    try:
                        clf.connect(
                            rdwr={
                                'on-connect': on_connect,
                                'beep-on-connect': True,
                                'terminate-after': 1  # Add timeout to prevent hanging
                            }
                        )
                        print("Tag done—remove it to scan the next one.")
                        time.sleep(0.5)  # Small delay between reads
                    except nfc.clf.CommunicationError:
                        print("Tag removed or communication error")
                        continue
        except nfc.clf.NoSuchDeviceError:
            print("No reader found; retrying in 1s…")
            time.sleep(1)
        except Exception as e:
            print("Unexpected NFC error:", e)
            time.sleep(1)

@app.route('/')
def index():
    return render_template(
        'index.html',
        current_number=current_number,
        serial_prefix=SERIAL_PREFIX,
        base_url=BASE_URL
    )

@app.route('/get-current-serial', methods=['GET'])
def get_current_serial():
    serial = f"{SERIAL_PREFIX}{current_number:06d}"  # Keep consistent with 6 digits
    data = create_product_data(serial)
    return jsonify({
        "serial": serial,
        "number": current_number,
        "product_data": data
    })

@app.route('/update-prefix', methods=['POST'])
def update_prefix():
    global SERIAL_PREFIX, current_number
    payload = request.get_json()
    SERIAL_PREFIX = payload.get('prefix', SERIAL_PREFIX)
    current_number = int(payload.get('number', current_number))  # Ensure number is an integer
    return jsonify({
        "status": "success",
        "prefix": SERIAL_PREFIX,
        "number": current_number
    })

if __name__ == '__main__':
    # Fire up the NFC thread
    threading.Thread(target=nfc_reader_thread, daemon=True).start()
    print("\nApp running at http://0.0.0.0:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
