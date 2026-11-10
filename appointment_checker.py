import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

URL = "https://www.etermin.net/qtermin-stadtheilbronn-abh"
STATE_FILE = Path(__file__).with_name("appointment_state.json")
TZ = ZoneInfo("Europe/Berlin")
SLOT_PATTERN = re.compile(r"\b([01]\d|2[0-3]):[0-5]\d\s*-\s*([01]\d|2[0-3]):[0-5]\d\b")


def get_visible_slots(page):
    # Read time ranges in the appointment selection section, not the whole page.
    text = page.locator("body").inner_text()
    return sorted(set(match.group(0) for match in SLOT_PATTERN.finditer(text)))


def scan():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="de-DE", timezone_id="Europe/Berlin")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            main = page.get_by_text("Aufenthaltserlaubnis", exact=True).filter(visible=True).first
            main.wait_for(state="visible", timeout=30000)
            main.click()
            category = page.locator('li[id="144512"]')
            category.wait_for(state="visible", timeout=15000)
            counter = page.locator('[id="capvalue144512"]')
            if counter.inner_text().strip() == "0":
                category.locator(".counterPlus").click()
            if counter.inner_text().strip() != "1":
                raise RuntimeError("Hizmet seçimi doğrulanamadı")
            page.get_by_text("Weiter zur Terminauswahl", exact=True).click()
            page.locator(".ui-datepicker-month").wait_for(state="visible", timeout=20000)
            today = datetime.now(TZ).date()
            results = []
            # Check the displayed month and navigate backward only when the UI permits.
            visited = set()
            for _ in range(12):
                month = int(page.locator(".ui-datepicker-month").input_value()) + 1
                year = int(page.locator(".ui-datepicker-year").inner_text())
                if (year, month) in visited:
                    break
                visited.add((year, month))
                day_numbers = sorted({int(x.get_attribute("data-date")) for x in page.locator('a.ui-state-default[data-date]:visible').all()})
                for number in day_numbers:
                    appointment_day = date(year, month, number)
                    if appointment_day < today:
                        continue
                    page.locator(f'a.ui-state-default[data-date="{number}"]:visible').click()
                    # Wait briefly for the selected-day content to update.
                    page.wait_for_timeout(450)
                    for slot in get_visible_slots(page):
                        results.append((appointment_day.isoformat(), slot.split("-")[0].strip()))
                prev = page.locator(".ui-datepicker-prev")
                if prev.count() == 0 or not prev.is_visible() or "ui-state-disabled" in (prev.get_attribute("class") or ""):
                    break
                previous_month = (year, month)
                prev.click()
                try:
                    page.wait_for_function(
                        "([y, m]) => {const e=document.querySelector('.ui-datepicker-month'); const yr=document.querySelector('.ui-datepicker-year'); return e && yr && (Number(e.value)+1 !== m || Number(yr.textContent) !== y)}",
                        arg=[year, month], timeout=8000,
                    )
                except Exception:
                    break
            return sorted(set(results))
        finally:
            browser.close()


def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID .env içinde eksik")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram mesajı kabul etmedi")


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    slots = scan()
    if not slots:
        print("Doğrulanabilir saat bulunamadı; kayıt değiştirilmedi.")
        return
    earliest = slots[0]
    print(f"En erken görünen saat: {earliest[0]} {earliest[1]}")
    previous = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else None
    current_set = set(slots)
    if previous is None:
        print("İlk kontrol: başlangıç durumu kaydediliyor, mesaj gönderilmiyor.")
    else:
        old_slots = {tuple(x) for x in previous.get("slots", [])}
        old_earliest = tuple(previous["earliest"])
        if earliest < old_earliest and earliest not in old_slots:
            day = date.fromisoformat(earliest[0])
            days = (day - datetime.now(TZ).date()).days
            message = (
                "🔔 Heilbronn ABH — Daha erken randevu!\n"
                f"📅 {day:%d.%m.%Y}\n"
                f"🕒 {earliest[1]}\n"
                f"⏳ {days} gün sonra\n"
                "Hizmet: Verlängerung Aufenthaltserlaubnis\n"
                f"{URL}"
            )
            send_telegram(message)
            print("Telegram bildirimi gönderildi.")
        else:
            print("Daha erken yeni randevu yok. Bildirim gönderilmedi.")
    # Save only after a successful check and any required notification.
    STATE_FILE.write_text(json.dumps({"earliest": list(earliest), "slots": [list(x) for x in sorted(current_set)]}, indent=2))


if __name__ == "__main__":
    main()
