# generate_feeds.py
"""
A script to generate a well-formatted Python file containing over 100
trusted RSS feeds for music, travel, and US local journalism.

The output file will be named 'discovery_rss_generated.py' and can be
used as a discovery source for the Axiom Engine.
"""

import os
from typing import Final, List, Tuple

# --- Data: A curated list of high-quality RSS feeds ---

# Category 1: AP & Music Journalism
# A mix of direct AP feeds and other top-tier music journalism sources.
MUSIC_FEEDS: Final[Tuple[str, ...]] = (
    "https://apnews.com/hub/music/rss",  # Associated Press - Music News
    "https://www.npr.org/rss/rss.php?id=1039",  # NPR Music
    "https://www.billboard.com/feed/",  # Billboard
    "https://pitchfork.com/feed/feed-news/rss",  # Pitchfork - News
    "https://www.rollingstone.com/feed/",  # Rolling Stone
    "https://www.spin.com/feed/",  # SPIN Magazine
    "https://www.pastemagazine.com/music/rss",  # Paste Magazine - Music
    "https://consequence.net/feed/",  # Consequence of Sound
    "https://www.brooklynvegan.com/feed/",  # BrooklynVegan
    "https://www.stereogum.com/category/news/feed/",  # Stereogum
    "https://www.thefader.com/feeds/main",  # The FADER
    "https://www.classicfm.com/music-news/rss/",  # Classic FM (UK)
    "https://www.grammy.com/rss.xml",  # The GRAMMYs
    "https://www.musicbusinessworldwide.com/feed",  # Music Business Worldwide
    "https://www.factmag.com/feed",  # FACT Magazine
)

# Category 2: AP & Tourist Journalism (Travel)
# A mix of direct AP feeds and other reputable travel/exploration sources.
TRAVEL_FEEDS: Final[Tuple[str, ...]] = (
    "https://apnews.com/hub/travel/rss",  # Associated Press - Travel
    "https://www.atlasobscura.com/feeds/latest",  # Atlas Obscura (Highly Recommended)
    "https://www.nationalgeographic.com/travel/rss-feed",  # National Geographic Travel
    "https://www.lonelyplanet.com/news/feed/atom/",  # Lonely Planet
    "https://www.travelandleisure.com/travel/rss",  # Travel + Leisure
    "https://www.cntraveler.com/feed/rss",  # Condé Nast Traveler
    "https://adventure.com/feed/",  # Adventure.com
    "https://matadornetwork.com/feed/",  # Matador Network
    "https://www.nomadicmatt.com/travel-blog/feed/",  # Nomadic Matt's Travel Site
    "https://www.ricksteves.com/watch-read-listen/read/travel-news/rss.xml",  # Rick Steves' Europe
    "https://www.fodors.com/news/rss",  # Fodor's Travel
    "https://www.frommers.com/rss",  # Frommer's
    "https://www.roadsandkingdoms.com/feed",  # Roads & Kingdoms
    "https://www.smithsonianmag.com/rss/travel/",  # Smithsonian Magazine - Travel
    "https://www.afar.com/feed/atom",  # AFAR
)

