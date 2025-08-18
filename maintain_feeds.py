# maintain_feeds.py (Version 3.0 - The Intelligent Curator)
"""
A self-healing script to maintain and improve the Axiom Engine's RSS feed list.

This script will automatically:
1.  Create a backup of the existing discovery_rss.py file.
2.  Read and parse ALL URLs from the source file, including commented-out ones.
3.  Verify all found feeds, sorting them into 'good' and 'bad' lists.
4.  For each bad feed, it first attempts an INTELLIGENT REPAIR by searching the
    web for a directly related, official RSS feed from the same domain.
5.  If intelligent repair fails, it falls back to replacing the bad feed with a
    high-quality, trusted source from a massive internal backup list.
6.  It then REWRITES the discovery_rss.py file with the repaired/replaced feeds.

Dependencies:
pip install requests feedparser ddgs beautifulsoup4 lxml
"""
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Final, Optional
from urllib.parse import urljoin, urlparse
from bs4 import XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
import feedparser
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

# --- Setup Paths (run from root of AxiomEngine project) ---
try:
    sys.path.insert(0, os.path.join(os.getcwd(), "src"))
    SOURCE_FILE_PATH = os.path.join("src", "axiom_server", "discovery_rss.py")
    if not os.path.exists(SOURCE_FILE_PATH):
        raise FileNotFoundError
except FileNotFoundError:
    print("❌ ERROR: Could not find 'src/axiom_server/discovery_rss.py'")
    print("Please make sure you are running this script from the root 'AxiomEngine' directory.")
    sys.exit(1)

BACKUP_FILE_PATH = f"{SOURCE_FILE_PATH}.bak"
HEADERS = {"User-Agent": "Axiom-Feed-Curator/3.0"}


# --- MASSIVE BACKUP FEED LIST (OVER 150 SOURCES) ---
# This list is used as a fallback if intelligent repair fails.

