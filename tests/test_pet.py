import json, os, shutil, socket, subprocess, tempfile, time, urllib.request
from pathlib import Path
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

WAIT_TIMEOUT = 10
PET_TABLE_ROWS = (By.CSS_SELECTOR, "#pets-table-body tr")
SLOW_STEP_DELAY = 0.5

# --- APP SETUP HELPERS ---

def _find_app_root() -> Path:
    configured_root = os.environ.get("PET_APP_DIR")
    candidates = []
    if configured_root:
        candidates.append(Path(configured_root).expanduser().resolve())

    cwd = Path.cwd().resolve()
    test_root = Path(__file__).resolve().parents[2]
    
    candidates.extend([
        cwd,
        cwd.parent / "pet-hydro-feed-calculator",
        cwd / "pet-hydro-feed-calculator",
        test_root / "pet-hydro-feed-calculator",
    ])

    for candidate in candidates:
        if (candidate / "server.js").is_file() and (candidate / "package.json").is_file():
            return candidate

    raise RuntimeError(f"Cannot find server.js in candidates: {candidates}. Set PET_APP_DIR to absolute path.")

def _api_request(url: str, method: str = "GET") -> dict:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=5) as res:
        return json.loads(res.read().decode("utf-8"))

def _clear_pets(base_url: str) -> None:
    try:
        data = _api_request(f"{base_url}/api/pets").get("data", [])
        for pet in data:
            _api_request(f"{base_url}/api/pets/{pet['id']}", method="DELETE")
    except Exception:
        pass

# --- FIXTURES ---

@pytest.fixture(scope="session")
def app_url():
    app_root = _find_app_root()
    node = shutil.which("node") or "node"

    # สุ่ม free port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    base_url = f"http://127.0.0.1:{port}"
    temp_dir = tempfile.mkdtemp(prefix="pet-hydro-")
    
    env = os.environ.copy()
    env.update({
        "PORT": str(port),
        "NODE_ENV": "test",
        "DB_PATH": str(Path(temp_dir) / "pets.db")
    })
    
    for key in ("TURSO_DATABASE_URL", "TURSO_URL", "TURSO_AUTH_TOKEN", "TURSO_API_TOKEN"):
        env.pop(key, None)

    server = subprocess.Popen(
        [node, "server.js"],
        cwd=app_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8"
    )

    # รอ server พร้อม
    deadline = time.monotonic() + 30
    server_ready = False
    while time.monotonic() < deadline:
        if server.poll() is not None:
            stdout, _ = server.communicate()
            raise RuntimeError(f"App server stopped during startup:\n{stdout}")
        try:
            res = _api_request(f"{base_url}/api/pets")
            if res.get("success"):
                server_ready = True
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not server_ready:
        server.kill()
        stdout, _ = server.communicate()
        raise RuntimeError(f"App server timeout after 30s:\n{stdout}")

    yield base_url

    # Cleanup
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def browser(app_url):
    _clear_pets(app_url)
    driver = webdriver.Chrome()
    driver.set_window_size(1440, 1200)
    try:
        driver.get(app_url)
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        wait.until(EC.visibility_of_element_located((By.ID, "pet-form")))
        wait.until(EC.text_to_be_present_in_element((By.ID, "summary-total-pets"), "0"))
        yield driver
    finally:
        time.sleep(1.5)  # หน่วงเวลา 1.5 วินาทีก่อนปิดเบราว์เซอร์เพื่อให้สังเกตผลลัพธ์ทัน
        driver.quit()

# --- HELPER FUNCTIONS ---

def _type_slowly(element, text: str, delay: float = 0.05):
    """ฟังก์ชันช่วยพิมพ์ข้อความทีละตัวอักษรเพื่อชะลอความเร็ว"""
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(delay)

def _fill_pet_form(driver: webdriver.Chrome, name: str) -> None:
    _type_slowly(driver.find_element(By.ID, "pet-name"), name)
    time.sleep(SLOW_STEP_DELAY)
    
    Select(driver.find_element(By.ID, "pet-type")).select_by_value("dog")
    time.sleep(SLOW_STEP_DELAY)
    
    _type_slowly(driver.find_element(By.ID, "pet-breed"), "Golden Retriever")
    time.sleep(SLOW_STEP_DELAY)
    
    _type_slowly(driver.find_element(By.ID, "pet-weight"), "20")
    time.sleep(SLOW_STEP_DELAY)
    
    Select(driver.find_element(By.ID, "pet-activity")).select_by_value("medium")
    time.sleep(SLOW_STEP_DELAY)

# ==============================================================================
# TEST CASES
# ==============================================================================

def test_ST_DATA_01_บันทึกข้อมูลสำเร็จ(browser):
    _fill_pet_form(browser, "Lucky")
    
    # กดปุ่มบันทึก
    browser.find_element(By.ID, "btn-submit").click()
    time.sleep(SLOW_STEP_DELAY)

    # ตรวจสอบว่ามีข้อมูลเพิ่มในตาราง
    wait = WebDriverWait(browser, WAIT_TIMEOUT)
    pet_row_xpath = "//tbody[@id='pets-table-body']/tr[td[1][normalize-space()='Lucky']]"
    wait.until(EC.visibility_of_element_located((By.XPATH, pet_row_xpath)))
    wait.until(EC.text_to_be_present_in_element((By.ID, "summary-total-pets"), "1"))

    rows = browser.find_elements(*PET_TABLE_ROWS)
    assert len(rows) == 1
    assert "Lucky" in rows[0].text


def test_ST_DATA_02_บันทึกข้อมูลไม่สำเร็จ(browser):
    _fill_pet_form(browser, "Lucky-Offline")
    
    # จำลองสถานการณ์ Offline ผ่าน CDP
    browser.execute_cdp_cmd("Network.enable", {})
    offline = {"offline": True, "latency": 0, "downloadThroughput": 0, "uploadThroughput": 0}
    browser.execute_cdp_cmd("Network.emulateNetworkConditions", offline)

    try:
        browser.find_element(By.ID, "btn-submit").click()
        time.sleep(SLOW_STEP_DELAY)

        wait = WebDriverWait(browser, WAIT_TIMEOUT)
        wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".swal2-popup"), "ไม่สามารถบันทึกข้อมูลได้"))
        wait.until(EC.text_to_be_present_in_element((By.ID, "summary-total-pets"), "0"))
        assert len(browser.find_elements(*PET_TABLE_ROWS)) == 0
    finally:
        # คืนค่าสถานะเครือข่ายกลับเป็น Online
        browser.execute_cdp_cmd("Network.emulateNetworkConditions", {**offline, "offline": False, "downloadThroughput": -1, "uploadThroughput": -1})
        browser.execute_cdp_cmd("Network.disable", {})

    time.sleep(SLOW_STEP_DELAY)
    browser.refresh()
    WebDriverWait(browser, WAIT_TIMEOUT).until(EC.text_to_be_present_in_element((By.ID, "summary-total-pets"), "0"))
    assert len(browser.find_elements(*PET_TABLE_ROWS)) == 0