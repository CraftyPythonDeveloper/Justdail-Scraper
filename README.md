# Justdial Web Scraper

**⚠️ Disclaimer: Educational Purpose Only**
This scraper is created solely for educational purposes to demonstrate web automation techniques. Use it at your own risk. The creator is not responsible for any misuse or violation of terms of service. Please respect websites' terms of service and robots.txt policies.

## Overview
This Python-based web scraper automates the extraction of business information from Justdial listings. It uses Selenium WebDriver to navigate pages and extract details like business names, ratings, addresses, and contact information.

## Features
- Multi-URL support through configuration file
- Human-like browsing behavior
- Automatic handling of login popups
- Smooth scrolling and dynamic content loading
- Detailed logging
- Excel output with timestamps
- Error handling and recovery

## Requirements
```
undetected-chromedriver
pandas
openpyxl
```

## Installation
1. Clone the repository:
```bash
git clone https://github.com/CraftyPythonDeveloper/Justdail-Scraper.git
cd Justdail-Scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### 1. Configure Input URLs
Create or edit `justdail_urls.txt` with target URLs (one per line):
```
https://www.justdial.com/Mumbai/Restaurants
https://www.justdial.com/Delhi/Hotels
```

### 2. Run the Scraper
```bash
python justdail_scraper.py
```

### 3. Output
- Results are saved in Excel files named `justdial_results_YYYYMMDD_HHMMSS.xlsx`
- Logs are written to `scraper.log`

## Output Format
The scraper collects the following information for each business:
- URL source
- Product index
- Product title
- Business name
- Rating
- Address
- Phone number
- Timestamp

## Technical Details

### Browser Configuration
- Uses Chrome WebDriver
- Configurable delays for human-like behavior
- Handles dynamic loading and popups

### Error Handling
- Validates input URLs
- Logs errors without stopping execution
- Handles network issues and stale elements
- Recovers from popup interruptions

### Rate Limiting
- Random delays between actions
- Smooth scrolling behavior
- Natural interaction patterns

## Limitations
- May break if Justdial changes their HTML structure
- No handling of CAPTCHAs
- Limited to public information
- Depends on stable internet connection

## Contributing
Feel free to open issues or submit pull requests to improve the scraper.

## Legal Notice
This project is for educational purposes only. Web scraping may be against some websites' terms of service. Always check and respect:
- The website's robots.txt
- Terms of Service
- Rate limiting policies
- Data usage rights

The developer assumes no responsibility for any misuse of this tool or violation of Justdial's terms of service.

## License
This project is meant for educational purposes. Please use responsibly and in accordance with applicable laws and website policies.
