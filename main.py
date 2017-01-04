# region Imports

import sys, traceback, re, os, shutil, string
from collections import defaultdict
from decimal import *
from datetime import datetime, date, time, timedelta
import time as tyme
from collections import OrderedDict
import pyrebase
import configparser
import http.client
import urllib.request
import urllib.parse
import urllib.error
import base64
import ssl
import json
from flask import Flask, jsonify, request, abort, url_for, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask.ext.cors import CORS
from raven.contrib.flask import Sentry
import logging
from random import randint
import requests

# endregion

# region Constants

STATUS_UPDATE_REQUIRED = 'update required'
STATUS_FULL_UPDATE_REQUIRED = 'full update required'
STATUS_PARTIAL_UPDATE_REQUIRED = 'partial update required'
STATUS_SUCCESS = 'success'
STATUS_CURRENT = 'current'
STATUS_ERROR = 'error'
STATUS_NOT_FOUND = 'not found'
FAKE_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'

# endregion

# region Initialisation and Configuration

# Change directory to the location of this script
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

config = configparser.ConfigParser()
config.read('config.ini')

# Start app with CORS support and rate limiting
app = Flask(__name__, static_url_path='')
CORS(app)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    global_limits=["10000 per minute", "50 per second"],
)
sentry = Sentry(
    app,
    dsn=config['sentry']['dsn'],
    logging=True,
    level=logging.ERROR,
)

firebase_config = {
  "apiKey": config['firebase']['firebaseApiKey'],
  "authDomain": config['firebase']['firebaseAuthUrl'],
  "databaseURL": config['firebase']['firebaseDatabaseUrl'],
  "storageBucket": "",
  "serviceAccount": config['firebase']['firebaseServiceJson']
}

# Initialise Firebase
firebase = pyrebase.initialize_app(firebase_config)
firebase_auth = firebase.auth()
firebase_user = firebase_auth.sign_in_with_email_and_password(config['firebase']['firebaseUser'], config['firebase']['firebasePassword'])
fire_db = firebase.database()

# endregion

# region External Services (bing, glassdoor, etc.)

def search_glassdoor(company_name, page_size="20", ua=None, ip=None):
    """Returns list of matching companies (or empty list)"""
    obj = None
    useragent = ua
    # Construct user agent
    if useragent is None or useragent == '':
        useragent = 'Mozilla%2F5.0%20(Macintosh%3B%20Intel%20Mac%20OS%20X%2010_10_1)%20AppleWebKit'
        useragent += '%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F39.0.2171.95%20Safari%2F537.36'
        useragent += '.' + str(randint(0, 10000))  # Add a bit of randomness to avoid hitting limits
    userip = ip
    if userip is None or userip == '':
        userip = '0.0.0.0'
    url = 'http://api.glassdoor.com/api/api.htm?t.p='
    url += config['glassdoor']['glassDoorPartnerId']
    url += '&t.k=' + config['glassdoor']['glassDoorPartnerKey']
    if page_size != "20":
        url += '&ps=' + page_size
    url += '&userip=' + userip + '&useragent=' + useragent + '&format=json&v=1&action=employers&q='
    url += company_name
    headers = {'User-Agent': FAKE_USER_AGENT}
    r = requests.request('GET', url, headers=headers)
    if r.status_code == 200:
        obj = r.json()
    else:
        raise Exception('Received invalid response code from Glassdoor (' + str(r.status_code) + '): ' + r.content)
    if obj and 'success' in obj and not bool(obj['success']):
        raise Exception('Glassdoor call not successful (' + str(r.status_code) + '): ' + r.content)
    if obj and 'employers' in obj['response']:
        return obj['response']['employers']
    return []

