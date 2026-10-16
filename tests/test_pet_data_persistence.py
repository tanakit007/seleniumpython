import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

WAIT_TIMEOUT = 10
PET_TABLE_ROWS = (By.CSS_SELECTOR, "#pets-table-body tr")
EMPTY_STATE = (By.ID, "empty-state")
DELETE_CONFIRM_BUTTON = (By.CSS_SELECTOR, ".swal2-confirm")
DELETE_CANCEL_BUTTON = (By.CSS_SELECTOR, ".swal2-cancel")
ALERT_POPUP = (By.CSS_SELECTOR, ".swal2-popup")
SLOW_STEP_DELAY = 0.5


def _slow_down() -> None:
    """ช่วยหน่วงเวลาระหว่างขั้นตอนเพื่อให้ UI/Animation ทำงานได้ทัน"""
    time.sleep(SLOW_STEP_DELAY)


def _find_app_root() -> Path:
    configured_root = os.environ.get("PET_APP_DIR")
    candidates: List[Path] = []
    if configured_root:
        candidates.append(Path(configured_root).expanduser().resolve())

    test_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            Path.cwd().resolve(),
            Path.cwd().resolve().parent / "pet-hydro-feed-calculator",
            test_root / "pet-hydro-feed-calculator",
        ]
    )

    for candidate in candidates:
        if (candidate / "server.js").is_file() and (candidate / "package.json").is_file():
            return candidate

    raise RuntimeError(
        "Cannot find pet-hydro-feed-calculator. Set PET_APP_DIR to its absolute path."
    )


def _api_json(url: str, method: str = "GET") -> dict:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _clear_pets(base_url: str) -> None:
    response = _api_json(f"{base_url}/api/pets")
    if not response.get("success"):
        raise RuntimeError(f"Unable to read test data: {response}")

    for pet in response["data"]:
        result = _api_json(f"{base_url}/api/pets/{pet['id']}", method="DELETE")
        if not result.get("success"):
            raise RuntimeError(f"Unable to remove leftover test data: {result}")


@pytest.fixture(scope="session")
def app_url():
    app_root = _find_app_root()
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js was not found on PATH.")

    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "PORT": str(port),
            "NODE_ENV": "test",
        }
    )
    for key in (
        "TURSO_DATABASE_URL",
        "TURSO_URL",
        "TURSO_AUTH_TOKEN",
        "TURSO_API_TOKEN",
    ):
        environment.pop(key, None)

    temp_dir = tempfile.mkdtemp(prefix="pet-hydro-selenium-")
    try:
        log_path = Path(temp_dir) / "server.log"
        environment["DB_PATH"] = str(Path(temp_dir) / "pets.db")

        with log_path.open("w", encoding="utf-8") as server_log:
            server = subprocess.Popen(
                [node, "server.js"],
                cwd=app_root,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )

            try:
                deadline = time.monotonic() + 30
                server_ready = False
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError(
                            "App server stopped during startup:\n"
                            + log_path.read_text(encoding="utf-8")
                        )
                    try:
                        response = _api_json(f"{base_url}/api/pets")
                        if response.get("success"):
                            server_ready = True
                            break
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(0.3)

                if not server_ready:
                    raise RuntimeError(
                        "App server did not start within 30 seconds:\n"
                        + log_path.read_text(encoding="utf-8")
                    )

                yield base_url
            finally:
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1200")

    repository_root = Path(__file__).resolve().parents[2]
    driver_candidates = [
        repository_root / "testselenium" / "chromedriver.exe",
        repository_root.parent / "testselenium" / "chromedriver.exe",
    ]
    driver_path = next((path for path in driver_candidates if path.is_file()), None)

    service = Service(str(driver_path)) if driver_path else Service()
    return webdriver.Chrome(service=service, options=options)


@pytest.fixture
def browser(app_url):
    _clear_pets(app_url)
    driver = _create_driver()
    try:
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        driver.get(app_url)
        wait.until(EC.visibility_of_element_located((By.ID, "pet-form")))
        wait.until(EC.text_to_be_present_in_element((By.ID, "summary-total-pets"), "0"))
        yield driver
    finally:
        driver.quit()