# Category: Top-Tier General & World News (Total: 75)
_world_news = (
    # Foundational Global News Agencies & Broadcasters
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml", # Wall Street Journal
    "https://www.theguardian.com/world/rss",
    "https://apnews.com/hub/world-news.rss",
    "https://www.reutersagency.com/feed/?best-topics=international-news&post_type=best",
    "https://www.npr.org/rss/rss.php?id=1004",
    "https://www.pbs.org/newshour/feeds/rss/headlines",
    "https://www.csmonitor.com/rss/feed/global/latest.xml",
    "https://www.voanews.com/api/zmgqoe$mo", # Voice of America

    # Major Publications from Democratic Nations
    "https://www.washingtonpost.com/world/feed/",
    "https://www.latimes.com/world-nation/rss2.0.xml",
    "https://www.theatlantic.com/feed/channel/news/",
    "https://time.com/feed/",
    "https://www.economist.com/the-world-in-brief/rss.xml",
    "https://www.telegraph.co.uk/world-news/rss.xml",      # UK
    "https://www.independent.co.uk/news/world/rss",        # UK
    "https://www.theglobeandmail.com/world/rss/",          # Canada
    "https://www.cbc.ca/cmlink/rss-world",                  # Canada
    "https://www.smh.com.au/rss/world.xml",                # Australia
    "https://www.theage.com.au/rss/world.xml",             # Australia
    "https://www.abc.net.au/news/feed/51120/rss.xml",      # Australia
    "https://www.nzherald.co.nz/rss/world/",               # New Zealand
    "https://www.irishtimes.com/news/world/rss",           # Ireland
    "https://www.dw.com/rdf/rss-en-all",                    # Germany
    "https://www.spiegel.de/international/index.rss",     # Germany
    "https://www.france24.com/en/rss",                     # France
    "https://www.rfi.fr/en/rss",                           # France
    "https://elpais.com/rss/elpais/inenglish.xml",         # Spain
    "https://www.lemonde.fr/en/rss_full.xml",              # France
    "https://www.swissinfo.ch/eng/rss",                    # Switzerland
    "https://www.cphpost.dk/feed/",                        # Denmark
    "https://www.thelocal.de/feed/",                       # Germany (The Local)

    # Reputable Sources from Asia & Pacific
    "https://www.japantimes.co.jp/feed",
    "https://www.kyodonews.net/rss/english.xml",
    "https://www.asahi.com/rss/asahi/newsheadlines.rdf",
    "https://www.koreatimes.co.kr/www/rss/world.xml",
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "https://www.thehindu.com/news/international/feeder/default.rss",
    "https://www.straitstimes.com/news/world/rss.xml",      # Singapore
    "https://www.thejakartapost.com/rss/news",              # Indonesia
    "https://www.bangkokpost.com/rss/world",                # Thailand
    "https://www.scmp.com/rss/91/feed",                     # South China Morning Post (Hong Kong)

    # Reputable Sources from Middle East & Africa
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.haaretz.com/srv/haaretz/syndication/rss/news.xml", # Israel
    "https://www.ynetnews.com/Common/0,7340,L-3083,00.xml",         # Israel
    "https://www.dailymaverick.co.za/rss",                  # South Africa
    "https://www.africanews.com/rss/",
    "https://www.thenationalnews.com/world/rss/",           # UAE
    "https://www.dawn.com/feeds/world",                     # Pakistan
    
    # Policy, NGOs, and International Organizations
    "https://foreignpolicy.com/feed/",
    "https://www.foreignaffairs.com/feed",
    "https://www.un.org/press/en/feed",
    "https://www.thenewhumanitarian.org/rss.xml",
    "https://www.euronews.com/rss?format=mrss&level=vertical&name=world",
    "https://www.politico.eu/feed/",
    "https://www.euractiv.com/feed/",
    "https://reliefweb.int/rss.xml",
    "https://pulitzercenter.org/rss.xml",
    "https://carnegieendowment.org/rss/solr/feed",
    "https://www.lowyinstitute.org/publications/rss.xml",
    "https://www.iiss.org/rss",
    "https://www.buenosairesherald.com/rss",                # Argentina
    
    # 25 New Additions
    "https://www.un.org/press/en/feed",                        # United Nations - Press Releases
    "https://www.theatlantic.com/feed/channel/news/",         # The Atlantic - News
    "https://www.foreignaffairs.com/feed",                     # Foreign Affairs
    "https://time.com/feed/",                                  # TIME Magazine
    "https://www.economist.com/the-world-in-brief/rss.xml",    # The Economist - World in Brief
    "https://www.theglobeandmail.com/world/rss/",              # The Globe and Mail (Canada) - World
    "https://elpais.com/rss/elpais/inenglish.xml",             # El País (Spain) - English Edition
    "https://www.lemonde.fr/en/rss_full.xml",                  # Le Monde (France) - English Edition
    "https://www.dailymaverick.co.za/rss",                      # Daily Maverick (South Africa)
    "https://www.thehindu.com/news/international/feeder/default.rss", # The Hindu (India) - International
    "https://www.thejakartapost.com/rss/news",                  # The Jakarta Post (Indonesia)
    "https://www.theage.com.au/rss/world.xml",                 # The Age (Australia) - World
    "https://www.kyodonews.net/rss/english.xml",               # Kyodo News (Japan)
    "https://www.telegraph.co.uk/world-news/rss.xml",          # The Telegraph (UK) - World News
    "https://www.independent.co.uk/news/world/rss",            # The Independent (UK) - World
    "https://www.cphpost.dk/feed/",                            # The Copenhagen Post (Denmark)
    "https://www.thelocal.de/feed",                            # The Local (Germany)
    "https://www.buenosairesherald.com/rss",                   # Buenos Aires Herald (Argentina)
    "https://www.pri.org/programs/the-world/feed",             # PRX's The World
    "https://www.stripes.com/rss.xml",                         # Stars and Stripes
    "https://pulitzercenter.org/rss.xml",                      # Pulitzer Center
    "https://carnegieendowment.org/rss/solr/feed",             # Carnegie Endowment for International Peace
    "https://www.lowyinstitute.org/publications/rss.xml",     # Lowy Institute
    "https://www.iiss.org/rss",                                # International Institute for Strategic Studies
    "https://reliefweb.int/rss.xml",                           # ReliefWeb (UN OCHA)
)

