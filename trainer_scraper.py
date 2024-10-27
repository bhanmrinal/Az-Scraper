import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import re

class TrainerScraper:
    def __init__(self, base_url="https://institute.aljazeera.net"):
        self.base_url = base_url
        self.session = requests.Session()
        self.trainers_data = []

    def get_soup(self, url):
        response = self.session.get(url)
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
        return None

    def get_total_pages(self, soup):
        """Extract total number of pages from pagination"""
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
            
            # If we couldn't find numbered pages, count the number of pagination items
            # excluding Previous/Next buttons
            non_nav_items = [li for li in links if not li.find('a', class_=['prev', 'next'])]
            if non_nav_items:
                return len(non_nav_items)
        
        try:
            test_url = f"{self.base_url}/en/trainers?page=3"
            test_response = self.session.get(test_url)
            if test_response.status_code == 200:
                test_soup = BeautifulSoup(test_response.text, 'html.parser')
                if test_soup.find('div', class_='trainer-box'):
                    return 3
        except:
            pass
        
        return 3  # Default to 3 pages since we know they exist

    def extract_trainer_info(self, trainer_box):
        """Extract basic information from trainer box on main page"""
        trainer = {}
        
        # Extract name
        name_elem = trainer_box.find('h4', class_='header')
        trainer['name'] = name_elem.text.strip() if name_elem else None
        
        # Extract organization
        org_elem = trainer_box.find('h5', class_='header')
        trainer['organization'] = org_elem.text.strip() if org_elem else None
        
        # Extract profile URL
        link_elem = trainer_box.find('a')
        if link_elem and link_elem.get('href'):
            trainer['profile_url'] = self.base_url + link_elem.get('href')
        
        # Extract image URL
        img_elem = trainer_box.find('img')
        if img_elem:
            img_src = img_elem.get('src')
            trainer['image_url'] = img_src if img_src.startswith('http') else self.base_url + img_src

        return trainer

    def get_trainer_details(self, profile_url):
        """Scrape detailed information from trainer's profile page"""
        soup = self.get_soup(profile_url)
        if not soup:
            return {}
        
        details = {}
        
        try:
            # Find the trainer-details div
            trainer_details = soup.find('div', id='trainer-details')
            if not trainer_details:
                return details

            # Extract information from trainer-info section
            trainer_info = trainer_details.find('div', class_='trainer-info')
            if trainer_info:
                # Get specialization/expertise (paragraph after organization)
                paragraphs = trainer_info.find_all('p')
                if len(paragraphs) > 1:
                    details['specialization'] = paragraphs[-1].text.strip()

            # Extract Bio
            bio_heading = trainer_details.find('p', class_='sub-heading', string=re.compile(r'Bio', re.IGNORECASE))
            if bio_heading:
                bio = bio_heading.find_next('p')
                if bio:
                    details['biography'] = bio.text.strip()

            # Extract Experience
            exp_heading = trainer_details.find('p', class_='sub-heading', string=re.compile(r'Experience', re.IGNORECASE))
            if exp_heading:
                exp = exp_heading.find_next('p')
                if exp:
                    exp_text = exp.text.strip()
                    exp_points = [point.strip() for point in re.split(r'\d+\.', exp_text) if point.strip()]
                    details['experience'] = exp_points

            # Extract Education
            edu_heading = trainer_details.find('p', class_='sub-heading', string=re.compile(r'Education', re.IGNORECASE))
            if edu_heading:
                edu = edu_heading.find_next('p')
                if edu:
                    details['education'] = edu.text.strip()

        except Exception as e:
            print(f"Error extracting details from {profile_url}: {str(e)}")
        
        return details

    def scrape_trainers(self, max_pages=None):
        """Scrape all trainers from main listing pages"""
        # Get first page to determine total pages
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
            page_num = page + 1  # URLs are 1-based
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
                
                self.trainers_data.append(trainer_info)
                time.sleep(1)  # Rate limiting
            
            print(f"Completed page {page_num}")

    def save_to_json(self, filename='trainers_data.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.trainers_data, f, ensure_ascii=False, indent=2)
        print(f"Data saved to {filename}")

def main():
    # Initialize scraper
    scraper = TrainerScraper()
    
    try:
        # Scrape 3 pages as specified
        scraper.scrape_trainers(max_pages=3)
        scraper.save_to_json()
        
        print("Scraping completed successfully!")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()