def _wait(driver: webdriver.Chrome) -> WebDriverWait:
    return WebDriverWait(driver, WAIT_TIMEOUT)


def _pet_row(name: str) -> Tuple[str, str]:
    return (
        By.XPATH,
        f"//tbody[@id='pets-table-body']/tr[td[1][normalize-space()='{name}']]",
    )


def _rows(driver: webdriver.Chrome):
    return driver.find_elements(*PET_TABLE_ROWS)


def _row_count(driver: webdriver.Chrome) -> int:
    return len(_rows(driver))


def _wait_visible(driver: webdriver.Chrome, locator: Tuple[str, str]) -> None:
    _wait(driver).until(EC.visibility_of_element_located(locator))


def _wait_hidden(driver: webdriver.Chrome, locator: Tuple[str, str]) -> None:
    _wait(driver).until(EC.invisibility_of_element_located(locator))


def _wait_for_text(
    driver: webdriver.Chrome, locator: Tuple[str, str], text: str
) -> None:
    _wait(driver).until(EC.text_to_be_present_in_element(locator, text))


def _wait_for_total(driver: webdriver.Chrome, expected: int) -> None:
    _wait_for_text(driver, (By.ID, "summary-total-pets"), str(expected))


def _wait_for_empty_state(driver: webdriver.Chrome) -> None:
    _wait_visible(driver, EMPTY_STATE)


def _add_pet(driver: webdriver.Chrome, name: str) -> None:
    _slow_down()
    driver.find_element(By.ID, "pet-name").send_keys(name)
    Select(driver.find_element(By.ID, "pet-type")).select_by_value("dog")
    driver.find_element(By.ID, "pet-breed").send_keys("Golden Retriever")
    driver.find_element(By.ID, "pet-weight").send_keys("25")
    Select(driver.find_element(By.ID, "pet-activity")).select_by_value("medium")
    _slow_down()
    driver.find_element(By.ID, "btn-submit").click()
    _wait_visible(driver, _pet_row(name))
    _wait_for_total(driver, 1)
    _slow_down()


def _click_delete(driver: webdriver.Chrome, name: str) -> None:
    _slow_down()
    driver.find_element(
        By.CSS_SELECTOR, f"button.btn-delete[aria-label='ลบ {name}']"
    ).click()


def _confirm_delete(driver: webdriver.Chrome, name: str) -> None:
    _click_delete(driver, name)
    _confirm_dialog(driver)


def _confirm_dialog(driver: webdriver.Chrome) -> None:
    _wait_visible(driver, DELETE_CONFIRM_BUTTON)
    _slow_down()
    driver.find_element(*DELETE_CONFIRM_BUTTON).click()
    _slow_down()


def _cancel_dialog(driver: webdriver.Chrome) -> None:
    _wait_visible(driver, DELETE_CANCEL_BUTTON)
    _slow_down()
    driver.find_element(*DELETE_CANCEL_BUTTON).click()
    _slow_down()


def test_ST_DATA_03_เพิ่มลบและรีเฟรชแล้วข้อมูลที่ลบไม่กลับมา(browser):
    """เพิ่มและลบสัตว์เลี้ยง แล้วตรวจสอบข้อมูลหลังรีเฟรช"""
    _add_pet(browser, "Test-Pet-01")

    assert _row_count(browser) == 1
    assert "Test-Pet-01" in _rows(browser)[0].text
    _wait_for_total(browser, 1)

    _confirm_delete(browser, "Test-Pet-01")
    _wait_hidden(browser, _pet_row("Test-Pet-01"))
    _wait_for_total(browser, 0)

    _slow_down()
    browser.refresh()
    _wait_for_empty_state(browser)
    _wait_for_total(browser, 0)
    assert _row_count(browser) == 0


