import json
import os
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

URL = 'https://www.mizrahi-tefahot.co.il/nifgashim/#nav-events-1'
CACHE_FILE = 'events_cache.json'

SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'levido08@gmail.com').strip()
IDO_APP_PASSWORD = os.getenv('IDO_APP_PASSWORD', '').strip()
RECEIVER_EMAIL = os.getenv('RECEIVER_EMAIL', 'levi0080@gmail.com').strip()

def send_email(updates_list, is_new=True):
    msg = MIMEMultipart()
    msg['Subject'] = 'עדכון חדש: אירועי מזרחי טפחות - שינוי סטטוס' if not is_new else 'עדכון חדש: אירוע מזרחי טפחות חדש!'
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    body = '<div dir="rtl" style="text-align: right; font-family: Arial, sans-serif;">'
    body += 'התגלו העדכונים הבאים באירועי מזרחי טפחות "נפגשים":<br><br>'

    for event in updates_list:
        body += f"<b>כותרת האירוע:</b> {event['title']}<br>"
        body += f"<b>מרצה:</b> {event['lecturer']}<br>"
        body += f"<b>תאריך ושעה:</b> {event['time']}<br>"
        body += f"<b>מיקום:</b> {event['location']}<br>"
        body += f"<b>סטטוס:</b> {event['status_text']}<br>"
        body += f"<b>לינק להרשמה:</b> <a href='{event['link']}'>{event['link']}</a><br><br>"
        body += '-' * 30 + '<br>'

    body += '</div>'

    msg.attach(MIMEText(body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, IDO_APP_PASSWORD)
            server.send_message(msg)
        print('המייל נשלח בהצלחה!')
    except Exception as e:
        print(f'שגיאה בשליחת המייל: {e}')

def get_events_list():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(URL, wait_until='networkidle')
        html_content = page.content()

        soup = BeautifulSoup(html_content, 'html.parser')
        
        event_cards = soup.select('a.eventCardLink')

        events = []
        for card in event_cards:
            link = card.get('href', '')
            if link.startswith('/'):
                link = 'https://www.mizrahi-tefahot.co.il' + link

            title_tag = card.find(class_='lectureTitle')
            lecturer_tag = card.find(class_='lecturerName')
            location_tag = card.find(class_='location')
            time_tag = card.find(class_='time')
            status_tag = card.find(class_='fullOrLastPlacesTitle')

            title = title_tag.get_text(strip=True) if title_tag else 'ללא כותרת'
            lecturer = lecturer_tag.get_text(strip=True) if lecturer_tag else ''
            
            location = location_tag.get_text(strip=True) if location_tag else ''
            time_str = time_tag.get_text(strip=True) if time_tag else ''

            status_text = status_tag.get_text(strip=True) if status_tag else 'פתוח להרשמה'
            is_closed = 'הסתיים' in status_text or 'מלאה' in status_text

            events.append({
                'title': title,
                'lecturer': lecturer,
                'location': location,
                'time': time_str,
                'link': link,
                'status_text': status_text,
                'is_closed': is_closed
            })

        browser.close()
    return events


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_cache(events):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=4)


def commit_cache_to_github():
    try:
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", CACHE_FILE], check=True)
        
        status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        if status_result.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Update mizrahi events cache automatically [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("הקאש עודכן והועלה בהצלחה לגיטהאב!")
        else:
            print("אין שינויים בקאש לעדכון.")
    except Exception as e:
        print(f"שגיאה בעדכון הקאש בגיטהאב: {e}")


def main():
    print('Checking for Mizrahi Tefahot events updates...')
    current_events = get_events_list()
    cached_events = load_cache()

    cached_dict = {e['link']: e for e in cached_events}

    new_events = []
    status_changed_events = []

    for event in current_events:
        link = event['link']
        
        if link not in cached_dict:
            if not event['is_closed']:
                new_events.append(event)
        else:
            old_closed_status = cached_dict[link].get('is_closed', False)
            current_closed_status = event['is_closed']
            
            if not old_closed_status and current_closed_status:
                print(f"שינוי סטטוס באירוע '{event['title']}': נסגר להרשמה.")
                status_changed_events.append(event)

    if new_events:
        print(f'>>> Found {len(new_events)} new events! <<<')
        send_email(new_events, is_new=True)

    if status_changed_events:
        print(f'>>> Found {len(status_changed_events)} events that recently closed! <<<')

    if not new_events and not status_changed_events:
        print('No New Events or Status Changes Found.')

    save_cache(current_events)
    commit_cache_to_github()


if __name__ == '__main__':
    main()