def search_fullcontact(website):
    """Performs Fullcontact search by domain and returns object (or None)"""
    obj = None
    apikey = config['fullcontact']['fullContactApiKey']
    url = 'https://api.fullcontact.com/v2/company/lookup.json?domain=' + website
    headers = {
        'User-Agent': FAKE_USER_AGENT + '.' + str(randint(0, 10000)),  # Randomness to avoid hitting limits
        'X-FullContact-APIKey': apikey
    }
    r = requests.request('GET', url, headers=headers)
    if r.status_code == 200:
        obj = r.json()
    else:
        sentry.captureMessage('Received invalid response code from FullContact (' + str(r.status_code) + ')', extra=r.content)
    if obj and 'status' in obj and int(obj['status']) != 200:
        sentry.captureMessage('Fullcontact call not successful (' + str(r.status_code) + ')', extra=r.content)
    return obj

def request_klout_score(user_id):
    """Gets Klout score (if username exists) or None if not found"""
    obj = None
    apikey = config['klout']['kloutApiKey']
    url = 'http://api.klout.com/v2/user.json/' + user_id + '/score?key=' + apikey
    headers = {
        'User-Agent': FAKE_USER_AGENT
    }
    r = requests.request('GET', url, headers=headers)
    if r.status_code == 200:
        obj = r.json()
    else:
        sentry.captureMessage('Received invalid response code from Klout (' + str(r.status_code) + ')', extra=r.content)
    if obj and 'score' in obj:
        return float(obj['score'])
    return None

def search_bing(term):
    # TODO
    '''
    headers = {
        # Request headers
        'Ocp-Apim-Subscription-Key': config['azure']['bingSearchKey1'],
    }

    params = urllib.parse.urlencode({
        # Request parameters
        'q': 'microsoft',
        'count': '10',
        'offset': '0',
        'mkt': 'en-us',
        'safeSearch': 'Moderate',
    })

    try:
        conn = http.client.HTTPSConnection('api.cognitive.microsoft.com', context= ssl._create_unverified_context())
        conn.request("GET", "/bing/v5.0/news/search?%s" % params, "google", headers)
        response = conn.getresponse()
        data = response.read()
        print(data)
        conn.close()
    except Exception as e:
        print("[Errno {0}] {1}".format(e.errno, e.strerror))
    '''
    return None

def search_twitter(term):
    # TODO
    return None

def request_sentiment(documents):
    # TODO
    # Detect sentiment: https://www.microsoft.com/cognitive-services/en-us/text-analytics-api
    # AZURE = 90 days trial only!
    #https://www.microsoft.com/cognitive-services/en-US/subscriptions
    '''
    headers = {
        # Request headers
        'Content-Type': 'application/json',
        'Ocp-Apim-Subscription-Key': config['azure']['textAnalyticsKey1'],
    }

    params = urllib.parse.urlencode({
    })

    body = {
        "documents": [
            {
                "language": "en",
                "id": 1,
                "text": ""
            }
        ]
    }


    try:
        conn = http.client.HTTPSConnection('westus.api.cognitive.microsoft.com', context= ssl._create_unverified_context())
        conn.request("POST", "/text/analytics/v2.0/sentiment?%s" % params, json.dumps(body), headers)
        response = conn.getresponse()
        data = response.read()
        print(data)
        conn.close()
    except Exception as e:
        print("[Errno {0}] {1}".format(e.errno, e.strerror))

    '''
    return None

def request_stock(company):
    """Uses Google's open finance API to query a company name and hopefully get back a % representing score (or None)"""
    obj = None
    try:
        url = 'https://www.google.com/finance?q=' + company + '&output=json'
        headers = { 'User-Agent': FAKE_USER_AGENT }
        r = requests.request('GET', url, headers=headers)
        if r.status_code == 200:
            results = r.text.replace('\n', '').replace('// ', '').replace('\\', '').strip()
            obj = json.loads(results)
        else:
            sentry.captureMessage('Received invalid response code from Google Finance (' + str(r.status_code) + ')', extra=r.content)
    except Exception as e:
        # Do not die because of this!
        sentry.captureException()
    if obj is not None and len(obj) > 0:
        if type(obj) is list:
            if 'lo' in obj[0]:
                avg_today = (float(obj[0]['lo']) + float(obj[0]['hi'])) / 2
                low_52_weeks = float(obj[0]['lo52'])
                high_52_weeks = float(obj[0]['hi52'])
                result = 0.5
                if avg_today <= low_52_weeks:
                    result = 0
                elif avg_today >= high_52_weeks:
                    result = 1
                else:
                    roof = high_52_weeks - low_52_weeks
                    current_below_roof = avg_today - low_52_weeks
                    # e.g. 800=top, 600=bottom, roof=200, current=100, result=0.5
                    result = current_below_roof / roof
                return result
        elif type(obj) is dict:
            if 'searchresults' in obj:
                #for result in obj['searchresults']:
                # TODO: In the future we can try to determine if there is an exact match (replacing spaces, lowercasing)
                # If there is, then we can get the stock value from that (as this is a search in this case and not)
                # an exact match... exact match is a list like described in the previous example
                return None
    return None

