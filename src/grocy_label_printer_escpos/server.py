#!/usr/bin/env python3
"""
Grocy Thermal Label Server
Receives Grocy label requests and prints to ESC/P thermal printer
"""

import logging
import os
from flask import Flask, Response, request, jsonify
from PIL import Image, ImageDraw, ImageFont
from escpos.printer import Network
import qrcode
import io

class GrocyThermalServer:
    def __init__(self, printer_host=None, printer_port=None, label_width=None):
        self.printer_host = printer_host or os.getenv('PRINTER_HOST', '192.168.1.100')
        self.printer_port = int(printer_port or os.getenv('PRINTER_PORT', '9100'))
        self.label_width = int(label_width or os.getenv('LABEL_WIDTH', '384'))
        self.printer = None

        # Use pip-installed Roboto fonts with much larger sizes
        import font_roboto
        self.font_large = ImageFont.truetype(font_roboto.RobotoBold, 48)
        self.font_small = ImageFont.truetype(font_roboto.RobotoBold, 32)

    def connect_printer(self):
        """Connect to thermal printer"""
        try:
            self.printer = Network(host=self.printer_host, port=self.printer_port, profile="Sunmi-V2")
            logging.info(f"Connected to printer {self.printer_host}:{self.printer_port}")
            return True
        except Exception as e:
            logging.error(f"Printer connection failed: {e}")
            return False

    def extract_grocy_params(self, data):
        """Extract parameters from Grocy request data"""
        logging.info(f"Received Grocy data: {data}")

        # Extract name from various fields
        name_fields = ['product', 'battery', 'chore', 'recipe']
        name = next((data.get(field, '') for field in name_fields if data.get(field)), '')

        # Extract barcode
        barcode = data.get('grocycode', '')

        # Extract stock entry data
        stock_entry = data.get('stock_entry') or {}
        if not isinstance(stock_entry, dict):
            stock_entry = {}

        # Check for special case: exclude amount and dates if container weight is present
        stock_entry_userfields = data.get('stock_entry_userfields') or {}
        container_weight = stock_entry_userfields.get('StockEntryContainerWeight')

        exclude_amount_and_dates = False
        if container_weight is not None:
            try:
                float(container_weight)
                exclude_amount_and_dates = True
            except (ValueError, TypeError):
                pass

        # Extract dates and amount
        best_before_date = '' if exclude_amount_and_dates else str(stock_entry.get('best_before_date', ''))
        purchased_date = '' if exclude_amount_and_dates else str(stock_entry.get('purchased_date', ''))
        amount = '' if exclude_amount_and_dates else str(stock_entry.get('amount', ''))

        # Extract unit info
        quantity_unit_stock = (
            data.get('quantity_unit_stock') if isinstance(data.get('quantity_unit_stock'), dict)
            else data.get('details', {}).get('quantity_unit_stock', {})
        )

        unit_name = self._get_unit_name(quantity_unit_stock, amount)

        return {
            'name': name,
            'barcode': barcode,
            'best_before_date': best_before_date,
            'purchased_date': purchased_date,
            'amount': amount,
            'unit_name': unit_name
        }

    def _get_unit_name(self, quantity_unit_stock, amount):
        """Get appropriate unit name (singular/plural)"""
        if not quantity_unit_stock.get('name'):
            return ''

        try:
            amount_float = float(amount) if amount else 0
            if amount_float > 1 and quantity_unit_stock.get('name_plural'):
                return str(quantity_unit_stock['name_plural'])
            return str(quantity_unit_stock['name'])
        except (ValueError, TypeError):
            return str(quantity_unit_stock.get('name', ''))

    def create_qr_code(self, data, size=240):
        """Create QR code image - double size"""
        if not data:
            return None

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,  # Double the box size
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((size, size), Image.LANCZOS)
        return qr_img

    def create_label_image(self, params):
        """Create label image from Grocy parameters - QR first, then text below"""
        # Calculate label dimensions
        line_height = 35
        padding = 15
        qr_size = 240    # Double size QR code

        # Count lines needed
        lines = []
        if params['name']:
            # Split long names - adjust for bigger fonts
            name_words = params['name'].split()
            if len(params['name']) > 20:
                mid = len(name_words) // 2
                lines.append(' '.join(name_words[:mid]))
                lines.append(' '.join(name_words[mid:]))
            else:
                lines.append(params['name'])

        if params['amount'] and params['unit_name']:
            lines.append(f"{params['amount']} {params['unit_name']}")

        if params['best_before_date']:
            lines.append(f"Best: {params['best_before_date']}")

        if params['purchased_date']:
            lines.append(f"Purchased: {params['purchased_date']}")

        # Calculate image height - QR first, then text below
        text_height = len(lines) * line_height + padding
        if params['barcode']:
            label_height = qr_size + padding * 2 + text_height
        else:
            label_height = text_height + padding

        # Create image
        img = Image.new('L', (self.label_width, label_height), color=255)
        draw = ImageDraw.Draw(img)

        current_y = padding

        # Add QR code at top center if barcode exists
        if params['barcode']:
            qr_img = self.create_qr_code(params['barcode'], qr_size)
            if qr_img:
                qr_x = (self.label_width - qr_size) // 2  # Center the QR code
                img.paste(qr_img, (qr_x, current_y))
                current_y += qr_size + padding

        # Add text lines below QR code
        for i, line in enumerate(lines):
            font = self.font_large if i == 0 else self.font_small
            if font:
                # Center the text
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                text_x = (self.label_width - text_width) // 2
                draw.text((text_x, current_y), line, fill=0, font=font)
            else:
                # Fallback without font
                draw.text((padding, current_y), line, fill=0)

            # Add extra spacing after the title (first line)
            if i == 0:
                current_y += line_height + 20  # Extra 20px spacing after title
            else:
                current_y += line_height

        return img

    def print_label(self, params):
        """Print label to thermal printer"""
        logging.info(f"Attempting to print label for: {params['name']}")

        if not self.connect_printer():
            logging.error("Failed to connect to printer")
            return False

        try:
            # Create label image
            label_img = self.create_label_image(params)
            logging.info(f"Created label image: {label_img.size}")

            # Print to thermal printer
            self.printer.image(label_img)
            self.printer.text("\n\n\n\n")  # Add some spacing after label

            # Feed paper to advance label past the cutter
            #self.printer.ln(3)  # Feed 3 lines to move past cutter

            # Close the printer connection to flush the buffer
            if hasattr(self.printer, 'close'):
                self.printer.close()

            logging.info(f"Successfully sent label to printer for: {params['name']}")
            return True

        except Exception as e:
            logging.error(f"Print error: {e}")
            return False
        finally:
            # Ensure connection is closed
            try:
                if self.printer and hasattr(self.printer, 'close'):
                    self.printer.close()
            except:
                pass
            self.printer = None

