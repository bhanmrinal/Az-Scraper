import datetime
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from flask import Flask, jsonify, request
from pymongo import MongoClient

# Initialize Flask app
app = Flask(__name__)

# MongoDB setup
client = MongoClient('mongodb://127.0.0.1:27017/')
db = client['aljazeera']  # Database name
news_collection = db['news']          # Collection for news
courses_collection = db['courses']      # Collection for courses
trainers_collection = db['trainers']    # Collection for trainers

# Clean text helper
def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

class NewsScraper:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.news_data = []
        
        # Set up session headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_soup(self, url):
        """Get BeautifulSoup object for a given URL"""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            print(f"Error fetching {url}: {str(e)}")
            return None

    def extract_news_item(self, news_element):
        """Extract information from a news item element"""
        try:
            news = {}
            
            # Extract title and URL
            title_elem = news_element.find('h5', class_='event-title')
            if title_elem and title_elem.find('a'):
                news['title'] = title_elem.find('a').text.strip()
                news['article_url'] = self.base_url + title_elem.find('a')['href']
            
            # Extract image URL
            img_elem = news_element.find('img', class_='img-responsive')
            if img_elem:
                img_src = img_elem.get('src', '')
                news['image_url'] = self.base_url + img_src if not img_src.startswith('http') else img_src

            # Extract date if available
            date_elem = news_element.find('span', class_='date-display-single')
            if date_elem:
                news['date'] = date_elem.text.strip()

            # Get full article details
            if news.get('article_url'):
                article_details = self.get_article_details(news['article_url'])
                news.update(article_details)

            return news
        except Exception as e:
            print(f"Error extracting news item: {str(e)}")
            return None

    def get_article_details(self, article_url):
        """Scrape detailed information from the article page"""
        print(f"Fetching details from: {article_url}")
        soup = self.get_soup(article_url)
        if not soup:
            return {}
        
        details = {}
        try:
            # Extract article content from node__content
            content_div = soup.find('div', class_='node__content')
            if content_div:
                # Get all paragraphs and their text
                paragraphs = content_div.find_all('p')
                
                # Join remaining paragraphs for full content (description)
                content = '\n\n'.join([p.text.strip() for p in paragraphs if p.text.strip()])
                details['description'] = content

            # Try to extract date if available
            date_elem = soup.find('span', class_='date-display-single')
            if date_elem:
                details['article_date'] = date_elem.text.strip()
                
            # Try to get author if available
            author_elem = soup.find('div', class_='field--name-field-author')
            if author_elem:
                details['author'] = author_elem.text.strip()
                
            # Get any tags/categories
            tags_container = soup.find('div', class_='field--name-field-tags')
            if tags_container:
                tags = tags_container.find_all('a')
                details['tags'] = [tag.text.strip() for tag in tags]

        except Exception as e:
            print(f"Error extracting article details from {article_url}: {str(e)}")
        
        return details

    def check_load_more_button(self, soup):
        """Check if there's a 'Load More' button on the page"""
        pager = soup.find('ul', class_='js-pager__items')
        if pager:
            load_more = pager.find('a', rel='next')
            return bool(load_more)
        return False

    def get_next_page_url(self, soup):
        """Extract the next page URL from the Load More button"""
        pager = soup.find('ul', class_='js-pager__items')
        if pager:
            load_more = pager.find('a', rel='next')
            if load_more and 'href' in load_more.attrs:
                return load_more['href']
        return None

    def scrape_page(self, url):
        """Scrape a single page of news items"""
        print(f"\nScraping page: {url}")
        
        soup = self.get_soup(url)
        if not soup:
            return False, None

        # Handle both top stories and regular news
        news_containers = soup.find_all('div', class_=['event-card top-story', 'event-card more-news'])
        
        for container in news_containers:
            news_info = self.extract_news_item(container)
            if news_info:
                self.news_data.append(news_info)
                time.sleep(1)  # Polite delay between requests

        # Check for next page
        has_more = self.check_load_more_button(soup)
        next_url = self.get_next_page_url(soup) if has_more else None
        
        return has_more, next_url

    def scrape_all_news(self, max_pages=None):
        """Scrape all news pages up to max_pages"""
        current_url = f"{self.base_url}/en/news"
        page_count = 0
        
        while current_url:
            if max_pages is not None and page_count >= max_pages:
                break
                
            has_more, next_url = self.scrape_page(current_url)
            
            if not has_more or not next_url:
                break
                
            if next_url.startswith('?'):
                current_url = f"{self.base_url}/en/news{next_url}"
            else:
                current_url = f"{self.base_url}{next_url}"
                
            page_count += 1
            time.sleep(2)  
        
        print(f"\nCompleted scraping {page_count + 1} pages")
        print(f"Total articles collected: {len(self.news_data)}")

    def save_to_json(self, filename='news_data.json'):
        """Save scraped data to JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'scrape_date': datetime.now().isoformat(),
                    'total_articles': len(self.news_data),
                    'articles': self.news_data
                }, f, ensure_ascii=False, indent=2)
            print(f"\nSuccessfully saved {len(self.news_data)} articles to {filename}")
        except Exception as e:
            print(f"Error saving to JSON: {str(e)}")

    def save_to_mongo(self):
        """Save scraped data to MongoDB"""
        try:
            if self.news_data:
                news_collection.insert_many(self.news_data)
                print(f"\nSuccessfully inserted {len(self.news_data)} articles into MongoDB")
            else:
                print("No data to save to MongoDB")
        except Exception as e:
            print(f"Error saving to MongoDB: {str(e)}")

def scrape_news():
    base_url = "https://institute.aljazeera.net"
    scraper = NewsScraper(base_url)
    
    try:
        # max_pages = request.args.get('max_pages', default=4, type=int)
        scraper.scrape_all_news(max_pages=5)
        scraper.save_to_mongo()  
        return jsonify({"message": "News scraping completed successfully", "articles_collected": len(scraper.news_data)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/news', methods=['GET'])
def get_news():
    try:
        news = list(news_collection.find({}, {'_id': 0}))  # Exclude MongoDB's default _id field
        return jsonify(news), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

### Course Scraper ###
def scrape_course_details(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        details = {
            'Title': clean_text(soup.select_one('h2.course-subtitle').get_text()),
            'Trainer': clean_text(soup.select_one('.course-details-s1 p + a').get_text()),
            'Time': clean_text(soup.select('.course-details-s1 p')[3].get_text().replace('Category:', '').strip()),
            'Price': clean_text(soup.select_one('.price .discount-data-bk1').get_text()),
            'Prerequisites': clean_text(soup.find('p', class_='sub-heading', string='Prerequisites').find_next('p').get_text()),
            'Description': clean_text(soup.find('p', class_='sub-heading', string='Course Description').find_next('p').get_text()),
            'Objectives': clean_text(soup.find('p', class_='sub-heading', string='Course Objective').find_next('p').get_text()),
            'Outline': clean_text(soup.find('p', class_='sub-heading', string='Course Outline').find_next('p').get_text()),
            'Benefits': clean_text(soup.find('p', class_='sub-heading', string='Course Benefits').find_next('p').get_text())
        }
        return details

    except Exception as e:
        print(f"Error scraping course details from {url}: {str(e)}")
        return None

def scrape_all_courses(base_url):
    courses = []
    page = 0

    while True:
        page_url = f"{base_url}?page={page}"
        print(f"Scraping courses page: {page_url}")
        
        response = requests.get(page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        course_cards = soup.select('#course-filter-results .course-card')
        if not course_cards:
            print("No more course cards found. Stopping.")
            break

        for card in course_cards:
            link = card.find('a')['href']
            course_url = 'https://institute.aljazeera.net' + link
            print(f"Scraping course: {course_url}")

            course_info = {
                'Title': clean_text(card.select_one('.course-title').text),
                'Date and Time': clean_text(card.select_one('.course-date').text),
                'Description': clean_text(card.select_one('.card-desc').text),
                'Image URL': card.select_one('.course-img-top')['src'],
                'Course URL': course_url
            }

            detailed_info = scrape_course_details(course_url)
            if detailed_info:
                course_info.update(detailed_info)

            courses.append(course_info)
            time.sleep(1)

        page += 1

    return courses

### Trainer Scraper ###
class TrainerScraper:
    def __init__(self, base_url="https://institute.aljazeera.net"):
        self.base_url = base_url
        self.session = requests.Session()
        self.trainers = []

    def get_soup(self, url):
        response = self.session.get(url)
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
        return None

    def get_total_pages(self, soup):
        pagination = soup.find('ul', class_='pagination')
        if pagination:
            links = pagination.find_all('li')
            page_no = []
            for link in links:
                if link.find('a'):
                    try:
                        num = int(link.find('a').text.strip())
                        page_no.append(num)
                    except ValueError:
                        continue
            
            if page_no:
                return max(page_no)

        return 3  # Default to 3 pages since we know they exist

    def extract_trainer_info(self, trainer_box):
        trainer = {}
        name_elem = trainer_box.find('h4', class_='header')
        trainer['name'] = name_elem.text.strip() if name_elem else None
        
        org_elem = trainer_box.find('h5', class_='header')
        trainer['organization'] = org_elem.text.strip() if org_elem else None
        
        link_elem = trainer_box.find('a')
        if link_elem and link_elem.get('href'):
            trainer['profile_url'] = self.base_url + link_elem.get('href')
        
        img_elem = trainer_box.find('img')
        if img_elem:
            img_src = img_elem.get('src')
            trainer['image_url'] = img_src if img_src.startswith('http') else self.base_url + img_src

        return trainer

    def get_trainer_details(self, profile_url):
        soup = self.get_soup(profile_url)
        if not soup:
            return {}
        
        details = {}
        trainer_details = soup.find('div', id='trainer-details')
        if trainer_details:
            trainer_info = trainer_details.find('div', class_='trainer-info')
            if trainer_info:
                paragraphs = trainer_info.find_all('p')
                if len(paragraphs) > 1:
                    details['specialization'] = paragraphs[-1].text.strip()
            
            bio_heading = trainer_details.find('p', class_='sub-heading', string=re.compile(r'Bio', re.IGNORECASE))
            if bio_heading:
                bio = bio_heading.find_next('p')
                if bio:
                    details['biography'] = bio.text.strip()

            exp_heading = trainer_details.find('p', class_='sub-heading', string=re.compile(r'Experience', re.IGNORECASE))
            if exp_heading:
                exp = exp_heading.find_next('p')
                if exp:
                    exp_text = exp.text.strip()
                    exp_points = [point.strip() for point in re.split(r'\d+\.', exp_text) if point.strip()]
                    details['experience'] = exp_points

            edu_heading = trainer_details.find('p', class_='sub-heading', string=re.compile(r'Education', re.IGNORECASE))
            if edu_heading:
                edu = edu_heading.find_next('p')
                if edu:
                    details['education'] = edu.text.strip()

        return details

    def scrape_trainers(self, max_pages=None):
        first_page_url = f"{self.base_url}/en/trainers"
        first_page_soup = self.get_soup(first_page_url)
        
        if not first_page_soup:
            print("Failed to access the first page")
            return
        
        total_pages = self.get_total_pages(first_page_soup)
        if max_pages:
            total_pages = min(total_pages, max_pages)
        
        print(f"Found {total_pages} pages to scrape")
        
        for page in range(total_pages):
            page_num = page + 1
            url = f"{self.base_url}/en/trainers?page={page_num}"
            print(f"Scraping page {page_num} of {total_pages}")
            
            soup = self.get_soup(url)
            if not soup:
                print(f"Failed to access page {page_num}")
                continue
            
            trainer_boxes = soup.find_all('div', class_='trainer-box')
            
            for box in trainer_boxes:
                trainer_info = self.extract_trainer_info(box)
                
                if trainer_info.get('profile_url'):
                    print(f"Scraping details for {trainer_info['name']}")
                    details = self.get_trainer_details(trainer_info['profile_url'])
                    trainer_info.update(details)
                
                self.trainers.append(trainer_info)
                time.sleep(1) 
            
            print(f"Completed page {page_num}")

    def save_to_mongo(self):
        trainers_collection.delete_many({})  
        trainers_collection.insert_many(self.trainers)
        print(f"Saved {len(self.trainers)} trainers to MongoDB.")

### Flask Endpoints ###
@app.route('/refresh', methods=['POST'])
def refresh_data():
    print("Starting refresh process")
    
    # Clear previous collections
    news_collection.delete_many({})
    courses_collection.delete_many({})
    trainers_collection.delete_many({})

    # Scrape news
    news_data = scrape_news()
    news_collection.insert_many(news_data)

    # Scrape courses
    courses_data = scrape_all_courses("https://institute.aljazeera.net/en/courses")
    courses_collection.insert_many(courses_data)

    # Scrape trainers
    trainer_scraper = TrainerScraper()
    trainer_scraper.scrape_trainers(max_pages=3)
    trainer_scraper.save_to_mongo()

    return jsonify({'message': 'Data refreshed successfully'}), 200

@app.route('/news', methods=['GET'])
def fetch_news():
    news = list(news_collection.find({}, {'_id': 0}))
    return jsonify(news)

@app.route('/courses', methods=['GET'])
def get_courses():
    courses = list(courses_collection.find({}, {'_id': 0}))
    return jsonify(courses)

@app.route('/trainers', methods=['GET'])
def get_trainers():
    trainers = list(trainers_collection.find({}, {'_id': 0}))
    return jsonify(trainers)


if __name__ == '__main__':
    app.run(debug=True)