# endregion

# region Internal Functions

def construct_companies(company_name, company_name_clean, limit_to_this_id=None, existing_valuations_for_this_id=None, ua=None, ip=None):
    results = []

    # Search Glassdoor (larger page size if looking for 1 ID as they only have name search so we must try to find it!)
    glassdoor_results = search_glassdoor(company_name, '20' if limit_to_this_id is None else '50', ua, ip)
    if len(glassdoor_results) == 0:
        return []

    # Loop through results (up to 10 for a given company name)
    for item in glassdoor_results[:10]:
        if limit_to_this_id is not None and int(item['id']) != limit_to_this_id:
            continue

        # Extract Glassdoor content
        gd_number_of_ratings = int(item['numberOfRatings']) if 'numberOfRatings' in item else 0
        gd_overall_rating = float(item['overallRating']) if 'overallRating' in item else 0
        gd_culture_and_values_rating = float(item['overallRating']) if 'overallRating' in item else 0
        gd_senior_leadership_rating = float(item['cultureAndValuesRating']) if 'cultureAndValuesRating' in item else 0
        gd_compensation_and_benefits_rating = float(item['compensationAndBenefitsRating']) if 'compensationAndBenefitsRating' in item else 0
        gd_career_opportunities_rating = float(item['careerOpportunitiesRating']) if 'careerOpportunitiesRating' in item else 0
        gd_work_life_balance_rating = float(item['workLifeBalanceRating']) if 'workLifeBalanceRating' in item else 0
        gd_ceo_pct_approval = float(item['ceo']['pctApprove']) if 'ceo' in item else 100
        gd_id = item['id']
        gd_name_real = item['name']
        gd_square_logo = item['squareLogo'] if ('squareLogo' in item and item['squareLogo'] is not None and item['squareLogo'].strip() != '') else None
        gd_website = item['website'] if ('website' in item and item['website'] is not None and item['website'].strip() != '') else None
        gd_industry = item['industry'] if ('industry' in item and item['industry'] is not None and item['industry'].strip() != '') else None
        gd_sector_name = item['sectorName'] if ('sectorName' in item and item['sectorName'] is not None and item['sectorName'].strip() != '') else None
        gd_ceo = item['ceo'] if ('ceo' in item and item['ceo'] is not None) else None

        # Fullcontact search
        fc_found = False
        fc_name_full = ''
        fc_language = ''
        fc_aprox_employees = 0
        fc_founded = ''
        fc_keywords = []
        fc_traffic_global_rank = None
        fc_item = None
        if gd_website is not None:
            try:
                fc_item = search_fullcontact(gd_website)
                if fc_item is not None:
                    fc_found = True
                    fc_name_full = fc_item['organization']['name'] if 'organization' in fc_item else ''
                    fc_language = fc_item['languageLocale'] if 'languageLocale' in fc_item else ''
                    fc_aprox_employees = int(fc_item['organization']['approxEmployees']) if 'organization' in fc_item else 0
                    fc_founded = fc_item['organization']['approxEmployees'] if 'organization' in fc_item else 0
                    fc_keywords = ', '.join(fc_item['organization']['keywords']) if 'organization' in fc_item else ''
                    if 'traffic' in fc_item and 'ranking' in fc_item['traffic']:
                        ranks = fc_item['traffic']['ranking']
                        for rank in ranks:
                            if rank['locale'] == 'global':
                                fc_traffic_global_rank = int(rank['rank'])
            except Exception as e:
                # Don't die, just log and set fc_found to false again
                fc_found = False
                sentry.captureException()

        # Klout
        klout_found = False
        klout_score = 0
        if fc_found:
            try:
                if 'socialProfiles' in fc_item:
                    for profile in fc_item['socialProfiles']:
                        if profile['typeId'] == 'klout' and 'id' in profile:
                            klout_score = request_klout_score(profile['id'])
                            klout_found = True if klout_score is not None else False
            except Exception as e:
                # Don't die, just log and set klout_found to false again
                klout_found = False
                sentry.captureException()

        # Get news TODO
        # Get tweets TODO
        # Perform sentiment analysis on both TODO
        sentiment_found = False
        social_sentiment = None  # pct! (0-1)

        # Get stock index
        stock_score = request_stock(company_name)
        stock_found = True if stock_score is not None else False

        # Form object to be persisted
        record_status = 'complete' if sentiment_found and fc_found else 'incomplete'
        update_date = int(tyme.time())
        company_data = {
            'record_status': record_status,
            'last_update': update_date,
            'name': company_name_clean,
            'valuations': {
                str(update_date): {
                    'gd_number_of_ratings': gd_number_of_ratings,
                    'gd_overall_rating': gd_overall_rating,
                    'gd_culture_and_values_rating': gd_culture_and_values_rating,
                    'gd_senior_leadership_rating': gd_senior_leadership_rating,
                    'gd_compensation_and_benefits_rating': gd_compensation_and_benefits_rating,
                    'gd_career_opportunities_rating': gd_career_opportunities_rating,
                    'gd_work_life_balance_rating': gd_work_life_balance_rating,
                    'gd_ceo_pct_approval': gd_ceo_pct_approval,
                    'valuation_total_score': 0  # Temp
                }
            },
            'gd_id': gd_id,
            'gd_name_real': gd_name_real,
            'gd_square_logo': gd_square_logo,
            'gd_website': gd_website,
            'gd_industry': gd_industry,
            'gd_sector_name': gd_sector_name,
            'gd_ceo': gd_ceo
        }

        # Merge valuations with existing ones if updating an existing record and this is the record
        if limit_to_this_id is not None and int(item['id']) == limit_to_this_id and existing_valuations_for_this_id is not None:
            oldest_valuation = None
            for key, valuation in existing_valuations_for_this_id.items():
                company_data['valuations'][key] = valuation
                if oldest_valuation is None or int(key) < oldest_valuation:
                    oldest_valuation = int(key)
            # Limit to 12 data points (could increase in the future, just don't want to fill up firebase)
            if len(company_data['valuations']) > 12:
                company_data['valuations'].pop(str(oldest_valuation), None)

        if fc_found:
            company_data['fc_name_full'] = fc_name_full
            company_data['fc_language'] = fc_language
            company_data['fc_aprox_employees'] = fc_aprox_employees
            company_data['fc_founded'] = fc_founded
            company_data['fc_keywords'] = fc_keywords
            company_data['valuations'][str(update_date)]['fc_traffic_global_rank'] = fc_traffic_global_rank

        if sentiment_found:
            company_data['valuations'][str(update_date)]['social_sentiment'] = social_sentiment

        if klout_found:
            company_data['valuations'][str(update_date)]['kl_score'] = klout_score

        if stock_found:
            company_data['valuations'][str(update_date)]['stock_lo'] = stock_score

        # Calculate rank (%) for the new variation
        # 80% GD, 10% Social, 5% Stock, 3% Klout, 2% "in top 5000 traffic rank"
        val_gd_pct = float(gd_overall_rating / 5) * 0.8
        val_soc_pct = 0.10 if not sentiment_found else float(social_sentiment) * 0.10
        val_stock_pct = 0.05 if not stock_found else float(stock_score) * 0.05
        val_klout_pct = 0.03 if not klout_found else float(klout_score / 100) * 0.03
        val_traffic_pct = 0 if (fc_traffic_global_rank is None or fc_traffic_global_rank > 5000) else 0.02
        valuation_total_score = float(val_gd_pct + val_soc_pct + val_stock_pct + val_klout_pct + val_traffic_pct)
        company_data['valuations'][str(update_date)]['valuation_total_score'] = valuation_total_score

        # Get the incline
        oldest_valuation_key = None
        newest_valuation_key = None
        for key, val_obj in company_data['valuations'].items():
            if newest_valuation_key is None or int(key) > newest_valuation_key:
                newest_valuation_key = int(key)
            if oldest_valuation_key is None or int(key) < oldest_valuation_key:
                oldest_valuation_key = int(key)
        first_valuation_score = company_data['valuations'][str(oldest_valuation_key)]['valuation_total_score']
        last_valuation_score = company_data['valuations'][str(newest_valuation_key)]['valuation_total_score']
        pct_valuation_change = float(last_valuation_score) - float(first_valuation_score)  # Negative if falling

        # Determine status
        # (floating|rising|falling, sailing|speeding|leaking, submerged|surfacing|sinking, sunk)
        boat_status = 'unknown'
        if fc_found and fc_aprox_employees >= 1000 and last_valuation_score >= 0.8:
            # Large companies can float
            boat_status = 'floating'
            if pct_valuation_change > 0.05:
                boat_status = 'rising'
            elif pct_valuation_change < -0.05:
                boat_status = 'falling'
        if boat_status == 'unknown':
            if last_valuation_score >= 0.65:
                boat_status = 'sailing'
                if pct_valuation_change > 0.05:
                    boat_status = 'speeding'
                elif pct_valuation_change < -0.05:
                    boat_status = 'leaking'
            elif last_valuation_score < 0.65 and last_valuation_score >= 0.3:
                boat_status = 'submerged'
                if pct_valuation_change > 0.05:
                    boat_status = 'surfacing'
                elif pct_valuation_change < -0.05:
                    boat_status = 'sinking'
            elif last_valuation_score < 0.3:
                boat_status = 'sunk'
                # TODO: Detect if company still exists, if not then it also counts as sunk!
        company_data['boat_status'] = boat_status

        # Determine average monthly score
        sorted_keys = sorted(list(company_data['valuations'].keys()), reverse=True)[:4]
        last_valuations = []
        for key in sorted_keys:
            last_valuations.append(company_data['valuations'][key]['valuation_total_score'])
        valuation_4_week_avg_score = float(sum(last_valuations) / len(last_valuations))
        company_data['valuation_4_week_avg_score'] = valuation_4_week_avg_score

        # Add item to results
        results.append({'id': gd_id, 'data': company_data})

    return results

