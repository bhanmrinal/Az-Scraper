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
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

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
            
            # Extract title and URL from the event-body div
            event_body = news_element.find('div', class_='event-body')
            if event_body:
                title_elem = event_body.find('h5', class_='event-title')
                if title_elem and title_elem.find('a'):
                    news['title'] = title_elem.find('a').text.strip()
                    href = title_elem.find('a')['href']
                    news['article_url'] = self.base_url + href if href.startswith('/') else href
            
            # Extract image URL if available
            # img_elem = news_element.find('img', class_='img-responsive')
            # if img_elem:
            #     img_src = img_elem.get('src', '')
            #     news['image_url'] = self.base_url + img_src if img_src.startswith('/') else img_src

            # Extract date if available
            date_elem = news_element.find('span', class_='date-display-single')
            if date_elem:
                news['date'] = date_elem.text.strip()

            # Get full article details
            if news.get('article_url'):
                print(f"Fetching detailed content for: {news['title']}")
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
            # Extract main title (page header) - from the first h1 with page-header class
            page_headers = soup.find_all('h1', class_='page-header')
            if page_headers and len(page_headers) > 0:
                # Get the first h1 that has actual content
                for header in page_headers:
                    if header.find('span') and header.find('span').get_text(strip=True):
                        details['main_title'] = header.find('span').get_text(strip=True)
                        break

            # Extract subtitle
            subtitle = soup.find('h2', class_='course-subtitle')
            if subtitle and subtitle.find('span'):
                details['subtitle'] = subtitle.find('span').get_text(strip=True)
            else:
                print(f"Subtitle not found on page: {article_url}")

            # Extract main image
            main_image = soup.find('img', class_='img-responsive')
            if main_image:
                img_src = main_image.get('src', '')
                details['main_image'] = self.base_url + img_src if img_src.startswith('/') else img_src
            else:
                print(f"Image not found on page: {article_url}")

            # Extract the main content (description)
            # First, find the content div within the article
            article = soup.find('article', class_='news')
            if article:
                # Find the content row
                content_row = article.find('div', class_='content row')
                if content_row:
                    # Find the second column which contains the description
                    content_col = content_row.find_all('div', class_='col-xl-6 col-lg-8 col-md-12')
                    if len(content_col) > 1:  # Make sure we have at least 2 columns
                        content_div = content_col[1].find('div', class_='field--item')
                        if content_div:
                            paragraphs = content_div.find_all('p', class_='text-align-justify')
                            if paragraphs:
                                # Extract location/date from first paragraph
                                details['location_date'] = paragraphs[0].get_text(strip=True)
                                
                                # Join all paragraphs for full description
                                details['full_description'] = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)
                            else:
                                print(f"No content paragraphs found on page: {article_url}")
                        else:
                            print(f"Content field item not found on page: {article_url}")
                    else:
                        print(f"Content column not found on page: {article_url}")
                else:
                    print(f"Content row not found on page: {article_url}")
            else:
                print(f"Article not found on page: {article_url}")

            # Extract any additional metadata if available
            date_div = soup.find('div', class_=['field--name-field-date', 'date-display-single'])
            if date_div:
                details['publication_date'] = date_div.text.strip()

            author_div = soup.find('div', class_='field--name-field-author')
            if author_div:
                details['author'] = author_div.text.strip()

            tags_div = soup.find('div', class_='field--name-field-tags')
            if tags_div:
                tags = tags_div.find_all('a')
                details['categories'] = [tag.text.strip() for tag in tags]

        except Exception as e:
            print(f"Error extracting article details from {article_url}: {str(e)}")
            
        # print("Extracted details:", details)  # Debug print to see what was extracted
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
        return scraper.news_data  
        # print(jsonify({"message": "News scraping completed successfully", "articles_collected": len(scraper.news_data)}), 200)
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

        details = {}  # Initialize as empty dict

        # Safely get elements with error handling
        subtitle_elem = soup.select_one('h2.course-subtitle')
        if subtitle_elem:
            details['Title'] = clean_text(subtitle_elem.get_text())

        trainer_elem = soup.select_one('.course-details-s1 p + a')
        if trainer_elem:
            details['Trainer'] = clean_text(trainer_elem.get_text())

        time_elems = soup.select('.course-details-s1 p')
        if len(time_elems) > 3:
            details['Time'] = clean_text(time_elems[3].get_text().replace('Category:', '').strip())

        price_elem = soup.select_one('.price .discount-data-bk1')
        if price_elem:
            details['Price'] = clean_text(price_elem.get_text())

        # Function to safely get content after a heading
        def get_section_content(heading_text):
            try:
                heading = soup.find('p', class_='sub-heading', string=heading_text)
                if heading and heading.find_next('p'):
                    return clean_text(heading.find_next('p').get_text())
            except Exception:
                return None
            return None

        # Get various sections safely
        sections = {
            'Prerequisites': 'Prerequisites',
            'Description': 'Course Description',
            'Objectives': 'Course Objective',
            'Outline': 'Course Outline',
            'Benefits': 'Course Benefits'
        }

        for key, heading in sections.items():
            content = get_section_content(heading)
            if content:
                details[key] = content

        return details

    except Exception as e:
        print(f"Error scraping course details from {url}: {str(e)}")
        return {}  # Return empty dict instead of None

