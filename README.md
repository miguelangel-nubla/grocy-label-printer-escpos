# Grocy Label Printer ESC/P

A Flask server that receives Grocy label requests and prints them to ESC/P thermal printers.

[![CI](https://github.com/miguelangel-nubla/grocy-label-printer-escpos/actions/workflows/ci.yml/badge.svg)](https://github.com/miguelangel-nubla/grocy-label-printer-escpos/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/grocy-label-printer-escpos.svg)](https://badge.fury.io/py/grocy-label-printer-escpos)
[![Docker](https://img.shields.io/docker/v/ghcr.io/miguelangel-nubla/grocy-label-printer-escpos?label=docker)](https://github.com/miguelangel-nubla/grocy-label-printer-escpos/pkgs/container/grocy-label-printer-escpos)

## Features

- **Grocy Integration**: Compatible with Grocy's label printing system
- **ESC/P Support**: Works with ESC/P thermal printers via network
- **QR Code Generation**: Automatically generates QR codes from Grocy barcodes
- **Smart Layout**: QR code at top, product information below
- **Font Management**: Uses Roboto Bold fonts in multiple sizes
- **Container Support**: Available as Docker images for easy deployment
- **Multi-Architecture**: Supports AMD64 and ARM64 architectures

## Quick Start

### Docker (Recommended)

```bash
docker run -d \
  --name grocy-label-printer \
  -p 5000:5000 \
  -e PRINTER_HOST=192.168.1.100 \
  -e PRINTER_PORT=9100 \
  ghcr.io/miguelangel-nubla/grocy-label-printer-escpos:latest
```

### Python Package

```bash
pip install grocy-label-printer-escpos
grocy-label-printer-escpos
```

### From Source

```bash
git clone https://github.com/miguelangel-nubla/grocy-label-printer-escpos.git
cd grocy-label-printer-escpos
pip install -e .
python -m grocy_label_printer_escpos.server
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PRINTER_HOST` | `192.168.1.100` | IP address of the thermal printer |
| `PRINTER_PORT` | `9100` | Port of the thermal printer |
| `LABEL_WIDTH` | `384` | Width of labels in pixels |
| `SERVER_HOST` | `0.0.0.0` | Server bind address |
| `SERVER_PORT` | `5000` | Server port |

### Grocy Configuration

In Grocy, configure a new label printer:

1. Go to **Manage > Label printers**
2. Add a new printer with these settings:
   - **Name**: ESC/P Thermal Printer
   - **Type**: Generic
   - **URL**: `http://your-server:5000/print`
   - **HTTP Method**: POST

## API Endpoints

### `POST /print`
Print a label from Grocy data.

**Request Body**: Grocy label data (JSON or form-encoded)

**Response**:
- `200 OK` - Label printed successfully
- `400 Bad Request` - Invalid or missing data
- `500 Internal Server Error` - Print failed

### `GET|POST /image`
Preview label image without printing.

**Parameters**: Same as `/print`

**Response**: PNG image of the label

### `GET /test`
Print a test label with sample data.

**Response**:
```json
{"status": "success", "message": "Test label printed"}
```

### `GET /`
Server status and configuration.

**Response**:
```json
{
  "status": "running",
  "printer": "192.168.1.100:9001",
  "service": "Grocy Thermal Label Server"
}
```

## Label Format

Labels include:
- **QR Code**: Generated from Grocy barcode (top, centered)
- **Product Name**: Large bold font (centered)
- **Amount & Unit**: Medium font (if available)
- **Best Before Date**: Medium font (if available)
- **Purchase Date**: Medium font (if available)

Special handling:
- Long product names are automatically split across lines
- Container weight items exclude amount/date information
- Proper singular/plural unit names

## Printer Compatibility

Tested with:
- Sunmi integrated 58mm thermal printers

## Development

### Setup

```bash
git clone https://github.com/miguelangel-nubla/grocy-label-printer-escpos.git
cd grocy-label-printer-escpos
pip install -e ".[dev]"
pre-commit install
```

### Testing

```bash
pytest
```

### Code Quality

```bash
black src/ tests/
isort src/ tests/
flake8 src/ tests/
mypy src/
```

### Building

```bash
python -m build
```

## Deployment

### Docker Compose

```yaml
version: '3.8'
services:
  grocy-label-printer:
    image: ghcr.io/miguelangel-nubla/grocy-label-printer-escpos:latest
    ports:
      - "5000:5000"
    environment:
      - PRINTER_HOST=192.168.1.100
      - PRINTER_PORT=9100
    restart: unless-stopped
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grocy-label-printer
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grocy-label-printer
  template:
    metadata:
      labels:
        app: grocy-label-printer
    spec:
      containers:
      - name: grocy-label-printer
        image: ghcr.io/miguelangel-nubla/grocy-label-printer-escpos:latest
        ports:
        - containerPort: 5000
        env:
        - name: PRINTER_HOST
          value: "192.168.1.100"
        - name: PRINTER_PORT
          value: "9100"
---
apiVersion: v1
kind: Service
metadata:
  name: grocy-label-printer
spec:
  selector:
    app: grocy-label-printer
  ports:
  - port: 5000
    targetPort: 5000
```

## Troubleshooting

### Printer Connection Issues

1. **Check network connectivity**:
   ```bash
   telnet 192.168.1.100 9100
   ```

2. **Verify printer profile**: Some printers may need different profiles. Try:
   - `TM-T20`
   - `Generic`
   - `TM-T88III`

3. **Check printer logs**:
   ```bash
   docker logs grocy-label-printer
   ```

### Label Not Printing

1. **Test with sample data**:
   ```bash
   curl http://localhost:5000/test
   ```

2. **Check Grocy data format**:
   ```bash
   curl -X POST http://localhost:5000/image \
     -H "Content-Type: application/json" \
     -d '{"product": "Test", "grocycode": "123"}'
   ```

3. **Verify printer buffer**: Ensure the printer connection is properly closed after each print job.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Releases

See [GitHub Releases](https://github.com/miguelangel-nubla/grocy-label-printer-escpos/releases) for version history and changes.