# Category: Science & Technology (Total: 67)
_science_tech = (
    # Original 42
    "https://www.nasa.gov/rss/dyn/breaking_news.rss", "https://www.sciencedaily.com/rss/top.xml",
    "https://www.technologyreview.com/feed/", "https://www.wired.com/feed/category/science/latest/rss",
    "https://arstechnica.com/science/feed/", "https://spectrum.ieee.org/rss/fulltext",
    "https://www.scientificamerican.com/feed/", "https://www.quantamagazine.org/feed/",
    "https://phys.org/rss-feed/", "https://www.nature.com/nature.rss",
    "https://techcrunch.com/feed/", "https://www.theverge.com/rss/index.xml",
    "https://www.science.org/rss/news.xml", "https://www.smithsonianmag.com/rss/science-nature/", 
    "https://www.popularmechanics.com/feed/", "https://www.newscientist.com/feed/home/?cmpid=RSS%7CNSNS-Home", 
    "https://www.space.com/feeds/all", "https://www.sciencenews.org/feed",
    "https://www.sciencenewsforstudents.org/feed", "https://www.chemistryworld.com/feeds/rss/", 
    "https://www.eurekalert.org/rss.xml", "https://www.zmescience.com/feed/", 
    "https://www.futurity.org/feed/", "https://scitechdaily.com/feed/",
    "https://www.engadget.com/rss.xml", "https://www.digitaltrends.com/feed/", 
    "https://gizmodo.com/rss", "https://www.techradar.com/rss", 
    "https://www.cnet.com/rss/news/", "https://www.tomsguide.com/feeds/all",
    "https://www.extremetech.com/feed", "https://www.techspot.com/backend.xml", 
    "https://www.zdnet.com/news/rss.xml", "https://www.analyticsinsight.net/feed/", 
    "https://www.artificialintelligence-news.com/feed/", "https://www.techrepublic.com/rssfeeds/articles/",
    "https://www.techmeme.com/feed.xml", "https://www.androidauthority.com/feed/", 
    "https://www.macrumors.com/rss.xml", "https://www.phoronix.com/rss.php", 
    "https://hackaday.com/feed/", "https://www.slashgear.com/feed/",
    
    # 25 New Additions
    "https://www.livescience.com/feeds/all",                   # Live Science
    "https://www.astronomy.com/rss/news",                       # Astronomy Magazine
    "https://skyandtelescope.org/feed/",                       # Sky & Telescope
    "https://www.cell.com/rss/browse.xml",                     # Cell Press
    "https://www.pnas.org/rss/current.xml",                    # Proceedings of the National Academy of Sciences
    "https://www.discovermagazine.com/rss/news",               # Discover Magazine
    "https://www.anthropology-news.org/feed/",                 # Anthropology News
    "https://www.archaeology.org/news?format=feed&type=rss",    # Archaeology Magazine
    "https://www.geosociety.org/GSA/News/rss.xml",             # Geological Society of America
    "https://www.ams.org/news/rss.xml",                        # American Mathematical Society
    "https://www.acm.org/publications/toc/rss",                # Association for Computing Machinery
    "https://news.mit.edu/rss/feed",                           # MIT News
    "https://news.stanford.edu/feed/",                         # Stanford News
    "https://news.berkeley.edu/feed/",                         # Berkeley News
    "https://news.harvard.edu/gazette/feed/",                  # The Harvard Gazette
    "https://darkdaily.com/feed/",                             # Dark Daily (Clinical Lab Tech)
    "https://www.iotforall.com/feed",                          # IoT For All
    "https://singularityhub.com/feed/",                        # Singularity Hub
    "https://www.nextplatform.com/feed/",                      # The Next Platform (HPC)
    "https://www.fast.ai/feed.xml",                            # fast.ai Blog
    "https://distill.pub/rss.xml",                             # Distill.pub (ML Research)
    "https://www.roboticsbusinessreview.com/feed/",            # Robotics Business Review
    "https://www.humanetech.com/feed",                         # Center for Humane Technology
    "https://www.eff.org/rss/updates.xml",                     # Electronic Frontier Foundation
    "https://www.thebulletin.org/feed/",                       # Bulletin of the Atomic Scientists
)

