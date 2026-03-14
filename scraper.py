import requests
import json
import os
import time
import sys

if not os.path.exists('data'):
    os.makedirs('data')

def get_wikipedia_summary(wiki_url):
    if wiki_url == "#" or not wiki_url:
        return "No description available.", None
    title = wiki_url.split('/')[-1]
    api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    headers = {'User-Agent': 'HistoricalGlobeBot/1.0'}
    try:
        r = requests.get(api_url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data.get('extract', 'No summary.'), data.get('thumbnail', {}).get('source', None)
    except: pass
    return "No description available.", None

def fetch_year(year):
    print(f"\n📅 Scoping Year: {year}")
    endpoint_url = "https://query.wikidata.org/sparql"

    # IMPROVED QUERY:
    # 1. We look for coords on the event OR the event's location (P276/P17)
    # 2. We bucket types into 6 categories for your JS colors
    query = f"""
    SELECT DISTINCT ?item ?itemLabel ?eventDate ?coords ?article ?categoryLabel WHERE {{
      {{ ?item wdt:P585 ?eventDate. }} UNION {{ ?item wdt:P580 ?eventDate. }}
      
      # Try to get coords from the item itself, or its location/country
      OPTIONAL {{ ?item wdt:P625 ?directCoords. }}
      OPTIONAL {{ ?item wdt:P276/wdt:P625 ?locCoords. }}
      OPTIONAL {{ ?item wdt:P17/wdt:P625 ?countryCoords. }}
      BIND(COALESCE(?directCoords, ?locCoords, ?countryCoords) AS ?coords)
      
      FILTER(BOUND(?coords))
      FILTER(?eventDate >= "{year}-01-01T00:00:00Z"^^xsd:dateTime && 
             ?eventDate <= "{year}-12-31T23:59:59Z"^^xsd:dateTime)

      ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>.
      
      # CATEGORY BUCKETING
      OPTIONAL {{ ?item wdt:P31 ?type. }}
      BIND(
        IF(?type IN (wd:Q198, wd:Q188055, wd:Q170658, wd:Q80707), "Conflict",
        IF(?type IN (wd:Q103360, wd:Q274870, wd:Q4022, wd:Q890045), "Politics",
        IF(?type IN (wd:Q464980, wd:Q16530, wd:Q211386), "Science",
        IF(?type IN (wd:Q11538, wd:Q80839, wd:Q1656682), "Sports",
        IF(?type IN (wd:Q12483, wd:Q7150, wd:Q333, wd:Q11660), "Culture", "General")))))
      AS ?categoryLabel)

      MINUS {{ ?item wdt:P31 wd:Q5. }} # No Humans
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 1500
    """

    headers = {'User-Agent': 'HistoricalGlobeBot/1.0', 'Accept': 'application/sparql-results+json'}
    
    try:
        response = requests.get(endpoint_url, params={'query': query, 'format': 'json'}, headers=headers, timeout=60)
        data = response.json()['results']['bindings']
        
        results = []
        seen_titles = set()
        count = 0

        for res in data:
            # Debug to stop lots of data entries
            if count > 100:
                continue
            
            title = res['itemLabel']['value']
            if title.lower() in seen_titles: continue
            
            wiki_link = res.get('article', {}).get('value', '#')
            summary, img = get_wikipedia_summary(wiki_link)
            raw_c = res['coords']['value'].replace("Point(", "").replace(")", "").split(" ")
            
            results.append({
                "title": title,
                "category": res.get('categoryLabel', {'value': 'General'})['value'],
                "date": res['eventDate']['value'].split('T')[0],
                "description": summary,
                "imageUrl": img,
                "wikiLink": wiki_link,
                "lon": float(raw_c[0]),
                "lat": float(raw_c[1]),
                "id": res['item']['value'].split('/')[-1], # Gets the QID (e.g., Q12345)
            })
            seen_titles.add(title.lower())
            count += 1
            print(f"\r   📥 Events Saved: {count} | Current: {title[:20]}...", end="")

        if results:
            results.sort(key=lambda x: x['date'])
            with open(f'data/{year}.json', 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            print(f"\n✅ Total unique events for {year}: {len(results)}")

    except Exception as e:
        print(f"\n❌ Failed {year}: {e}")

if __name__ == "__main__":
    try:
        for y in range(1900, 1905):
            fetch_year(y)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 User stopped the process.")
        sys.exit(0)