def test_ST_DATA_04_ยกเลิกลบแล้วข้อมูลยังอยู่หลังรีเฟรช(browser):
    """ยกเลิกการลบ แล้วตรวจสอบว่าข้อมูลยังอยู่หลังรีเฟรช"""
    _add_pet(browser, "Test-Pet-02")

    _click_delete(browser, "Test-Pet-02")
    _wait_visible(browser, ALERT_POPUP)
    _cancel_dialog(browser)
    _wait_hidden(browser, ALERT_POPUP)

    assert _row_count(browser) == 1
    _wait_for_total(browser, 1)

    _slow_down()
    browser.refresh()
    _wait_visible(browser, _pet_row("Test-Pet-02"))
    _wait_for_total(browser, 1)


def test_ST_DATA_05_ลบข้ามแท็บและแจ้งข้อผิดพลาดเมื่อลบข้อมูลซ้ำ(browser, app_url):
    """ลบจากแท็บหนึ่ง แล้วตรวจสอบแท็บอื่นที่ยังมีข้อมูลเก่า"""
    _add_pet(browser, "Test-Pet-03")
    tab_a = browser.current_window_handle
    browser.switch_to.new_window("tab")
    tab_b = browser.current_window_handle
    browser.get(app_url)
    _wait_visible(browser, _pet_row("Test-Pet-03"))
    _wait_for_total(browser, 1)

    browser.switch_to.window(tab_a)
    _confirm_delete(browser, "Test-Pet-03")
    _wait_for_empty_state(browser)
    _wait_for_total(browser, 0)

    browser.switch_to.window(tab_b)
    _click_delete(browser, "Test-Pet-03")
    _confirm_dialog(browser)
    _wait_for_text(browser, ALERT_POPUP, "Pet not found")
    assert _row_count(browser) == 1

    _slow_down()
    browser.refresh()
    _wait_for_empty_state(browser)
    _wait_for_total(browser, 0)
    assert _row_count(browser) == 0


def test_ST_DATA_06_ลบรายการสุดท้ายแล้วแสดงสถานะว่างและยอดรวมศูนย์(browser):
    """ลบสัตว์เลี้ยงตัวสุดท้าย แล้วตรวจสอบสถานะว่างและยอดรวม"""
    _add_pet(browser, "Test-Pet-Last")
    assert _row_count(browser) == 1
    _wait_for_total(browser, 1)

    _confirm_delete(browser, "Test-Pet-Last")
    _wait_for_empty_state(browser)
    _wait_for_total(browser, 0)
    assert "ยังไม่มีข้อมูลสัตว์เลี้ยง" in browser.find_element(By.ID, "empty-state").text

    _slow_down()
    browser.refresh()
    _wait_for_empty_state(browser)
    _wait_for_total(browser, 0)
    assert _row_count(browser) == 0


def test_ST_DATA_07_เครือข่ายขัดข้องระหว่างลบแล้วข้อมูลยังอยู่หลังเชื่อมต่อใหม่(
    browser,
):
    """จำลองเครือข่ายขัดข้องระหว่างลบ แล้วตรวจสอบข้อมูลหลังเชื่อมต่อใหม่"""
    _add_pet(browser, "Test-Pet-Offline")
    browser.execute_cdp_cmd("Network.enable", {})
    offline = {
        "offline": True,
        "latency": 0,
        "downloadThroughput": 0,
        "uploadThroughput": 0,
    }
    browser.execute_cdp_cmd("Network.emulateNetworkConditions", offline)

    try:
        _confirm_delete(browser, "Test-Pet-Offline")
        _wait_for_text(browser, ALERT_POPUP, "ไม่สามารถลบข้อมูลได้")
        assert _row_count(browser) == 1
        _wait_for_total(browser, 1)
    finally:
        online = {
            **offline,
            "offline": False,
            "downloadThroughput": -1,
            "uploadThroughput": -1,
        }
        browser.execute_cdp_cmd("Network.emulateNetworkConditions", online)
        browser.execute_cdp_cmd("Network.disable", {})

    _slow_down()
    browser.refresh()
    _wait_visible(browser, _pet_row("Test-Pet-Offline"))
    _wait_for_total(browser, 1)