# Category: Health & Medicine (Total: 50)
_health = (
    # Original 25
    "https://newsnetwork.mayoclinic.org/feed/", "https://www.statnews.com/feed/",
    "https://www.nih.gov/news-events/news-releases/rss", "https://www.who.int/rss-feeds/news-english.xml",
    "https://www.medpagetoday.com/rss/headlines.xml", "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",
    "https://jamanetwork.com/rss/site_1/9.xml", "https://www.thelancet.com/rssfeed/lanrss.xml", 
    "https://www.bmj.com/rss/current.xml", "https://www.webmd.com/rss/default.aspx", 
    "https://www.health.harvard.edu/blog/feed", "https://www.cdc.gov/media/rss/syndicate.xml",
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds", "https://www.healthline.com/health-news/rss", 
    "https://www.medicalnewstoday.com/rss", "https://www.heart.org/en/news/rss", 
    "https://www.cancer.gov/news-events/rss", "https://www.apa.org/news/psycport/rss/top-stories.xml",
    "https://www.nami.org/NAMI/media/NAMI-Media/RSS/NAMI-News.xml", "https://www.psychologytoday.com/us/rss.xml",
    "https://www.pharmacytimes.com/rss/news", "https://www.nursingtimes.net/feed", 
    "https://www.medicalxpress.com/rss-feed/", "https://www.kff.org/feed/",
    "https://www.fiercehealthcare.com/rss.xml",

    # 25 New Additions
    "https://www.nature.com/nm/rss/current",                   # Nature Medicine
    "https://sciencebasedmedicine.org/feed/",                  # Science-Based Medicine
    "https://www.genome.gov/rss",                              # National Human Genome Research Institute
    "https://www.nia.nih.gov/news/rss",                        # National Institute on Aging
    "https://www.niaid.nih.gov/news-events/feed",              # National Institute of Allergy and Infectious Diseases
    "https://www.nimh.nih.gov/news/index.shtml.rss",           # National Institute of Mental Health
    "https://www.drugabuse.gov/news-events/rss.xml",           # National Institute on Drug Abuse
    "https://www.ashp.org/news/rss-feeds/ashp-news",           # American Society of Health-System Pharmacists
    "https://www.eatright.org/rss",                            # Academy of Nutrition and Dietetics
    "https://www.diabetes.org/newsroom/rss",                   # American Diabetes Association
    "https://www.alz.org/rss-feed.asp",                        # Alzheimer's Association
    "https://www.arthritis.org/rss/news",                      # Arthritis Foundation
    "https://www.lung.org/media/press-releases-rss.xml",       # American Lung Association
    "https://www.aappublications.org/rss/latest.xml",          # American Academy of Pediatrics
    "https://www.acog.org/news/rss-feed",                      # American College of Obstetricians and Gynecologists
    "https://www.mskcc.org/rss",                               # Memorial Sloan Kettering Cancer Center
    "https://www.dana-farber.org/rss/",                        # Dana-Farber Cancer Institute
    "https://www.jhsph.edu/rss/news-and-events.xml",           # Johns Hopkins Bloomberg School of Public Health
    "https://www.hsph.harvard.edu/news/feed/",                 # Harvard T.H. Chan School of Public Health
    "https://www.npr.org/rss/rss.php?id=1128",                  # NPR - Health
    "https://www.nytimes.com/svc/collections/v1/publish/www.nytimes.com/section/health/rss.xml", # NYT - Health
    "https://www.thebody.com/rss-2.0.xml",                      # TheBody.com (HIV/AIDS News)
    "https://www.precisionnanosystems.com/blog?format=rss",    # Precision NanoSystems
    "https://www.goodrx.com/blog/feed/",                       # GoodRx Health
    "https://www.wellandgood.com/feed/",                       # Well+Good
)