def scrape_all_courses(base_url):
    courses = []
    page = 0

    try:
        while True:
            page_url = f"{base_url}?page={page}"
            print(f"Scraping courses page: {page_url}")
            
            try:
                response = requests.get(page_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                print(f"Error fetching page {page_url}: {str(e)}")
                break

            course_cards = soup.select('#course-filter-results .course-card')
            if not course_cards:
                print("No more course cards found. Stopping.")
                break

            for card in course_cards:
                try:
                    course_info = {}  # Initialize as dict
                    
                    # Safely get link
                    link_elem = card.find('a')
                    if not link_elem or 'href' not in link_elem.attrs:
                        print("No link found for course card, skipping...")
                        continue
                        
                    link = link_elem['href']
                    course_url = 'https://institute.aljazeera.net' + link
                    print(f"Scraping course: {course_url}")

                    # Safely get basic course info
                    title_elem = card.select_one('.course-title')
                    if title_elem:
                        course_info['Title'] = clean_text(title_elem.text)
                    
                    date_elem = card.select_one('.course-date')
                    if date_elem:
                        course_info['Date and Time'] = clean_text(date_elem.text)
                    
                    desc_elem = card.select_one('.card-desc')
                    if desc_elem:
                        course_info['Description'] = clean_text(desc_elem.text)
                    
                    img_elem = card.select_one('.course-img-top')
                    if img_elem and 'src' in img_elem.attrs:
                        course_info['Image URL'] = img_elem['src']
                    
                    course_info['Course URL'] = course_url

                    # Get detailed info
                    detailed_info = scrape_course_details(course_url)
                    if detailed_info:  # Will always be a dict now, empty or populated
                        course_info.update(detailed_info)

                    if course_info:  # Only append if we have data
                        courses.append(course_info)
                        print(f"Successfully scraped course: {course_info.get('Title', 'Unknown')}")

                except Exception as e:
                    print(f"Error processing course card: {str(e)}")
                    continue

                time.sleep(1)  # Polite delay between requests

            page += 1
            time.sleep(2)  # Delay between pages

    except Exception as e:
        print(f"Error in scrape_all_courses: {str(e)}")
    
    print(f"Successfully scraped {len(courses)} courses")
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
    try:
        # Clear previous collections
        news_collection.delete_many({})
        courses_collection.delete_many({})
        trainers_collection.delete_many({})

        # Scrape and save news
        news_data = scrape_news()
        if news_data and isinstance(news_data, list):  # Verify we have a list of news
            # Verify each news item is a dictionary
            valid_news = [item for item in news_data if isinstance(item, dict)]
            if valid_news:
                news_collection.insert_many(valid_news)
                print(f"Inserted {len(valid_news)} news articles")

        # Scrape and save courses
        courses_data = scrape_all_courses("https://institute.aljazeera.net/en/courses")
        if courses_data and isinstance(courses_data, list):
            # Verify each course is a dictionary
            valid_courses = [course for course in courses_data if isinstance(course, dict)]
            if valid_courses:
                courses_collection.insert_many(valid_courses)
                print(f"Inserted {len(valid_courses)} courses")
        # Scrape and save trainers
        trainer_scraper = TrainerScraper()
        trainer_scraper.scrape_trainers(max_pages=3)
        if trainer_scraper.trainers:  # Only insert if we have data
            trainer_scraper.save_to_mongo()
            print(f"Inserted {len(trainer_scraper.trainers)} trainers")

        return jsonify({
            'message': 'Data refreshed successfully',
            'news_count': len(news_data) if news_data else 0,
            'courses_count': len(courses_data) if courses_data else 0,
            'trainers_count': len(trainer_scraper.trainers) if trainer_scraper.trainers else 0
        }), 200
    except Exception as e:
        print(f"Error in refresh_data: {str(e)}")
        return jsonify({'error': str(e)}), 500

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

@app.route('/counts', methods=['GET'])
def get_counts():
    try:
        return jsonify({
            'news_count': news_collection.count_documents({}),
            'courses_count': courses_collection.count_documents({}),
            'trainers_count': trainers_collection.count_documents({})
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(port=5001)