def construct_company_for_update(company_id, gd_name_real, db_record_company):
    """Call construct company, find the company in the results, return object, or None"""
    results = construct_companies(
        gd_name_real,
        gd_name_real.strip().lower(),
        company_id,
        db_record_company['valuations']
    )

    # Return single result (or none)
    if len(results) > 0:
        return results[0]
    return None

def item_needs_update(timestamp_last_updated):
    item_last_updated = datetime.utcfromtimestamp(int(timestamp_last_updated))
    current_datetime = datetime.utcnow()
    hours_difference = (current_datetime - item_last_updated).seconds / 60 / 60
    return hours_difference > 168

def prepare_result(company):
    item_status = STATUS_CURRENT
    if 'last_update' not in company or item_needs_update(company['last_update']):
        item_status = STATUS_UPDATE_REQUIRED
    company['status'] = item_status
    return company

# endregion

# region Endpoints

@app.route("/search/<string:company>", methods=['GET'])
@limiter.limit("100 per hour")
def search_company(company):
    # Lowercase (for search) + validate
    company_name_search = company.lower().strip()
    if company_name_search == '':
        return make_error({'status': STATUS_ERROR, 'message': 'Name was not entered or is not formatted correctly'}, 400)

    # Search for items based on name, if none found return "not found"
    try:
        search_results = fire_db.child("companies").order_by_child("name").equal_to(company_name_search).limit_to_first(10).get()
        if search_results.val() is None or len(search_results.val()) == 0:
            err_msg = 'We could not find a company with this name in our database'
            return make_error({'status': STATUS_NOT_FOUND, 'action': '/company/{NAME}/create', 'message': err_msg}, 404)
    except Exception as e:
        sentry.captureException()
        return make_error({'status': STATUS_ERROR, 'message': 'Server error (500)'}, 500)

    # Form a list of results based on Firebase's data (and check if each item is up to date)
    try:
        results = []
        global_status = 'success'
        items_needing_update = 0
        for item in search_results.each():
            item_data = item.val()
            if item_data:
                result_company = prepare_result(item_data)
                if result_company['status'] == STATUS_UPDATE_REQUIRED:
                    items_needing_update += 1
                results.append(result_company)

        # If all items require an update, set global status to that
        if items_needing_update == len(results):
            global_status = STATUS_FULL_UPDATE_REQUIRED
        elif items_needing_update >= 1 and items_needing_update < len(results):
            global_status = STATUS_PARTIAL_UPDATE_REQUIRED
    except Exception as e:
        sentry.captureException()
        return make_error({'status': STATUS_ERROR, 'message': 'Server error (500)'}, 500)

    # Return results
    return success({'status': global_status, 'results': results, 'count': len(results)})