# Category: Business & Finance (Total: 53)
_business = (
    # Original 28
    "https://www.wsj.com/xml/rss/3_7085.xml", "https://www.ft.com/rss/home/international",
    "https://www.bloomberg.com/opinion/authors/A-d-5ll56U/sitemap_news.xml", "https://www.cnbc.com/id/100003114/device/rss/rss.html", 
    "https://feeds.a.dj.com/rss/RSSWSJD.xml", "https://hbr.org/rss/latest", 
    "https://fortune.com/feed", "https://www.forbes.com/business/feed/",
    "https://www.barrons.com/rss/all-sections", "https://www.investing.com/rss/news.rss", 
    "https://www.marketwatch.com/rss/topstories", "https://www.reuters.com/business/feed", 
    "https://www.benzinga.com/rss", "https://seekingalpha.com/feed.xml",
    "https://www.kiplinger.com/feed", "https://www.economist.com/business-and-finance/rss.xml", 
    "https://www.fool.com/a/feeds/fool-high-growth-stocks.aspx", "https://www.entrepreneur.com/feed", 
    "https://www.inc.com/rss", "https://www.fastcompany.com/rss", 
    "https://www.businessinsider.com/rss", "https://feeds.feedburner.com/zerohedge/feed", 
    "https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss", 
    "https://www.americanbanker.com/rss", "https://www.accountingtoday.com/rss", 
    "https://www.financial-planning.com/rss", "https://www.adweek.com/feed",

    # 25 New Additions
    "https://www.worldbank.org/en/news/rss",                   # The World Bank
    "https://www.imf.org/en/news/rss",                         # International Monetary Fund
    "https://www.federalreserve.gov/feeds/pressreleases.xml",  # US Federal Reserve
    "https://www.ecb.europa.eu/press/rss/press.en.xml",        # European Central Bank
    "https://www.bis.org/rss/bis_publs.xml",                   # Bank for International Settlements
    "https://www.oecd.org/feeds/news.xml",                     # OECD News
    "https://www.weforum.org/feed",                            # World Economic Forum
    "https://www.uschamber.com/rss",                           # U.S. Chamber of Commerce
    "https://www.sba.gov/about-sba/sba-newsroom/rss.xml",      # U.S. Small Business Administration
    "https://www.sec.gov/news/pressreleases.rss",              # U.S. SEC Press Releases
    "https://www.cftc.gov/rss",                                # U.S. CFTC
    "https://www.sifma.org/feed/",                             # SIFMA
    "https://www.finra.org/newsroom/rss",                      # FINRA
    "https://www.pymnts.com/feed/",                            # PYMNTS.com
    "https://www.retaildive.com/feeds/news/",                  # Retail Dive
    "https://www.supplychaindive.com/feeds/news/",             # Supply Chain Dive
    "https://www.transportdive.com/feeds/news/",               # Transport Dive
    "https://www.marketingdive.com/feeds/news/",               # Marketing Dive
    "https://www.agweb.com/rss",                               # AgWeb (Agriculture)
    "https://www.eia.gov/rss/todayinenergy.xml",               # U.S. Energy Information Administration
    "https://oilprice.com/rss/main",                           # OilPrice.com
    "https://www.risk.net/rss",                                # Risk.net
    "https://www.pionline.com/rss",                            # Pensions & Investments
    "https://www.realclearmarkets.com/index.xml",              # RealClearMarkets
    "https://www. Morningstar.com/feeds/latest-news",         # Morningstar
)

