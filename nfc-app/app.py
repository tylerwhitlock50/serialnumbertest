from flask import Flask, render_template, request, jsonify
import nfc
import ndef
import time
import threading
import json
from datetime import datetime
import subprocess
import logging

app = Flask(__name__)

# Configuration
BASE_URL = "http://10.207.24.120/product"
SERIAL_PREFIX = "A451"  # Default prefix
current_number = 0
WATCHDOG_TIMEOUT = 30  # seconds
last_activity_time = time.time()
reader_active = False

def reset_nfc_reader():
    """Attempt to reset the NFC reader hardware."""
    try:
        # Method 1: Try usbreset with the correct device ID
        subprocess.run(['sudo', 'usbreset', '072f:2200'], check=False)
        print("✓ NFC reader hardware reset attempted via usbreset")
        time.sleep(2)  # Give the device time to reset

        # Method 2: Try to reset via libusb if available
        try:
            import usb.core
            import usb.util
            # Find the device
            device = usb.core.find(idVendor=0x072f, idProduct=0x2200)
            if device:
                # Reset the device
                device.reset()
                print("✓ NFC reader hardware reset attempted via libusb")
                time.sleep(2)
        except ImportError:
            print("→ libusb not available, skipping libusb reset method")
        except Exception as e:
            print(f"→ libusb reset failed: {str(e)}")

        # Method 3: Try to reset via udev if available
        try:
            subprocess.run(['sudo', 'udevadm', 'trigger', '--action=remove', '--subsystem-match=usb', '--attr-match=idVendor=072f', '--attr-match=idProduct=2200'], check=False)
            time.sleep(1)
            subprocess.run(['sudo', 'udevadm', 'trigger', '--action=add', '--subsystem-match=usb', '--attr-match=idVendor=072f', '--attr-match=idProduct=2200'], check=False)
            print("✓ NFC reader hardware reset attempted via udev")
            time.sleep(2)
        except Exception as e:
            print(f"→ udev reset failed: {str(e)}")

        print("✓ Reset sequence completed")
        return True
    except Exception as e:
        print("✗ Hardware reset failed:", str(e))
        return False

def watchdog_thread():
    """Monitor NFC reader activity and reset if necessary."""
    global last_activity_time, reader_active
    while True:
        time.sleep(5)  # Check every 5 seconds
        if reader_active and (time.time() - last_activity_time) > WATCHDOG_TIMEOUT:
            print("⚠ Watchdog: NFC reader appears stuck, attempting reset...")
            reset_nfc_reader()
            last_activity_time = time.time()

def update_activity():
    """Update the last activity timestamp."""
    global last_activity_time
    last_activity_time = time.time()

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
    global reader_active
    reader_active = True
    update_activity()
    
    print("Tag Detected:", tag)
    if not tag.ndef:
        print("→ Not NDEF or not writable.")
        reader_active = False
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
        reader_active = False
        return True
    except Exception as e:
        print("✗ Write failed:", e)
        reader_active = False
        return False

def nfc_reader_thread():
    """Continuously open/close the reader; write one tag per session."""
    global reader_active
    while True:
        clf = None
        try:
            print("Looking for NFC reader…")
            clf = nfc.ContactlessFrontend('usb')
            print("Reader connected! Tap a tag to write.")
            reader_active = True
            update_activity()
            
            while True:
                try:
                    clf.connect(
                        rdwr={
                            'on-connect': on_connect,
                            'beep-on-connect': True,
                            'terminate-after': 1
                        },
                        terminate=lambda: False
                    )
                    print("Tag done—remove it to scan the next one.")
                    time.sleep(1)
                except nfc.clf.CommunicationError as e:
                    print("Tag removed or communication error:", str(e))
                    time.sleep(0.5)
                    continue
                except Exception as e:
                    print("Error during tag operation:", str(e))
                    time.sleep(0.5)
                    continue
        except IOError as e:
            print("No reader found or device error; retrying in 1s…", str(e))
            reader_active = False
            time.sleep(1)
        except Exception as e:
            print("Unexpected NFC error:", str(e))
            reader_active = False
            time.sleep(1)
        finally:
            if clf:
                try:
                    clf.close()
                except:
                    pass
            reader_active = False
            time.sleep(0.5)

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

@app.route('/update-config', methods=['POST'])
def update_config():
    global SERIAL_PREFIX, current_number
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({
                "status": "error",
                "message": "No data provided"
            }), 400

        # Update prefix if provided
        if 'prefix' in payload and payload['prefix']:
            SERIAL_PREFIX = str(payload['prefix']).strip()
            print(f"Updated prefix to: {SERIAL_PREFIX}")

        # Update number if provided
        if 'number' in payload and payload['number'] is not None:
            try:
                current_number = int(payload['number'])
                print(f"Updated current number to: {current_number}")
            except ValueError:
                return jsonify({
                    "status": "error",
                    "message": "Invalid number format"
                }), 400

        # Generate a new serial to verify the update
        test_serial = generate_serial_number()
        
        return jsonify({
            "status": "success",
            "prefix": SERIAL_PREFIX,
            "number": current_number,
            "test_serial": test_serial
        })
    except Exception as e:
        print(f"Error updating configuration: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/reset-reader', methods=['POST'])
def reset_reader():
    """Endpoint to manually trigger NFC reader reset."""
    try:
        reset_nfc_reader()
        return jsonify({
            "status": "success",
            "message": "NFC reader reset initiated"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # Start the watchdog thread
    threading.Thread(target=watchdog_thread, daemon=True).start()
    
    # Fire up the NFC thread
    threading.Thread(target=nfc_reader_thread, daemon=True).start()
    
    print("\nApp running at http://0.0.0.0:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
