import asyncio
import aiohttp
import json
import os
import random
import sys
from urllib.parse import unquote, quote

# Directory configuration
DATA_DIRECTORY = 'data'
START_YEAR = 2000
END_YEAR = 2001

# Ensure the output directory exists before starting
if not os.path.exists(DATA_DIRECTORY):
    os.makedirs(DATA_DIRECTORY)

async def fetch_summary(session, url, event, stats, semaphore):
    """
    Fetches the Wikipedia summary and updates the real-time progress line.
    """
    async with semaphore:
        for attempt in range(3):
            try:
                await asyncio.sleep(random.uniform(0.05, 0.2))
                async with session.get(url, timeout=12) as response:
                    if response.status == 200:
                        data = await response.json()
                        event['description'] = data.get('extract', 'No summary available.')
                        event['imageUrl'] = data.get('thumbnail', {}).get('source', None)
                        stats['done'] += 1
                        # Real-time progress update
                        sys.stdout.write(f"\r    → Progress: {stats['done']} synced | {stats['failed']} failed")
                        sys.stdout.flush()
                        return event
                    elif response.status == 429:
                        await asyncio.sleep((attempt + 1) * 2)
                    else:
                        break
            except Exception:
                await asyncio.sleep(0.5)
        
        stats['failed'] += 1
        sys.stdout.write(f"\r    → Progress: {stats['done']} synced | {stats['failed']} failed")
        sys.stdout.flush()
        event['description'] = "Summary unavailable (Sync failed)."
        return event

async def fetch_wikipedia_summaries(session, events):
    """
    Orchestrates asynchronous fetching and manages the progress line end.
    """
    stats = {'done': 0, 'failed': 0}
    semaphore = asyncio.Semaphore(25) 
    
    # Filter only events that need a Wiki fetch
    wiki_events = [e for e in events if e.get('hasWiki')]
    non_wiki_events = [e for e in events if not e.get('hasWiki')]
    
    for e in non_wiki_events:
        e['description'] = "Historical record (Wikidata)."

    if wiki_events:
        tasks = []
        # Inside fetch_wikipedia_summaries
        for event in wiki_events:
            # 1. Get the raw title (e.g., "George_W._Bush")
            raw_title = event['wikiLink'].split('/')[-1]
            # 2. Decode any existing %20 etc, then re-encode for a URL
            clean_title = quote(unquote(raw_title))
            
            api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_title}"
            tasks.append(fetch_summary(session, api_url, event, stats, semaphore))
            
        await asyncio.gather(*tasks)
    
    # Print a newline so the next log doesn't overwrite the final progress
    print() 
    return events

async def fetch_year(session, year):
    """
    Queries Wikidata and processes results with specific console logging.
    """
    print(f"--- Scoping Year: {year} ---")
    sparql_endpoint = "https://query.wikidata.org/sparql"
    
    query = f"""
    SELECT DISTINCT ?item ?itemLabel ?eventDate ?coords ?article ?sitelinks ?categoryLabel WHERE {{
    # 1. Date and Precision
    ?item p:P585/psv:P585 [
        wikibase:timeValue ?eventDate ;
        wikibase:timePrecision 11
    ] .
    
    FILTER(?eventDate >= "{year}-01-01T00:00:00Z"^^xsd:dateTime && 
            ?eventDate <= "{year}-12-31T23:59:59Z"^^xsd:dateTime)

    # 2. Notability Filter (Global History vs. Local News)
    ?item wikibase:sitelinks ?sitelinks .
    FILTER(?sitelinks >= 3)

    # 3. Category Filtering
    ?item wdt:P31 ?type .
    ?type (wdt:P279*) ?broadType .
    VALUES ?broadType {{ 
        wd:Q198      # War
        wd:Q188055   # Battle
        wd:Q124490   # Riot
        wd:Q7748     # Law
        wd:Q4022     # Treaty
        wd:Q27318    # Coup
        wd:Q1190554  # Incident
        wd:Q40262    # Election
    }}

    # 4. Coordinate Fallback
    OPTIONAL {{ ?item wdt:P625 ?directCoords. }}
    OPTIONAL {{ ?item wdt:P276/wdt:P625 ?locCoords. }}
    OPTIONAL {{ ?item wdt:P131/wdt:P625 ?adminCoords. }}
    OPTIONAL {{ ?item wdt:P17/wdt:P625 ?countryCoords. }}
    BIND(COALESCE(?directCoords, ?locCoords, ?adminCoords, ?countryCoords) AS ?coords)
    FILTER(BOUND(?coords))

    # 5. Wikipedia Link
    ?article schema:about ?item ; 
            schema:isPartOf <https://en.wikipedia.org/> .

    # 6. Labeling
    BIND(
        IF(?broadType = wd:Q198 || ?broadType = wd:Q188055, "Military",
        IF(?broadType = wd:Q7748 || ?broadType = wd:Q4022 || ?broadType = wd:Q40262, "Political",
        IF(?broadType = wd:Q124490 || ?broadType = wd:Q27318, "Unrest", "General"))) AS ?categoryLabel
    )

    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} 
    ORDER BY DESC(?sitelinks)
    LIMIT 500
    """

    headers = {'Accept': 'application/sparql-results+json'}
    
    async with session.get(sparql_endpoint, params={'query': query, 'format': 'json'}, headers=headers) as response:
        if response.status != 200:
            print(f"    → Wikidata request failed: {response.status}")
            return
        
        data = await response.json(content_type=None)
        raw_results = data['results']['bindings']

    print(f"Found {len(raw_results)} potential entries. Processing coordinates...")
    
    events_to_process = []
    invalid_coords = 0
    for res in raw_results:
        try:
            raw_coords = res['coords']['value'].replace("Point(", "").replace(")", "").split(" ")
            wiki_link = res.get('article', {}).get('value', None)
            
            events_to_process.append({
                "title": res['itemLabel']['value'],
                "category": res.get('categoryLabel', {'value': 'General'})['value'],
                "date": res['eventDate']['value'].split('T')[0],
                "wikiLink": wiki_link if wiki_link else f"https://www.wikidata.org/wiki/{res['item']['value'].split('/')[-1]}",
                "hasWiki": True if wiki_link else False,
                "lon": float(raw_coords[0]),
                "lat": float(raw_coords[1])
            })
        except Exception:
            invalid_coords += 1
            continue

    print(f"    → Valid coordinates: {len(events_to_process)} | Invalid: {invalid_coords}")
    print("Syncing summaries from Wikipedia API...")
    
    final_results = await fetch_wikipedia_summaries(session, events_to_process)

    file_path = f'{DATA_DIRECTORY}/{year}.json'
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, indent=2)
    
    print(f"Successfully saved {len(final_results)} events to {file_path}")

async def main():
    headers = {
        'User-Agent': 'HistoryMapBot/2.0 (contact: jascott@caltech.edu) aiohttp/3.x'
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        for year in range(START_YEAR, END_YEAR + 1):
            await fetch_year(session, year)
            
            wait_time = 3.0
            print(f"Waiting {wait_time:.1f}s before next year...\n")
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScraper stopped by user.")