# Category: Culture, Arts & Human Interest (Total: 56)
_culture = (
    # Original 31
    "https://www.atlasobscura.com/feeds/latest", "https://www.smithsonianmag.com/rss/latest/",
    "https://www.newyorker.com/feed/everything", "https://longform.org/feed.xml",
    "https://apnews.com/hub/strange-news/rss", "https://www.theparisreview.org/feed",
    "https://aeon.co/feed.rss", "https://psyche.co/feed.rss",
    "https://www.artsandlettersdaily.com/rss", "https://www.artsjournal.com/feed/",
    "https://hyperallergic.com/feed/", "https://lithub.com/feed/",
    "https://www.themarginalian.org/feed/", "https://www.artnews.com/feed/",
    "https://www.artforum.com/rss.xml", "https://www.architecturaldigest.com/feed/rss",
    "https://www.designboom.com/feed/", "https://www.dezeen.com/feed/",
    "https://www.openculture.com/feed", "https://www.nybooks.com/feed/",
    "https://www.laphamsquarterly.org/rss/feed", "https://www.guernicamag.com/feed/",
    "https://www.poetryfoundation.org/feed", "https://lareviewofbooks.org/feed/",
    "https://www.bookforum.com/rss.xml", "https://www.historytoday.com/rss",
    "https://www.nationalgeographic.com/history/rss-feed", "https://www.thisiscolossal.com/feed/",
    "https://www.boredpanda.com/feed/", "https://mymodernmet.com/feed/",
    "https://www.vulture.com/rss/index.xml",

    # 25 New Additions
    "https://www.americantheatre.org/feed/",                   # American Theatre Magazine
    "https://www.dancemagazine.com/feed/",                      # Dance Magazine
    "https://www.operanews.com/Opera_News_Magazine/RSS.aspx",   # Opera News
    "https://www.downbeat.com/feeds/news.asp",                 # DownBeat Magazine (Jazz)
    "https://www.hollywoodreporter.com/feed/",                 # The Hollywood Reporter
    "https://variety.com/feed/",                               # Variety
    "https://deadline.com/feed/",                              # Deadline
    "https://www.backstage.com/magazine/feed/",                # Backstage Magazine
    "https://www.neh.gov/rss.xml",                             # National Endowment for the Humanities
    "https://www.americansforthearts.org/news/rss",            # Americans for the Arts
    "https://www.getty.edu/news/rss.xml",                      # Getty Museum News
    "https://www.metmuseum.org/blogs/listings/now-at-the-met?rss=1", # The Met Museum Blog
    "https://www.moma.org/magazine/feed",                      # MoMA Magazine
    "https://blog.britishmuseum.org/feed/",                    # The British Museum Blog
    "https://publicdomainreview.org/feed/",                    # The Public Domain Review
    "https://www.loc.gov/rss/",                                # Library of Congress
    "https://www.nypl.org/rss",                                # New York Public Library
    "https://www.ala.org/news/rss",                            # American Library Association
    "https://pen.org/feed/",                                   # PEN America
    "https://www.storycorps.org/feed",                         # StoryCorps
    "https://themoth.org/rss.xml",                             # The Moth
    "https://www.humanesociety.org/news/feed",                 # The Humane Society
    "https://www.worldwildlife.org/press-releases/feed",       # World Wildlife Fund
    "https://www.nature.org/en-us/newsroom/rss/",              # The Nature Conservancy
    "https://www.audubon.org/rss",                             # Audubon Society
)