# Category 3: AP & US City/State Local News Feeds
# A curated list of the primary news source from each US state.
# Most of these syndicate AP content heavily.
LOCAL_NEWS_FEEDS: Final[Tuple[str, ...]] = (
    "https://www.al.com/arc/outboundfeeds/rss/?outputType=xml",  # Alabama - AL.com
    "https://www.adn.com/arc/outboundfeeds/rss/",  # Alaska - Anchorage Daily News
    "https://www.azcentral.com/rss/news",  # Arizona - The Arizona Republic
    "https://www.arkansasonline.com/rss/headlines/",  # Arkansas - Arkansas Democrat-Gazette
    "https://www.latimes.com/index.rss",  # California - Los Angeles Times
    "https://www.denverpost.com/feed/",  # Colorado - The Denver Post
    "https://www.courant.com/arcio/rss/",  # Connecticut - Hartford Courant
    "https://www.delawareonline.com/rss/news",  # Delaware - The News Journal
    "https://www.tampabay.com/arc/outboundfeeds/rss/category/news/?outputType=xml",  # Florida - Tampa Bay Times
    "https://www.ajc.com/arc/outboundfeeds/rss/",  # Georgia - The Atlanta Journal-Constitution
    "https://www.staradvertiser.com/feed/",  # Hawaii - Honolulu Star-Advertiser
    "https://www.idahostatesman.com/news/rss/",  # Idaho - Idaho Statesman
    "https://www.chicagotribune.com/rss",  # Illinois - Chicago Tribune
    "https://www.indystar.com/rss/news",  # Indiana - The Indianapolis Star
    "https://www.desmoinesregister.com/rss/news",  # Iowa - The Des Moines Register
    "https://www.kansas.com/news/rss/",  # Kansas - The Wichita Eagle
    "https://www.courier-journal.com/rss/news",  # Kentucky - The Courier-Journal
    "https://www.theadvocate.com/search/?f=rss&t=article&c=news&l=50",  # Louisiana - The Advocate
    "https://www.pressherald.com/feed/",  # Maine - Portland Press Herald
    "https://www.baltimoresun.com/rss/",  # Maryland - The Baltimore Sun
    "https://www.bostonglobe.com/feed",  # Massachusetts - The Boston Globe
    "https://www.freep.com/rss/news",  # Michigan - Detroit Free Press
    "https://www.startribune.com/rss/",  # Minnesota - Star Tribune
    "https://www.clarionledger.com/rss/news",  # Mississippi - Clarion Ledger
    "https://www.stltoday.com/search/?f=rss&t=article&c=news&l=50",  # Missouri - St. Louis Post-Dispatch
    "https://billingsgazette.com/search/?f=rss&t=article&c=news&l=50",  # Montana - Billings Gazette
    "https://omaha.com/search/?f=rss&t=article&c=news&l=50",  # Nebraska - Omaha World-Herald
    "https://www.reviewjournal.com/feed/",  # Nevada - Las Vegas Review-Journal
    "https://www.unionleader.com/search/?f=rss&t=article&c=news&l=50",  # New Hampshire - Union Leader
    "https://www.nj.com/arc/outboundfeeds/rss/?outputType=xml",  # New Jersey - NJ.com
    "https://www.abqjournal.com/feed",  # New Mexico - Albuquerque Journal
    "https://www.nytimes.com/svc/collections/v1/publish/www.nytimes.com/section/nyregion/rss.xml",  # New York - NYT NY Region
    "https://www.newsobserver.com/news/rss/",  # North Carolina - The News & Observer
    "https://www.inforum.com/news/rss",  # North Dakota - The Forum of Fargo-Moorhead
    "https://www.dispatch.com/rss/news",  # Ohio - The Columbus Dispatch
    "https://oklahoman.com/feed",  # Oklahoma - The Oklahoman
    "https://www.oregonlive.com/arc/outboundfeeds/rss/",  # Oregon - The Oregonian
    "https://www.inquirer.com/arc/outboundfeeds/rss/category/news/",  # Pennsylvania - The Philadelphia Inquirer
    "https://www.providencejournal.com/rss/news",  # Rhode Island - The Providence Journal
    "https://www.postandcourier.com/search/?f=rss&t=article&c=news&l=50",  # South Carolina - The Post and Courier
    "https://www.argusleader.com/rss/news",  # South Dakota - Argus Leader
    "https://www.tennessean.com/rss/news",  # Tennessee - The Tennessean
    "https://www.dallasnews.com/feed",  # Texas - The Dallas Morning News
    "https://www.sltrib.com/arc/outboundfeeds/rss/?outputType=xml",  # Utah - The Salt Lake Tribune
    "https://vtdigger.org/feed/",  # Vermont - VTDigger
    "https://richmond.com/search/?f=rss&t=article&c=news&l=50",  # Virginia - Richmond Times-Dispatch
    "https://www.seattletimes.com/feed/",  # Washington - The Seattle Times
    "https://www.wvgazettemail.com/search/?f=rss&t=article&c=news&l=50",  # West Virginia - Charleston Gazette-Mail
    "https://www.jsonline.com/rss/news",  # Wisconsin - Milwaukee Journal Sentinel
    "https://www.wyomingnews.com/news/rss.xml",  # Wyoming - Wyoming Tribune Eagle
)


def generate_file(output_filename: str = "discovery_rss_generated.py"):
    """Generates the Python file with the structured RSS feed list."""
    print(f"Generating new feed file: {output_filename}...")

    all_feeds = [
        ("# --- AP & Music Journalism ---", MUSIC_FEEDS),
        ("# --- AP & Tourist Journalism (Travel) ---", TRAVEL_FEEDS),
        ("# --- AP & US City/State Local News Feeds ---", LOCAL_NEWS_FEEDS),
    ]

    total_feeds = sum(len(feeds) for _, feeds in all_feeds)

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            # Write the header
            f.write("from typing import Final\n\n")
            f.write("RSS_FEEDS: Final[tuple[str, ...]] = (\n")

            # Write each category and its feeds
            for comment, feeds in all_feeds:
                f.write(f"    {comment}\n")
                for url in feeds:
                    f.write(f'    "{url}",\n')
                f.write("\n")  # Add a blank line between sections

            # Write the closing parenthesis
            f.write(")\n")

        print("-" * 40)
        print("✅ Success!")
        print(f"   Created '{os.path.abspath(output_filename)}'")
        print(f"   Total feeds generated: {total_feeds}")
        print("-" * 40)

    except IOError as e:
        print(f"❌ Error: Could not write to file '{output_filename}'. Reason: {e}")


if __name__ == "__main__":
    generate_file()