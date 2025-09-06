import asyncio
import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from playwright.async_api import async_playwright
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
from datetime import datetime
import certifi  # 1️⃣ Import the certifi library

# --- Configuration ---
load_dotenv()
PORT = int(os.environ.get("PORT", 8000))
COOKIES_FILE_PATH = "./cookies.json"
MONGO_URI = os.environ.get("MONGO_URI")

# --- Logic to Create cookies.json on Render ---
if os.environ.get("TWITTER_COOKIES"):
    if not os.path.exists(COOKIES_FILE_PATH):
        print("[DEBUG] cookies.json not found. Creating from environment variable...")
        with open(COOKIES_FILE_PATH, 'w') as f:
            f.write(os.environ.get("TWITTER_COOKIES"))
        print("[DEBUG] cookies.json created successfully.")

# --- MongoDB Connection ---
if not MONGO_URI:
    raise Exception("❌ ERROR: MONGO_URI is not defined in your .env file.")

# 2️⃣ Add tlsCAFile to the client to fix SSL issues
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client.get_default_database()
articles_collection = db.articles
print("✅ MongoDB connected successfully.")

# --- Main Scraper Function ---
async def scrape_tweets(username: str, required_tweet_count: int = 25):
    if not os.path.exists(COOKIES_FILE_PATH):
        raise Exception("Cookies file not found. Run login.py or set TWITTER_COOKIES env var.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = None
        try:
            with open(COOKIES_FILE_PATH, 'r') as f:
                cookies = json.load(f)
            
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()
            target_url = f"https://x.com/{username}"
            
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector("div[data-testid='cellInnerDiv']", timeout=60000)

            # Scrolling logic
            for _ in range(10):
                tweet_count = await page.locator("article[data-testid='tweet']").count()
                if tweet_count >= required_tweet_count:
                    break
                await page.evaluate("window.scrollBy(0, 2500)")
                await asyncio.sleep(2)

            scraped_tweets = await page.eval_on_selector_all(
                "article[data-testid='tweet']",
                "(articles, count) => articles.slice(0, count).map(article => {"
                "  const mainTimeEl = article.querySelector(\"a[href*='/status/'] time\");"
                "  if (!mainTimeEl) return null;"
                "  const mainLinkEl = mainTimeEl.closest('a');"
                "  const textEl = article.querySelector(\"div[data-testid='tweetText']\");"
                "  if (!mainLinkEl || !textEl) return null;"
                "  const media = [];"
                "  const hasVideoPlayer = article.querySelector(\"div[data-testid='videoPlayer']\");"
                "  if (hasVideoPlayer) {"
                "    let videoPostUrl = mainLinkEl.href;"
                "    const quotedTweet = article.querySelector(\"div[role='link'][tabindex='0']\");"
                "    if (quotedTweet) {"
                "      const quotedTimeEl = quotedTweet.querySelector('time');"
                "      const quotedLinkEl = quotedTimeEl ? quotedTimeEl.closest('a') : null;"
                "      if (quotedLinkEl && quotedLinkEl.href) videoPostUrl = quotedLinkEl.href;"
                "    }"
                "    media.push({ mediaType: 'video_post', url: videoPostUrl });"
                "  } else {"
                "    article.querySelectorAll(\"div[data-testid='tweetPhoto'] img\").forEach(img => {"
                "      if (img.src) media.push({ mediaType: 'image', url: img.src });"
                "    });"
                "  }"
                "  return {"
                "    text: textEl.innerText,"
                "    url: mainLinkEl.href,"
                "    date: mainTimeEl.getAttribute('datetime'),"
                "    media: media,"
                "  };"
                "})",
                required_tweet_count
            )

            valid_tweets = [t for t in scraped_tweets if t is not None]
            valid_tweets.sort(key=lambda x: x['date'], reverse=True)
            return valid_tweets
        finally:
            if browser:
                await browser.close()

# --- Flask Server Setup ---
app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return "Python Stealth Scraper server is running."

@app.route("/scrape/<username>")
def scrape_and_save(username):
    try:
        count = int(request.args.get('count', 5))
        
        recent_tweets = asyncio.run(scrape_tweets(username, count + 20))
        
        if not recent_tweets:
            return jsonify({"message": "No tweets found on the user's profile."}), 404

        standardized_tweets = [{
            **tweet,
            "url": tweet["url"].replace("x.com", "twitter.com"),
            "media": [{"mediaType": m["mediaType"], "url": m["url"].replace("x.com", "twitter.com")} for m in tweet["media"]]
        } for tweet in recent_tweets]
        
        scraped_urls = [t['url'] for t in standardized_tweets]
        existing_articles = articles_collection.find({'url': {'$in': scraped_urls}}, {'url': 1, '_id': 0})
        existing_urls = {a['url'] for a in existing_articles}
        
        new_tweets = [t for t in standardized_tweets if t['url'] not in existing_urls]
        
        if not new_tweets:
            return jsonify({"message": "Scraping complete. No new tweets found.", "username": username})

        tweets_to_save = new_tweets[:count]
        
        operations = []
        for tweet in tweets_to_save:
            article_data = {
                "title": tweet['text'][:150] + ('...' if len(tweet['text']) > 150 else ''),
                "summary": tweet['text'],
                "body": tweet['text'],
                "url": tweet['url'],
                "source": f"Twitter @{username}",
                "isCreatedBy": "twitter",
                "publishedAt": datetime.fromisoformat(tweet['date'].replace('Z', '+00:00')),
                "media": tweet['media'],
            }
            operations.append(UpdateOne({'url': article_data['url']}, {'$setOnInsert': article_data}, upsert=True))

        if operations:
            result = articles_collection.bulk_write(operations)
            new_articles_saved_count = result.upserted_count
        else:
            new_articles_saved_count = 0

        return jsonify({
            "message": "Scrape and save operation completed successfully.",
            "username": username,
            "newArticlesSaved": new_articles_saved_count,
            "articles": tweets_to_save,
        })

    except Exception as e:
        print(f"❌ Top-level error for @{username}: {e}")
        return jsonify({"error": "Failed to scrape or save tweets.", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(port=PORT)

