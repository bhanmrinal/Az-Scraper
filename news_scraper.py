import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime

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
            img_elem = news_element.find('img', class_='img-responsive')
            if img_elem:
                img_src = img_elem.get('src', '')
                news['image_url'] = self.base_url + img_src if img_src.startswith('/') else img_src

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
            
        print("Extracted details:", details)  # Debug print to see what was extracted
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

def main():
    base_url = "https://institute.aljazeera.net"
    scraper = NewsScraper(base_url)
    
    try:
        scraper.scrape_all_news(max_pages=4)  
        scraper.save_to_json()
        print("News scraping completed successfully")
        
    except Exception as e:
        print(f"An error occurred during scraping: {str(e)}")

if __name__ == "__main__":
    main()