#!/usr/bin/env python3
"""
Grocy Thermal Label Server.

Receives Grocy label requests and prints to ESC/P thermal printer.
"""

import io
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import qrcode
from dotenv import load_dotenv
from escpos.printer import Network
from flask import Flask, Response, jsonify, request
from PIL import Image, ImageDraw, ImageFont

# Load environment variables from .env file
load_dotenv()

# Localization strings
TRANSLATIONS = {
    "en": {
        "expires": "Expires",
        "purchased": "Purchased",
    },
    "es": {
        "expires": "Caduca",
        "purchased": "Comprado",
    },
    "fr": {
        "expires": "Expire",
        "purchased": "Acheté",
    },
    "de": {
        "expires": "Verfällt",
        "purchased": "Gekauft",
    },
    "it": {
        "expires": "Scade",
        "purchased": "Acquistato",
    },
}


class GrocyThermalServer:
    """Grocy thermal label server for ESC/P printers."""

    def __init__(
        self,
        printer_host: Optional[str] = None,
        printer_port: Optional[int] = None,
        label_width: Optional[int] = None,
        language: Optional[str] = None,
    ) -> None:
        """Initialize the thermal server with printer configuration."""
        self.printer_host = printer_host or os.getenv(
            "PRINTER_HOST", "192.168.1.100"
        )
        self.printer_port = int(
            printer_port
            if printer_port is not None
            else int(os.getenv("PRINTER_PORT", "9100"))
        )
        self.label_width = int(
            label_width
            if label_width is not None
            else int(os.getenv("LABEL_WIDTH", "384"))
        )
        self.language = language or os.getenv("LANGUAGE", "en")
        self.printer: Optional[Network] = None

        # Use pip-installed Roboto fonts with much larger sizes
        import font_roboto

        self.font_large = ImageFont.truetype(font_roboto.RobotoBold, 48)
        self.font_small = ImageFont.truetype(font_roboto.RobotoBold, 32)

    def connect_printer(self) -> bool:
        """Connect to thermal printer"""
        try:
            self.printer = Network(
                host=self.printer_host,
                port=self.printer_port,
                profile="Sunmi-V2",
            )
            logging.info("Connected to printer")
            return True
        except Exception as e:
            logging.error(f"Printer connection failed: {e}")
            return False

    def extract_grocy_params(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from Grocy request data"""
        logging.info(f"Received Grocy data: {data}")

        # Extract name from various fields
        name_fields = ["product", "battery", "chore", "recipe"]
        name = next(
            (data.get(field, "") for field in name_fields if data.get(field)),
            "",
        )

        # Extract barcode
        barcode = data.get("grocycode", "")

        # Extract stock entry data
        stock_entry = data.get("stock_entry") or {}
        if not isinstance(stock_entry, dict):
            stock_entry = {}

        # Check for special case: exclude amount and dates if container
        # weight is present
        stock_entry_userfields = data.get("stock_entry_userfields") or {}
        container_weight = stock_entry_userfields.get(
            "StockEntryContainerWeight"
        )

        exclude_amount_and_dates = False
        if container_weight is not None:
            try:
                float(container_weight)
                exclude_amount_and_dates = True
            except (ValueError, TypeError):
                pass

        # Extract dates and amount
        best_before_date = (
            ""
            if exclude_amount_and_dates
            else str(stock_entry.get("best_before_date") or "")
        )
        purchased_date = (
            ""
            if exclude_amount_and_dates
            else str(stock_entry.get("purchased_date") or "")
        )
        
        val = stock_entry.get("amount")
        amount = (
            ""
            if exclude_amount_and_dates
            else (str(val) if val is not None else "")
        )

        # Extract unit info
        quantity_unit_stock_raw = (
            data.get("quantity_unit_stock")
            if isinstance(data.get("quantity_unit_stock"), dict)
            else data.get("details", {}).get("quantity_unit_stock", {})
        )
        quantity_unit_stock = quantity_unit_stock_raw or {}

        unit_name = self._get_unit_name(quantity_unit_stock, amount)

        # Extract note
        val = stock_entry.get("note")
        note = str(val) if val is not None else ""

        return {
            "name": name,
            "barcode": barcode,
            "best_before_date": best_before_date,
            "purchased_date": purchased_date,
            "amount": amount,
            "unit_name": unit_name,
            "note": note,
        }

    def _get_unit_name(
        self, quantity_unit_stock: Dict[str, Any], amount: Optional[str]
    ) -> str:
        """Get appropriate unit name (singular/plural)"""
        if not quantity_unit_stock.get("name"):
            return ""

        try:
            amount_float = float(amount) if amount else 0
            if amount_float > 1 and quantity_unit_stock.get("name_plural"):
                return str(quantity_unit_stock["name_plural"])
            return str(quantity_unit_stock["name"])
        except (ValueError, TypeError):
            return str(quantity_unit_stock.get("name", ""))

    def _is_far_future_date(self, date_str: str) -> bool:
        """Check if date is more than 5 years in the future (no expiration)"""
        if not date_str:
            return False

        try:
            # Parse the date string (assuming YYYY-MM-DD format)
            expiry_date = datetime.strptime(date_str, "%Y-%m-%d")
            five_years_from_now = datetime.now() + timedelta(days=5 * 365)
            return expiry_date > five_years_from_now
        except (ValueError, TypeError):
            return False

    def _translate(self, key: str) -> str:
        """Get translated string for the current language."""
        language = self.language or "en"
        return TRANSLATIONS.get(language, TRANSLATIONS["en"]).get(
            key, TRANSLATIONS["en"][key]
        )

    def create_qr_code(
        self, data: str, size: int = 240
    ) -> Optional[Image.Image]:
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
        # Handle both PIL and PyPNG images
        if hasattr(qr_img, "resize"):
            qr_img = qr_img.resize((size, size), Image.Resampling.LANCZOS)
        return qr_img  # type: ignore[return-value]

    def _wrap_text(
        self, text: str, font: ImageFont.FreeTypeFont, max_width: int
    ) -> List[str]:
        """Wrap text to fit within max_width using the given font."""
        words = text.split()
        lines = []
        current_line: list = []

        # Create temporary image for measuring text
        temp_img = Image.new("L", (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = temp_draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, add it anyway
                    lines.append(word)

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def _build_text_lines(
        self, params: Dict[str, Any], padding: int
    ) -> Tuple[List[str], int]:
        """Build text lines for the label."""
        lines = []
        name_line_count = 0
        if params["name"]:
            # Wrap text properly based on font width
            max_text_width = self.label_width - (padding * 2)
            name_lines = self._wrap_text(
                params["name"], self.font_large, max_text_width
            )
            lines.extend(name_lines)
            name_line_count = len(name_lines)

        if params["amount"] and params["unit_name"]:
            lines.append(f"{params['amount']} {params['unit_name']}")

        # Show date range if both dates are present
        best_before = params["best_before_date"]
        purchased = params["purchased_date"]

        # Check if expiration is far in the future (>5 years = no expiration)
        has_real_expiry = best_before and not self._is_far_future_date(
            best_before
        )

        if purchased and has_real_expiry:
            lines.append(f"{purchased} - {best_before}")
        elif has_real_expiry:
            lines.append(f"{self._translate('expires')}: {best_before}")
        elif purchased:
            lines.append(f"{self._translate('purchased')}: {purchased}")

        if params.get("note"):
            # Wrap note text
            max_text_width = self.label_width - (padding * 2)
            note_lines = self._wrap_text(
                params["note"], self.font_small, max_text_width
            )
            lines.extend(note_lines)

        return lines, name_line_count

    def _calculate_label_height(
        self,
        params: Dict[str, Any],
        lines: List[str],
        line_height: int,
        padding: int,
        qr_size: int,
    ) -> int:
        """Calculate the total height needed for the label."""
        # Calculate actual font height for proper bottom padding
        temp_img = Image.new("L", (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)

        # Get the height of both fonts to ensure we have enough space
        large_bbox = temp_draw.textbbox((0, 0), "Tgyj", font=self.font_large)
        small_bbox = temp_draw.textbbox((0, 0), "Tgyj", font=self.font_small)

        large_font_height = large_bbox[3] - large_bbox[1]
        small_font_height = small_bbox[3] - small_bbox[1]

        # Use the larger font height as bottom padding for complete rendering
        bottom_padding = int(max(large_font_height, small_font_height))

        text_height = len(lines) * line_height + padding + bottom_padding
        if params["barcode"]:
            return qr_size + padding * 2 + text_height
        else:
            return text_height + padding

    def _add_qr_code(
        self,
        img: Image.Image,
        params: Dict[str, Any],
        qr_size: int,
        current_y: int,
    ) -> int:
        """Add QR code to the image if barcode exists."""
        if params["barcode"]:
            qr_img = self.create_qr_code(params["barcode"], qr_size)
            if qr_img:
                qr_x = (self.label_width - qr_size) // 2  # Center the QR code
                img.paste(qr_img, (qr_x, current_y))
                return current_y + qr_size + 15  # padding
        return current_y

    def _add_text_lines(
        self,
        draw: ImageDraw.ImageDraw,
        lines: List[str],
        name_line_count: int,
        current_y: int,
        line_height: int,
    ) -> None:
        """Add text lines to the label."""
        for i, line in enumerate(lines):
            # Use large font for all name lines, small font for other info
            font = self.font_large if i < name_line_count else self.font_small
            # Center the text
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = (self.label_width - text_width) // 2
            draw.text((text_x, current_y), line, fill=0, font=font)

            # Add extra spacing after the last name line
            if i == name_line_count - 1:
                current_y += line_height + 20  # Extra 20px spacing after name
            elif i < name_line_count:
                current_y += (
                    line_height + 10
                )  # Extra spacing between name lines
            else:
                current_y += line_height

    def create_label_image(self, params: Dict[str, Any]) -> Image.Image:
        """Create label image from Grocy parameters.

        QR code first, then text below.
        """
        # Calculate label dimensions
        line_height = 35
        padding = 15
        qr_size = 240  # Double size QR code

        # Build text lines
        lines, name_line_count = self._build_text_lines(params, padding)

        # Calculate image height
        label_height = self._calculate_label_height(
            params, lines, line_height, padding, qr_size
        )

        # Create image
        img = Image.new("L", (self.label_width, label_height), color=255)
        draw = ImageDraw.Draw(img)

        current_y = padding

        # Add QR code at top center if barcode exists
        current_y = self._add_qr_code(img, params, qr_size, current_y)

        # Add text lines below QR code
        self._add_text_lines(
            draw, lines, name_line_count, current_y, line_height
        )

        return img

    def print_label(self, params: Dict[str, Any]) -> bool:
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
            if self.printer is not None:
                self.printer.image(label_img)
                self.printer.text("\n\n\n\n")  # Add some spacing after label

                # Feed paper to advance label past the cutter
                # self.printer.ln(3)  # Feed 3 lines to move past cutter

                # Close the printer connection to flush the buffer
                if hasattr(self.printer, "close"):
                    self.printer.close()

            logging.info(
                f"Successfully sent label to printer for: {params['name']}"
            )
            return True

        except Exception as e:
            logging.error(f"Print error: {e}")
            return False
        finally:
            # Ensure connection is closed
            try:
                if self.printer and hasattr(self.printer, "close"):
                    self.printer.close()
            except Exception as e:
                logging.debug(f"Error closing printer connection: {e}")
            self.printer = None


# Flask app setup
app = Flask(__name__)
thermal_server = GrocyThermalServer()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_file = os.getenv("LOG_FILE", "grocy_server.log")


logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)


@app.before_request
def log_requests() -> None:
    """Log incoming requests"""
    if request.method == "POST":
        logging.info(f"POST request to {request.path}")
        if request.is_json:
            logging.info(f"JSON data: {request.get_json()}")


@app.route("/")
def home() -> Response:
    """Status endpoint"""
    return jsonify(
        {
            "status": "running",
            "printer": f"{thermal_server.printer_host}: {thermal_server.printer_port}",  # noqa: E501
            "service": "Grocy Thermal Label Server",
        }
    )


@app.route("/print", methods=["POST"])
def print_label() -> Response:
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
        if not params["name"]:
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
def preview_image() -> Response:
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
def test_label() -> Response:
    """Test endpoint with sample data - returns image preview"""
    test_data = {
        "product": "Test Product",
        "grocycode": "12345",
        "stock_entry": {
            "best_before_date": "2024-12-31",
            "purchased_date": "2024-10-05",
            "amount": "2",
            "note": "This is a test note.",
        },
        "quantity_unit_stock": {"name": "piece", "name_plural": "pieces"},
    }

    params = thermal_server.extract_grocy_params(test_data)
    
    # Create label image
    label_img = thermal_server.create_label_image(params)

    # Return image as PNG
    buf = io.BytesIO()
    label_img.save(buf, format="PNG")
    buf.seek(0)

    return Response(buf.getvalue(), mimetype="image/png")


def main() -> None:
    """Main entry point for the CLI script - for development use only"""
    host = os.getenv("SERVER_HOST", "0.0.0.0")  # nosec B104
    port = int(os.getenv("SERVER_PORT", "5000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"

    print("Grocy Thermal Label Server")
    print("=" * 30)
    print(
        f"Printer: {thermal_server.printer_host}: {thermal_server.printer_port}"  # noqa: E501
    )
    print("Endpoints:")
    print("  POST /print - Print Grocy label")
    print("  GET/POST /image - Preview label image")
    print("  GET /test - Preview test label")
    print("  GET / - Server status")
    server_url = f"http://{host}:{port}"  # noqa: E231
    print(f"\nStarting Flask development server on {server_url}")
    print("Note: For production, use gunicorn instead")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
