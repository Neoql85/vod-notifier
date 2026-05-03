import requests
from bs4 import BeautifulSoup
import schedule
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

PROVIDERS = {
    "HBO Max": 1,
    "Canal+": 20,
    "Canal+ (dodatkowe)": 5,
    "Amazon Prime": 8
}

WP_EMAIL = os.getenv("WP_EMAIL")
WP_PASSWORD = os.getenv("WP_PASSWORD")
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")

def get_new_movies(provider_id, from_date, until_date):
    url = f"https://www.filmweb.pl/api/v1/vod?type=film&vodProviderId={provider_id}&from={from_date}&until={until_date}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Błąd podczas pobierania filmów dla dostawcy {provider_id}: {e}")
    return []

def get_movie_info(film_id):
    url = f"https://www.filmweb.pl/api/v1/title/{film_id}/info"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Błąd podczas pobierania info o filmie {film_id}: {e}")
    return None

def get_movie_rating(film_id):
    url = f"https://www.filmweb.pl/api/v1/film/{film_id}/rating"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('rate', 0.0)
    except Exception as e:
        print(f"Błąd podczas pobierania oceny dla {film_id}: {e}")
    return 0.0

def is_horror_or_thriller(film_id, title, year):
    # Construct proper Filmweb URL
    formatted_title = urllib.parse.quote_plus(title)
    url = f"https://www.filmweb.pl/film/{formatted_title}-{year}-{film_id}"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tags = soup.find_all(attrs={'itemprop': 'genre'})
            genres = [t.text.strip().lower() for t in tags]
            if 'horror' in genres or 'thriller' in genres:
                return True
    except Exception as e:
        print(f"Błąd podczas sprawdzania gatunku dla {film_id}: {e}")
    return False

def check_movies_and_send_email():
    print(f"[{datetime.now()}] Rozpoczynam sprawdzanie nowych filmów...")
    
    until_date = datetime.now()
    from_date = until_date - timedelta(days=7)
    
    from_str = from_date.strftime("%Y-%m-%d")
    until_str = until_date.strftime("%Y-%m-%d")
    
    recommended_movies = []
    
    for provider_name, provider_id in PROVIDERS.items():
        print(f"Sprawdzam: {provider_name}")
        movies = get_new_movies(provider_id, from_str, until_str)
        if not movies:
            continue
            
        for item in movies:
            film_id = item.get('film')
            if not film_id:
                continue
                
            rating = get_movie_rating(film_id)
            if rating is None or rating <= 6.0:
                continue
            
            info = get_movie_info(film_id)
            if not info:
                continue
                
            title = info.get('title', 'Nieznany tytuł')
            year = info.get('year', '')
                
            if is_horror_or_thriller(film_id, title, year):
                movie_data = {
                    'title': title,
                    'rating': round(rating, 2),
                    'provider': provider_name,
                    'url': f"https://www.filmweb.pl/film/{urllib.parse.quote_plus(title)}-{year}-{film_id}"
                }
                recommended_movies.append(movie_data)
                print(f"Znaleziono: {title} ({rating}) na {provider_name}")
                
            time.sleep(0.5) # Zabezpieczenie przed zablokowaniem
            
    if recommended_movies:
        send_email(recommended_movies)
    else:
        print("Brak nowych horrorów/thrillerów spełniających kryteria.")

def send_email(movies):
    if not WP_EMAIL or not WP_PASSWORD or not GMAIL_EMAIL:
        print("Brak konfiguracji email. Ustaw WP_EMAIL, WP_PASSWORD i GMAIL_EMAIL w pliku .env")
        return
        
    from email.utils import formatdate
    
    msg = MIMEMultipart('alternative')
    msg['From'] = WP_EMAIL
    msg['To'] = GMAIL_EMAIL
    msg['Subject'] = "Nowości VOD: Twoje cotygodniowe zestawienie filmowe"
    msg['Date'] = formatdate(localtime=True)
    
    text = "Nowo dodane filmy (Ostatnie 7 dni):\n\n"
    html = "<html><body><h2>Nowo dodane filmy (Ostatnie 7 dni)</h2><ul>"
    
    for m in movies:
        text += f"- {m['title']} (Ocena: {m['rating']}) na {m['provider']}\nLink: {m['url']}\n\n"
        html += f"<li><b>{m['title']}</b> (Ocena: {m['rating']}) - {m['provider']} <br><a href='{m['url']}'>Link do strony filmu</a></li><br>"
        
    html += "</ul></body></html>"
    
    part1 = MIMEText(text, 'plain', 'utf-8')
    part2 = MIMEText(html, 'html', 'utf-8')
    
    msg.attach(part1)
    msg.attach(part2)
    
    try:
        server = smtplib.SMTP_SSL('smtp.wp.pl', 465)
        server.login(WP_EMAIL, WP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("E-mail został pomyślnie wysłany!")
    except Exception as e:
        print(f"Błąd podczas wysyłania e-maila: {e}")

if __name__ == "__main__":
    # Jeśli skrypt jest uruchamiany w środowisku GitHub Actions, wykonaj go raz i zakończ
    if os.getenv("GITHUB_ACTIONS") == "true":
        print("Uruchomienie w środowisku GitHub Actions. Wykonywanie skryptu jednorazowo...")
        check_movies_and_send_email()
    else:
        print("Program został uruchomiony lokalnie. E-maile będą wysyłane w każdy piątek o 16:00.")
        # Ustawienie harmonogramu
        schedule.every().friday.at("16:00").do(check_movies_and_send_email)
        
        # Opcjonalnie: odkomentuj poniższą linię, aby wymusić testowe wykonanie zaraz po starcie
        # check_movies_and_send_email()
        
        while True:
            schedule.run_pending()
            time.sleep(60)