@app.route("/company/<int:company_id>", methods=['GET'])
@limiter.limit("10 per hour")
def company_get_one(company_id):
    # Retrieve company
    try:
        item = fire_db.child("companies/" + str(company_id)).get()
        if item.val() is None:
            err_msg = 'We could not find a company with this ID in our database'
            return make_error({'status': STATUS_NOT_FOUND, 'message': err_msg}, 404)
    except Exception as e:
        sentry.captureException()
        return make_error({'status': STATUS_ERROR, 'message': 'Server error (500)'}, 500)
    company = item.val()

    # Return result
    result_company = prepare_result(company)
    call_status = STATUS_SUCCESS
    if result_company['status'] == STATUS_UPDATE_REQUIRED:
        call_status = STATUS_UPDATE_REQUIRED
    return success({'status': call_status, 'result': result_company})

@app.route("/company/<string:company>/create", methods=['GET'])
@limiter.limit("5 per hour")
def company_create(company):
    # Lowercase (for search) + validate
    company_name_search = company.lower().strip()
    if company_name_search == '':
        return make_error({'status': STATUS_ERROR, 'message': 'Incorrect format'}, 400)

    # Does it exist already?
    try:
        search_results = fire_db.child("companies").order_by_child("name").equal_to(company).limit_to_first(10).get()
        if search_results.val() is not None and len(search_results.val()) > 0:
            return make_error({'status': STATUS_ERROR, 'message': 'Company already exists'}, 400)
    except Exception as e:
        sentry.captureException()
        err_msg = 'An unexpected error ocurred while checking if company already exists'
        return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    # Construct company (search glassdoor, find all data, generate result object)
    try:
        ua = request.args.get('ua')  # Optional user agent
        ip = request.args.get('ip')  # Optional ip
        companies = construct_companies(company, company_name_search, None, None, ua, ip)
        if len(companies) == 0:
            return make_error({'status': STATUS_ERROR, 'message': 'Company not found on GD'}, 404)
    except Exception as e:
        sentry.captureException()
        err_msg = 'An unexpected error ocurred while obtaining the required data for this company'
        return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    # Push object to Firebase
    try:
        for company in companies:
            company_id = company['id']
            company_data = company['data']
            # Before persisting, check if ID exists in DB, as construct_companies returns various results
            item = fire_db.child("companies/" + str(company_id)).get()
            if item.val() is None:
                fire_db.child("companies").child(company_id).set(company_data)
    except Exception as e:
        sentry.captureException()
        err_msg = 'An unexpected error ocurred while saving this new company in our database'
        return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    # Return object
    results = []
    for company in companies:
        result_company = prepare_result(company['data'])
        results.append(result_company)
    return success({"status": STATUS_SUCCESS, "results": results})