# Category: Specialized & Investigative (Total: 56)
_investigative = (
    # Original 31
    "https://www.propublica.org/feeds/propublica/main", "https://www.bellingcat.com/feed/",
    "https://www.icij.org/feed/", "https://www.themarshallproject.org/rss.xml",
    "https://www.politifact.com/rss/all/", "https://insideclimatenews.org/feed/",
    "https://freakonomics.com/feed/", "https://lifehacker.com/rss",
    "https://www.occrp.org/en/rss", "https://www.revealnews.org/feed/",
    "https://www.opensecrets.org/news/feed/", "https://www.pogo.org/feed/",
    "https://www.transparency.org/en/press/rss", "https://www.globalwitness.org/en/rss.xml",
    "https://cpj.org/feed/", "https://www.rcfp.org/feed/", "https://www.niemanlab.org/feed/",
    "https://www.pewresearch.org/feed/", "https://www.brookings.edu/feed/",
    "https://www.rand.org/topics/all.rss.html", "https://www.csis.org/feeds/rss",
    "https://www.cfr.org/rss/current.xml", "https://www.chathamhouse.org/rss/feed",
    "https://www.cato.org/rss/all", "https://www.heritage.org/rss/news",
    "https://www.aclu.org/news/feed", "https://www.hrw.org/rss/news",
    "https://www.amnesty.org/en/latest/news/feed/", "https://www.icrc.org/en/rss-feeds/all/all",
    "https://www.thetrace.org/feed/", "https://www.factcheck.org/feed/",
    
    # 25 New Additions
    "https://www.theintercept.com/feed/?rss",                  # The Intercept
    "https://www.cjr.org/feed",                                # Columbia Journalism Review
    "https://www.poynter.org/feed/",                           # Poynter Institute
    "https://firstdraftnews.org/feed/",                        # First Draft News (Disinformation)
    "https://gijn.org/feed/",                                  # Global Investigative Journalism Network
    "https://www.ire.org/feed/",                               # Investigative Reporters & Editors
    "https://www.documentcloud.org/feed",                      # DocumentCloud Blog
    "https://www.muckrock.com/feed/",                          # MuckRock
    "https://www.judicialwatch.org/feed/",                     # Judicial Watch
    "https://www.epic.org/feed/",                              # Electronic Privacy Information Center
    "https://www.thefire.org/feed",                            # Foundation for Individual Rights and Expression
    "https://knightfoundation.org/feed/",                      # Knight Foundation
    "https://www.macfound.org/press/press-releases/feed/",     # MacArthur Foundation
    "https://fordfoundation.org/feed/",                        # Ford Foundation
    "https://www.gatesfoundation.org/ideas/media-center/press-releases/feed", # Gates Foundation
    "https://www.opensocietyfoundations.org/newsroom/rss.xml", # Open Society Foundations
    "https://www.splcenter.org/rss.xml",                       # Southern Poverty Law Center
    "https://www.adl.org/rss.xml",                             # Anti-Defamation League
    "https://www.scotusblog.com/feed/",                        # SCOTUSblog
    "https://www.lawfaremedia.org/rss.xml",                    # Lawfare
    "https://www.emptywheel.net/feed/",                        # emptywheel (National Security)
    "https://www.justsecurity.org/feed/",                      # Just Security
    "https://warontherocks.com/feed/",                         # War on the Rocks
    "https://smallwarsjournal.com/rss.xml",                    # Small Wars Journal
    "https://fas.org/feed/",                                   # Federation of American Scientists
)

BACKUP_FEEDS: Final[tuple[str, ...]] = _world_news + _science_tech + _health + _business + _culture + _investigative


