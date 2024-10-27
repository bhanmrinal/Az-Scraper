import requests
from bs4 import BeautifulSoup
import json
import time
import re

# Clean text helper
def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

# Function to scrape course details from the individual course URL
def scrape_course_details(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        details = {}

        # Course Title
        title = soup.select_one('h2.course-subtitle')
        details['Title'] = clean_text(title.get_text()) if title else "N/A"

        # Trainer Info
        trainer = soup.select_one('.course-details-s1 p + a')
        details['Trainer'] = clean_text(trainer.get_text()) if trainer else "N/A"

        # Information Section (Dates, Time, Category)
        information_section = soup.select('.course-details-s1 p')
        if information_section:
            details['Time'] = clean_text(information_section[3].get_text().replace('Category:', '').strip())
        else:
            details['From'] = details['Time'] = details['Category'] = "N/A"

        # Price (if needed)
        price_section = soup.select_one('.price .discount-data-bk1')
        if price_section:
            details['Price'] = clean_text(price_section.get_text())
        else:
            details['Price'] = "N/A"

        # Prerequisites
        prerequisites = soup.find('p', class_='sub-heading', string='Prerequisites')
        if prerequisites:
            details['Prerequisites'] = clean_text(prerequisites.find_next('p').get_text())
        else:
            details['Prerequisites'] = "N/A"

        # Course Description
        course_description = soup.find('p', class_='sub-heading', string='Course Description')
        if course_description:
            details['Description'] = clean_text(course_description.find_next('p').get_text())
        else:
            details['Description'] = "N/A"

        # Course Objectives
        objectives = soup.find('p', class_='sub-heading', string='Course Objective')
        if objectives:
            details['Objectives'] = clean_text(objectives.find_next('p').get_text())
        else:
            details['Objectives'] = "N/A"

        # Course Outline
        outline = soup.find('p', class_='sub-heading', string='Course Outline')
        if outline:
            details['Outline'] = clean_text(outline.find_next('p').get_text())
        else:
            details['Outline'] = "N/A"

        # Course Benefits (if needed)
        benefits = soup.find('p', class_='sub-heading', string='Course Benefits')
        if benefits:
            details['Benefits'] = clean_text(benefits.find_next('p').get_text())
        else:
            details['Benefits'] = "N/A"

        return details

    except Exception as e:
        print(f"Error scraping course details from {url}: {str(e)}")
        return None

# Function to scrape all courses with dynamic pagination handling
def scrape_all_courses(base_url):
    courses = []
    page = 0  # Start from page 0

    while True:
        try:
            page_url = f"{base_url}?page={page}"
            print(f"Scraping page: {page_url}")
            
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            course_cards = soup.select('#course-filter-results .course-card')
            print(f"Found {len(course_cards)} course cards on page {page}")

            if not course_cards:
                print(f"No course cards found on page {page}. Stopping.")
                break

            for card in course_cards:
                link = card.find('a')
                if link and 'href' in link.attrs:
                    course_url = 'https://institute.aljazeera.net' + link['href']
                    print(f"Scraping course: {course_url}")

                    # Extract basic information from the course card
                    title = card.select_one('.course-title')
                    date_time = card.select_one('.course-date')
                    description = card.select_one('.card-desc')
                    image = card.select_one('.course-img-top')

                    course_info = {
                        'Title': clean_text(title.text) if title else "N/A",
                        'Date and Time': clean_text(date_time.text) if date_time else "N/A",
                        'Description': clean_text(description.text) if description else "N/A",
                        'Image URL': image['src'] if image and 'src' in image.attrs else "N/A",
                        'Course URL': course_url
                    }

                    # Redirect to the course detail page to scrape additional details
                    detailed_info = scrape_course_details(course_url)
                    if detailed_info:
                        course_info.update(detailed_info)

                    courses.append(course_info)
                    time.sleep(1)  

            # Check if there's a "next" page button or stop if not
            next_page = soup.select_one('.pagination-next-prev-s1')
            if next_page:
                page += 1
                print(f"Moving to the next page: {page}")
            else:
                print("No more pages found. Scraping finished.")
                break

        except Exception as e:
            print(f"Error scraping page {page}: {str(e)}. Stopping.")
            break

    return courses

# Main execution
base_url = "https://institute.aljazeera.net/en/courses"
all_courses = scrape_all_courses(base_url)

if all_courses:
    with open('1aljazeera_courses.json', 'w', encoding='utf-8') as file:
        json.dump(all_courses, file, ensure_ascii=False, indent=4)
    print(f"Scraped {len(all_courses)} courses and saved to aljazeera_courses.json")
else:
    print("No courses were scraped. Check the console output for error messages.")

if all_courses:
    print("\nSample Course Data:")
    print(json.dumps(all_courses[0], indent=4, ensure_ascii=False))
