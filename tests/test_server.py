from unittest.mock import Mock, patch

import pytest

from grocy_label_printer_escpos.server import GrocyThermalServer, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def thermal_server():
    return GrocyThermalServer(printer_host="test", printer_port=9100)


def test_home_endpoint(client):
    """Test the home status endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "running"
    assert "printer" in data
    assert data["service"] == "Grocy Thermal Label Server"


def test_image_endpoint_get(client):
    """Test image endpoint with GET request"""
    response = client.get("/image?product=Test&grocycode=123")
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_image_endpoint_post(client):
    """Test image endpoint with POST request"""
    data = {
        "product": "Test Product",
        "grocycode": "123456",
        "stock_entry": {"amount": "2", "best_before_date": "2024-12-31"},
    }
    response = client.post("/image", json=data)
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_print_endpoint_missing_data(client):
    """Test print endpoint with missing data"""
    response = client.post("/print")
    assert response.status_code == 400


def test_print_endpoint_missing_product_name(client):
    """Test print endpoint with missing product name"""
    data = {"grocycode": "123"}
    response = client.post("/print", json=data)
    assert response.status_code == 400


@patch("grocy_label_printer_escpos.server.GrocyThermalServer.print_label")
def test_print_endpoint_success(mock_print, client):
    """Test successful print endpoint"""
    mock_print.return_value = True

    data = {"product": "Test Product", "grocycode": "123456"}
    response = client.post("/print", json=data)
    assert response.status_code == 200
    assert response.data == b"OK"
    mock_print.assert_called_once()


@patch("grocy_label_printer_escpos.server.GrocyThermalServer.print_label")
def test_print_endpoint_failure(mock_print, client):
    """Test failed print endpoint"""
    mock_print.return_value = False

    data = {"product": "Test Product", "grocycode": "123456"}
    response = client.post("/print", json=data)
    assert response.status_code == 500
    assert response.data == b"Print failed"


def test_extract_grocy_params(thermal_server):
    """Test Grocy parameter extraction"""
    data = {
        "product": "Test Item",
        "grocycode": "123456",
        "stock_entry": {
            "amount": "2",
            "best_before_date": "2024-12-31",
            "purchased_date": "2024-10-05",
        },
        "quantity_unit_stock": {"name": "piece", "name_plural": "pieces"},
    }

    params = thermal_server.extract_grocy_params(data)

    assert params["name"] == "Test Item"
    assert params["barcode"] == "123456"
    assert params["amount"] == "2"
    assert params["unit_name"] == "pieces"
    assert params["best_before_date"] == "2024-12-31"
    assert params["purchased_date"] == "2024-10-05"


def test_extract_grocy_params_container_weight(thermal_server):
    """Test parameter extraction with container weight (should exclude amount/dates)"""  # noqa: E501
    data = {
        "product": "Test Item",
        "grocycode": "123456",
        "stock_entry": {
            "amount": "2",
            "best_before_date": "2024-12-31",
            "purchased_date": "2024-10-05",
        },
        "stock_entry_userfields": {"StockEntryContainerWeight": "100.5"},
    }

    params = thermal_server.extract_grocy_params(data)

    assert params["name"] == "Test Item"
    assert params["barcode"] == "123456"
    assert params["amount"] == ""
    assert params["best_before_date"] == ""
    assert params["purchased_date"] == ""


def test_unit_name_singular_plural(thermal_server):
    """Test unit name selection (singular vs plural)"""
    quantity_unit_stock = {"name": "piece", "name_plural": "pieces"}

    # Test singular
    result = thermal_server._get_unit_name(quantity_unit_stock, "1")
    assert result == "piece"

    # Test plural
    result = thermal_server._get_unit_name(quantity_unit_stock, "2")
    assert result == "pieces"

    # Test zero
    result = thermal_server._get_unit_name(quantity_unit_stock, "0")
    assert result == "piece"


def test_create_qr_code(thermal_server):
    """Test QR code creation"""
    qr_img = thermal_server.create_qr_code("test123", size=100)
    assert qr_img is not None
    assert qr_img.size == (100, 100)

    # Test empty data
    qr_img = thermal_server.create_qr_code("", size=100)
    assert qr_img is None


def test_create_label_image(thermal_server):
    """Test label image creation"""
    params = {
        "name": "Test Product",
        "barcode": "123456",
        "amount": "2",
        "unit_name": "pieces",
        "best_before_date": "2024-12-31",
        "purchased_date": "2024-10-05",
    }

    img = thermal_server.create_label_image(params)
    assert img is not None
    assert img.size[0] == thermal_server.label_width
    assert img.size[1] > 0  # Height should be calculated


@patch("grocy_label_printer_escpos.server.Network")
def test_connect_printer_success(mock_network, thermal_server):
    """Test successful printer connection"""
    mock_printer = Mock()
    mock_network.return_value = mock_printer

    result = thermal_server.connect_printer()
    assert result is True
    assert thermal_server.printer == mock_printer
    mock_network.assert_called_once_with(
        host=thermal_server.printer_host,
        port=thermal_server.printer_port,
        profile="Sunmi-V2",
    )


@patch("grocy_label_printer_escpos.server.Network")
def test_connect_printer_failure(mock_network, thermal_server):
    """Test failed printer connection"""
    mock_network.side_effect = Exception("Connection failed")

    result = thermal_server.connect_printer()
    assert result is False
    assert thermal_server.printer is None