# Flask app setup
app = Flask(__name__)
thermal_server = GrocyThermalServer()

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_file = os.getenv('LOG_FILE', '/app/logs/grocy_server.log')

# Ensure log directory exists
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

@app.before_request
def log_requests():
    """Log incoming requests"""
    if request.method == "POST":
        logging.info(f"POST request to {request.path}")
        if request.is_json:
            logging.info(f"JSON data: {request.get_json()}")

@app.route("/")
def home():
    """Status endpoint"""
    return jsonify({
        "status": "running",
        "printer": f"{thermal_server.printer_host}:{thermal_server.printer_port}",
        "service": "Grocy Thermal Label Server"
    })

@app.route("/print", methods=["POST"])
def print_label():
    """Print label endpoint - compatible with Grocy"""
    try:
        logging.info("Print endpoint called")

        # Get data from request
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()

        logging.info(f"Received data: {data}")

        if not data:
            logging.error("No data received")
            return Response("No data received", 400)

        # Extract Grocy parameters
        params = thermal_server.extract_grocy_params(data)
        logging.info(f"Extracted params: {params}")

        # Validate required fields
        if not params['name']:
            logging.error("Product name required")
            return Response("Product name required", 400)

        # Print label
        logging.info("Calling print_label function")
        success = thermal_server.print_label(params)
        logging.info(f"Print result: {success}")

        if success:
            return Response("OK", 200)
        else:
            return Response("Print failed", 500)

    except Exception as e:
        logging.error(f"Print endpoint error: {e}")
        return Response(f"Error: {e}", 500)

@app.route("/image", methods=["GET", "POST"])
def preview_image():
    """Preview label image endpoint"""
    try:
        # Get data from request
        if request.method == "POST":
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form.to_dict()
        else:
            data = request.args.to_dict()

        if not data:
            return Response("No data received", 400)

        # Extract Grocy parameters
        params = thermal_server.extract_grocy_params(data)

        # Create label image
        label_img = thermal_server.create_label_image(params)

        # Return image as PNG
        buf = io.BytesIO()
        label_img.save(buf, format="PNG")
        buf.seek(0)

        return Response(buf.getvalue(), mimetype="image/png")

    except Exception as e:
        logging.error(f"Image endpoint error: {e}")
        return Response(f"Error: {e}", 500)

@app.route("/test", methods=["GET"])
def test_label():
    """Test endpoint with sample data"""
    test_data = {
        "product": "Test Product",
        "grocycode": "12345",
        "stock_entry": {
            "best_before_date": "2024-12-31",
            "purchased_date": "2024-10-05",
            "amount": "2"
        },
        "quantity_unit_stock": {
            "name": "piece",
            "name_plural": "pieces"
        }
    }

    params = thermal_server.extract_grocy_params(test_data)
    success = thermal_server.print_label(params)

    if success:
        return jsonify({"status": "success", "message": "Test label printed"})
    else:
        return jsonify({"status": "error", "message": "Print failed"}), 500

def main():
    """Main entry point for the CLI script"""
    host = os.getenv('SERVER_HOST', '0.0.0.0')
    port = int(os.getenv('SERVER_PORT', '5000'))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'

    print("Grocy Thermal Label Server")
    print("=" * 30)
    print(f"Printer: {thermal_server.printer_host}:{thermal_server.printer_port}")
    print("Endpoints:")
    print("  POST /print - Print Grocy label")
    print("  GET/POST /image - Preview label image")
    print("  GET /test - Print test label")
    print("  GET / - Server status")
    print(f"\nStarting server on http://{host}:{port}")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()