@app.route("/company/<int:company_id>/update", methods=['GET'])
@limiter.limit("10 per hour")
def company_update(company_id):
    # Retrieve company
    try:
        item = fire_db.child("companies/" + str(company_id)).get()
        if item.val() is None:
            err_msg = 'We could not find a company with this ID in our database'
            return make_error({'status': STATUS_NOT_FOUND, 'message': err_msg}, 404)
    except Exception as e:
        sentry.captureException()
        return make_error({'status': STATUS_ERROR, 'message': 'Server error (500)'}, 500)
    company = item.val()

    if 'last_update' in company and not item_needs_update(company['last_update']):
        err_msg = 'Company does not require an update as it was updated recently'
        return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    # Construct new company (obtain data from external services and construct a new full object)
    try:
        new_company = construct_company_for_update(company_id, company['gd_name_real'], company)
    except Exception as e:
        sentry.captureException()
        err_msg = 'An unexpected error ocurred while updating this company with data from external services'
        return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    # If we couldn't construct the company, die
    if new_company is None:
        return make_error({'status': STATUS_ERROR, 'message': 'Unable to construct updated company'}, 500)

    # Push object to Firebase
    try:
        fire_db.child("companies").child(company_id).update(new_company)
    except Exception as e:
        sentry.captureException()
        err_msg = 'An unexpected error ocurred while saving this company in our database'
        return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    # Return object
    result_company = prepare_result(new_company)
    return success({"status": STATUS_SUCCESS, "result": result_company})

