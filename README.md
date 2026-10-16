# Selenium Python tests

ชุดทดสอบ Python + Selenium + pytest นี้ตั้งค่าให้ VS Code ค้นพบ tests ใน Test Explorer โดยมี 2 กรณี:

- ST-DATA-01: บันทึกข้อมูลสัตว์เลี้ยงที่กรอกครบสำเร็จ
- ST-DATA-02: กรอกข้อมูลครบ แต่จำลองเครือข่ายขัดข้องระหว่างบันทึก และยืนยันว่าไม่มีข้อมูลถูกบันทึก

ชื่อ test ใน Test Explorer เป็นภาษาไทยเพื่อให้อ่านผลการทดสอบได้ง่าย

## สิ่งที่ต้องมี

- Python 3.10 หรือใหม่กว่า
- Node.js และ dependencies ของ `pet-hydro-feed-calculator` ติดตั้งแล้ว
- Google Chrome ที่ใช้งานได้
- `chromedriver.exe` ที่เข้ากันได้ (ถ้าไม่มี Selenium Manager จะพยายามจัดหาให้อัตโนมัติ)

## ติดตั้งและรันใน VS Code (Windows)

เปิดโฟลเดอร์ `seleniumpython` ใน VS Code แล้วรันคำสั่งใน Terminal:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

เลือก Python interpreter จาก `.venv` ใน VS Code จากนั้นเปิด **Testing** เพื่อรัน test รายตัว หรือรันทั้งชุดจาก Terminal:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pet.py -v
```

ชุดทดสอบจะเริ่ม Node.js server เองโดยใช้ฐานข้อมูลชั่วคราวและลบข้อมูลเมื่อจบ จึงไม่แก้ไขฐานข้อมูลจริง `pet-hydro-feed-calculator\data\pets.db` ตัวทดสอบค้นหาโฟลเดอร์แอปที่อยู่ข้าง `seleniumpython` ให้อัตโนมัติ หากวางแอปไว้ตำแหน่งอื่น ให้กำหนด environment variable ก่อนรัน:

```powershell
$env:PET_APP_DIR = "C:\path\to\pet-hydro-feed-calculator"
.\.venv\Scripts\python.exe -m pytest tests\test_pet.py -v
```

หากใช้ ChromeDriver ที่มากับโฟลเดอร์ `testselenium` ตัวทดสอบจะเลือกใช้อัตโนมัติ
