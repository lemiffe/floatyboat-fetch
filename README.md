# FloatyBoat Fetcher & Crawler

## Requirements

- python3 (with pip3)

## Installation (for local development)

- pip3 install -r requirements.txt
- Fill in config.ini values (see config.ini.dist for info, you will need to open a few accounts!)
- Get your Firebase service account JSON and place it in the root directory (you can specify a name in config.ini)

## Installation (alternative: in a docker container)

- ./start-docker.sh
- Access locally at port 1337 (proxied to the container's 5000 port)

## Running (locally for development purposes)

- python3 main.py

## Endpoints

- This section is under construction (see main.py for more info for now)

## Deploying (using dokku)

- git push dokku master

## Dokku set up

**Set up Dokku + remote:**
- Make sure you have an initialised git repository in the project's root
- git remote add dokku dokku@your.ip.address:floatyboat
- SSH into your server
- wget https://raw.githubusercontent.com/dokku/dokku/v0.7.2/bootstrap.sh
- sudo DOKKU_TAG=v0.7.2 bash bootstrap.sh
- Go to your server's IP address and follow the installer

**Set up required files (on server):**
- config.ini and floaty.json should exist on the server, we can auto-mount during deploy with dokku:
- dokku storage:mount floatyboat /home/config.ini:/app/config.ini (make sure config.ini is on your dest. server)
- dokku storage:mount floatyboat /home/floaty.json:/app/floaty.json (make sure config.ini is on your dest. server)

**Set up the domain (on the server):**
- dokku domains floatyboat
- dokku domains:add floatyboat api.yourdomain.com
- dokku config:set boatyboat DOKKU_NGINX_PORT=80

**Set up the ports:**
- dokku proxy:ports floatyboat (see list of ports, see the port of your container)
- dokku proxy:ports-add floatyboat http:1337:5000 (host 1337 will map to your container now)
- dokku proxy:ports-add floatyboat https:1337:5000 (host 1337 will map to your container now)
- If adding https fails, first set up letsencrypt (see boatyboat setup instructions, use api.yourapp.com)

**Frontend setup:**
- See "boatyboat" repository README for instructions (including setting up the domain and letsencrypt)

## Sample Record

```
glassDoorID: {
    boat_status: "floating", <-- (floating|rising|falling, sailing|lifting|leaking, submerged|surfacing|sinking, sunk, unknown)
    record_status: "complete", <-- Depending on what we got, 'complete' if FC/GD/sentiment, else 'incomplete'. Min = Glassdoor
    last_update: UTC timestamp, <-- Calculated when storing + updating record
    name: "Google", <-- Calculated when storing record, just lower-case
    valuation_4_week_avg_score: 93.1249812 <-- Calculated very create/update
    <status>: "current|update required", <-- Not in DB... status filled in by the search endpoint

    //--->  Up to 12 data points per company (for 3 months, 1 per week)
    //---> Will contain twitter sentiment change, news sentiment change, klout score change, glassdoor change, etc.
    valuations: {
        UTC timestamp: {
            "gd_number_of_ratings": 68,
            "gd_overall_rating": "4.4",
            "gd_culture_and_values_rating": "4.5",
            "gd_senior_leadership_rating": "4.3",
            "gd_compensation_and_benefits_rating": "4.2",
            "gd_career_opportunities_rating": "4.5",
            "gd_work_life_balance_rating": "3.9",
            "gd_ceo_pct_approval": 94,
            "fc_traffic_global_rank": 1, <-- Optional (if FC)
            "kl_score": 97.08773873880774, <-- Optional (if KL)
            "social_sentiment": 0.9, <-- Optional (if BING/Twitter)
            "valuation_total_score": 95.8314, <-- Calculated when saving valuation (create/update)
            "stock_lo": 779.21 <-- Optional, only if we found a stock with that name
        },...
    }

    "gd_id": 683914,
    "gd_name_real": "Google"
    "gd_square_logo": "https://media.glassdoor.com/sqll/683910/nomnom-squarelogo-1436172612662.png",
    "gd_website": "www.google.com", <-- Can be None
    "gd_industry": "Computer Hardware & Software", <-- Can be None
    "gd_sector_name": "Information Technology", <-- Can be None

    "gd_ceo": { <-- Can be None/null
        "name": "Steven Bowen",
        "title": "Co-Founder & CEO",
        "numberOfRatings": 2,
        "pctApprove": 98,
        "pctDisapprove": 2,
        "image": {
          "src": "https://media.glassdoor.com/people/sqll/683910/nomnom-bowen.png",
          "height": 200,
          "width": 200
        }
    }

    "fc_name_full": "Google Inc." <-- Optional
    "fc_language" : "en", <-- Optional
    "fc_aprox_employees" : 50000, <-- Optional
    "fc_founded" : "1998", <-- Optional
    "fc_keywords" : [ "Advertising", "Apps", "Email", "Google", "Internet" ] <-- Optional
}
```

## To-Do

- Docker contaier should have cron to trigger update for top 200 companies on a weekly basis
- Twitter/News search and sentiment analysis (started)
- Improved stock market search (when multiple companies are found in the results)
- Aggregate from more sources (to make sure if one of them fails we can fall back on more data for analysis!)
- Glassdoor has no data for some companies - do not show "sunk" for those (check the gd_ variables)
- Partial searches (e.g. we might have 10 items with name "amazon" but gd_name_full "Amazon Centre", searching for the latter will give 0 results at the moment