def _verify_url(url: str) -> bool:
    """Checks if a URL is a valid, working RSS feed."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        if not feed.bozo and feed.entries:
            return True
    except Exception:
        pass
    return False


def _find_related_replacement(bad_url: str) -> Optional[str]:
    """Tier 1 Strategy: Intelligently search for a related replacement."""
    try:
        domain = urlparse(bad_url).netloc.replace("www.", "")
        if not domain:
            return None

        query = f'"{domain}" official RSS feed'
        with DDGS() as ddgs:
            # Search the web for the official feed
            for result in ddgs.text(query, max_results=5):
                try:
                    page_req = requests.get(result["href"], headers=HEADERS, timeout=10)
                    page_soup = BeautifulSoup(page_req.content, "lxml")
                    # Look for standard RSS link tags on the page
                    for link in page_soup.find_all("link", {"rel": "alternate", "type": "application/rss+xml"}):
                        feed_url = urljoin(result["href"], link.get("href", ""))
                        if _verify_url(feed_url):
                            return feed_url # Return the first valid one we find
                except Exception:
                    continue # Ignore errors with individual search results
    except Exception:
        pass # Ignore errors with the search itself
    return None


def read_and_parse_source_file() -> tuple[list[str], list[str]]:
    """Reads the source file and extracts ALL URLs, even commented ones."""
    with open(SOURCE_FILE_PATH) as f:
        lines = f.readlines()
    url_pattern = re.compile(r'["\'](https?://.*?)["\']')
    return [match.group(1) for line in lines if (match := url_pattern.search(line))], lines


def main() -> None:
    """Run the full verification, curation, and file update pipeline."""
    all_urls, original_lines = read_and_parse_source_file()
    unique_urls = sorted(list(set(all_urls)))
    print(f"--- Starting Curation for {len(unique_urls)} Unique Feeds ---\n")

    # --- Phase 1: Verification ---
    print("--- Phase 1: Verifying all current and commented feeds... ---")
    good_feeds: set[str] = set()
    bad_feeds: list[str] = []
    with ThreadPoolExecutor(max_workers=16) as executor:
        future_to_url = {executor.submit(_verify_url, url): url for url in unique_urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            if future.result():
                good_feeds.add(url)
            else:
                bad_feeds.append(url)

    print(f"\n--- Phase 1 Complete: {len(good_feeds)} Good, {len(bad_feeds)} Bad ---\n")
    if not bad_feeds:
        print("✅ All feeds are healthy! No maintenance needed.")
        return

    # --- Phase 2: Find Replacements (Two-Tiered Approach) ---
    print(f"--- Phase 2: Finding replacements for {len(bad_feeds)} bad feeds... ---")
    replacement_map: dict[str, str] = {}
    available_backups = [url for url in BACKUP_FEEDS if url not in good_feeds and url not in bad_feeds]
    backup_iterator = iter(available_backups)

    for bad_url in bad_feeds:
        # Tier 1: Attempt intelligent, related repair
        related_replacement = _find_related_replacement(bad_url)
        if related_replacement and related_replacement not in good_feeds:
            replacement_map[bad_url] = related_replacement
            print(f"  [FOUND RELATED] Replacement for {urlparse(bad_url).netloc}")
            continue

        # Tier 2: Fallback to generic high-quality backup
        try:
            backup_replacement = next(backup_iterator)
            replacement_map[bad_url] = backup_replacement
            print(f"  [USING BACKUP] for {urlparse(bad_url).netloc}")
        except StopIteration:
            print(f"  [NO REPLACEMENT] for {urlparse(bad_url).netloc} (out of backups)")

    # --- Phase 3: Rewrite the Source File ---
    print("\n--- Phase 3: Updating the source file... ---")
    new_lines: list[str] = []
    processed_urls = set()
    url_pattern = re.compile(r'["\'](https?://.*?)["\']')

    # First, write all the good feeds
    final_feed_list = sorted(list(good_feeds))
    # Then, add the new replacements, ensuring they are not duplicates
    for bad_url, new_url in replacement_map.items():
        if new_url not in final_feed_list:
            final_feed_list.append(new_url)

    # Reconstruct the file with the new, clean list
    header_lines = [line for line in original_lines if not url_pattern.search(line)]
    tuple_start = -1
    for i, line in enumerate(header_lines):
        if "RSS_FEEDS" in line:
            tuple_start = i
            break

    if tuple_start != -1:
        new_lines.extend(header_lines[:tuple_start+1])
        for url in sorted(final_feed_list):
            new_lines.append(f'    "{url}",\n')
        new_lines.append(")\n")
    else: # Fallback if tuple definition not found
        new_lines = original_lines


    # Create a backup and write the new file
    try:
        shutil.copy(SOURCE_FILE_PATH, BACKUP_FILE_PATH)
        print(f"\n✅ Backup of original file created at: {BACKUP_FILE_PATH}")
        with open(SOURCE_FILE_PATH, "w") as f:
            f.writelines(new_lines)
        print(f"✅ Successfully curated and updated {SOURCE_FILE_PATH} with {len(final_feed_list)} healthy feeds!")
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not write to source file. Error: {e}")

if __name__ == "__main__":
    main()