@app.route("/company/top/update", methods=['GET'])
@limiter.limit("1 per day")
def company_top_update():
    # Search for top 200
    try:
        results = fire_db.child("companies").order_by_child("valuation_4_week_avg_score").limit_to_last(200).get()
        if results.val() is None or len(results.val()) == 0:
            err_msg = 'No companies found to update'
            return make_error({'status': STATUS_NOT_FOUND, 'action': '/company/{NAME}/create', 'message': err_msg}, 404)
    except Exception as e:
        sentry.captureException()
        return make_error({'status': STATUS_ERROR, 'message': 'Server error (500)'}, 500)

    list_to_update = []
    company_names = {}
    company_records = {}
    for item in results.each():
        item_data = item.val()
        if 'last_update' not in item_data or item_needs_update(item_data['last_update']):
            if 'gd_id' in item_data:
                gd_id = int(item_data['gd_id'])
                list_to_update.append(gd_id)
                company_names[gd_id] = item_data['gd_name_real']
                company_records[gd_id] = item_data

    for company_id in list_to_update:
        # Construct new company (obtain data from external services and construct a new full object)
        try:
            new_company = construct_company_for_update(company_id, company_names[company_id], company_records[company_id])
        except Exception as e:
            sentry.captureException()
            err_msg = 'An unexpected error ocurred while updating this company with data from external services'
            return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

        # If we couldn't construct the company, die
        if new_company is None:
            return make_error({'status': STATUS_ERROR, 'message': 'Unable to construct updated company'}, 500)

        # Push object to Firebase
        try:
            fire_db.child("companies").child(company_id).update(new_company)
        except Exception as e:
            sentry.captureException()
            err_msg = 'An unexpected error ocurred while saving this company in our database'
            return make_error({'status': STATUS_ERROR, 'message': err_msg}, 500)

    return success({'status': 'success', 'updated': list_to_update})

# endregion

# region Response Generators

@app.errorhandler(404)
def error_not_found(error=''):
    err = 'Resource not found.'
    if error != '':
        err += ' ' + str(error.description)
    return make_error({'status': 'error', 'message': err}, 404)

@app.errorhandler(500)
def error_unknown(error=''):
    err = 'Internal server error. We have caught this and will work to fix this issue ASAP.'
    if error != '':
        err += ' ' + str(error.description)
    return make_error(err, 500)

def success(obj):
    response = jsonify(**obj)
    response.status_code = 200
    return response

def make_error(obj, code=400):
    response = jsonify(**obj)
    response.status_code = code
    return response

# endregion

# region Main (entry point)

if __name__ == "__main__":
    app.debug = True
    app.run(host='0.0.0.0', port=5000)

# endregion
