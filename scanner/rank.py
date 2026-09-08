import re

CANON = {
 'akunacapital':'Akuna Capital','oldmissioncapital':'Old Mission Capital',
 'old-mission-capital':'Old Mission Capital','imc':'IMC Trading','jumptrading':'Jump Trading',
 'drweng':'DRW','chicagotrading':'Chicago Trading Company','belvederetrading':'Belvedere Trading',
 'vaticlabs':'Vatic Labs','janestreet':'Jane Street','pdtpartners':'PDT Partners',
 'sigmacomputing':'Sigma Computing','optiverus':'Optiver US','radixuniversity':'Radix Trading',
 'towerresearchcapital':'Tower Research Capital','vividseatsllc':'Vivid Seats',
 'gleanwork':'Glean','doordashusa':'DoorDash','tripactions':'Navan','sourcegraph91':'Sourcegraph',
 'hebbia-ai':'Hebbia','read-ai':'Read AI','mistral.ai':'Mistral AI','1password':'1Password',
 'shieldai':'Shield AI','shield-ai':'Shield AI','endeavorai.com':'Endeavor AI',
 '3redpartners':'3Red Partners','coreweave':'CoreWeave','togetherai':'Together AI',
 'scaleai':'Scale AI','xai':'xAI','motorolasolutions':'Motorola Solutions','motorola':'Motorola Solutions',
 'sproutsocial':'Sprout Social','project44':'project44','activecampaign':'ActiveCampaign',
 'grafanalabs':'Grafana Labs','planetscale':'PlanetScale','komodohealth':'Komodo Health',
 'flatironhealth':'Flatiron Health','vannevarlabs':'Vannevar Labs','appliedintuition':'Applied Intuition',
 'applied':'Applied Intuition','langchain':'LangChain','cerebras':'Cerebras Systems',
 'huggingface':'Hugging Face','doximity':'Doximity','upstart':'Upstart','m1finance':'M1 Finance',
 'g2':'G2','skydio':'Skydio','twosixtechnologies':'Two Six Technologies','notion':'Notion',
 'databricks':'Databricks','stripe':'Stripe','datadog':'Datadog','cloudflare':'Cloudflare',
 'anthropic':'Anthropic','openai':'OpenAI','perplexity':'Perplexity','cursor':'Anysphere (Cursor)',
 'harvey':'Harvey','abridge':'Abridge','sierra':'Sierra','cognition':'Cognition AI',
 'modal':'Modal','baseten':'Baseten','fireworks':'Fireworks AI','ramp':'Ramp','mercor':'Mercor',
 'decagon':'Decagon','writer':'Writer','linear':'Linear','replit':'Replit','supabase':'Supabase',
 'vercel':'Vercel','workos':'WorkOS','render':'Render','railway':'Railway','neon':'Neon',
 'roblox':'Roblox','affirm':'Affirm','robinhood':'Robinhood','coinbase':'Coinbase','brex':'Brex',
 'samsara':'Samsara','verkada':'Verkada','flexport':'Flexport','confluent':'Confluent',
 'snowflake':'Snowflake','mongodb':'MongoDB','elastic':'Elastic','twilio':'Twilio','okta':'Okta',
 'gitlab':'GitLab','instacart':'Instacart','lyft':'Lyft','airbnb':'Airbnb','dropbox':'Dropbox',
 'reddit':'Reddit','pinterest':'Pinterest','discord':'Discord','figma':'Figma','asana':'Asana',
 'duolingo':'Duolingo','celonis':'Celonis','appian':'Appian','workato':'Workato','tines':'Tines',
 'relativity':'Relativity Space','enova':'Enova International','groupon':'Groupon','zoro':'Zoro',
 'palantir':'Palantir','chainguard':'Chainguard','sofi':'SoFi','gemini':'Gemini','block':'Block',
 'gusto':'Gusto','mercury':'Mercury','betterment':'Betterment','marqeta':'Marqeta',
 'elevenlabs':'ElevenLabs','granola':'Granola','rogo':'Rogo','listenlabs':'Listen Labs',
 'anyscale':'Anyscale','synthesia':'Synthesia','vanta':'Vanta','persona':'Persona',
 'sardine':'Sardine','nabla':'Nabla','openevidence':'OpenEvidence','lovable':'Lovable',
 'browserbase':'Browserbase','e2b':'E2B','zocdoc':'Zocdoc','epirus':'Epirus','yugabyte':'YugabyteDB',
 'singlestore':'SingleStore','sumologic':'Sumo Logic','seatgeek':'SeatGeek','udemy':'Udemy',
 'squarespace':'Squarespace','riotgames':'Riot Games','newrelic':'New Relic','carta':'Carta',
 'braze':'Braze','oscar':'Oscar Health','quantcast':'Quantcast','virtu':'Virtu Financial',
 'cohere':'Cohere','typeface':'Typeface','toptal':'Toptal','linkedin':'LinkedIn',
 'chaosindustries':'CHAOS Industries',
}

def canon(n):
    n = str(n or '').strip()
    return CANON.get(n.lower(), n)

TRADING = re.compile(r"(trading|capital|securities|quant|jane street|imc|drw|optiver|"
    r"citadel|jump|akuna|belvedere|old mission|virtu|radix|tower research|voleon|five rings|"
    r"3red|maven|transmarket|blackedge|eagle seven|headlands|wolverine|group one|cboe|cme)", re.I)
AI_CO = re.compile(r"(ai\b|\.ai|anthropic|openai|databricks|scale|cerebras|langchain|cohere|"
    r"perplexity|cursor|anysphere|sierra|cognition|harvey|abridge|glean|mercor|decagon|writer|"
    r"fireworks|baseten|modal|together|anyscale|elevenlabs|hugging face|xai|coreweave|"
    r"nvidia|palantir|applied intuition|skild|torc|quantcast|litellm)", re.I)
AUTOMATION = re.compile(r"(uipath|automation anywhere|zapier|workato|tines|n8n|celonis|pega|"
    r"appian|camunda|temporal|retool|servicenow|automation|robotic)", re.I)
# companies that are not product-software employers for a new grad, or are wrong-discipline
POOR = re.compile(r"(staffing|9to9|cwill|datalab|interimage|hatch it|texas sports|arch aerial|"
    r"cybernetic labs|dark wolf|wyetech|captivation|general matter|freeform|revel|newsbreak|"
    r"bot auto|weride|aecom|astranis|rocket lab|spacex|true anomaly|nuclear company|gotion|"
    r"infleqtion|d-wave|micron|jabil|asm international|keysight|garmin|alarm\.com|viasat|"
    r"evertz|tesla|arcfield|sierra nevada|l3harris|rtx|northrop|general dynamics|leidos|caci|"
    r"booz|johns hopkins|hoffman|nrg energy|intertek|department|pmg|exelixis|iambic|"
    r"constellation energy|atlas energy|bertelsmann|payit|wellsky|cox automotive|ontic|"
    r"inductive automation|solace health|dtcc|walt disney|zebra|accenture|medical college|"
    r"university|college|hospital|pfizer|novartis|chevron|munters|andersen|thermo fisher|"
    r"johnson controls|teledyne|ferrovial|generac|semtech|vishay|polar semiconductor|nxp|"
    r"analog devices|cadence|marvell|\bups\b|boeing|caterpillar|relativity space|"
    r"rocket|aerospace|defense solutions)", re.I)


def score(company, posts):
    c = company
    best = max(posts, key=lambda p: ((p['smax'] or 0), p['opened'] or ''))
    s = 0.0
    why = []
    if AI_CO.search(c) or any(p['ai'] for p in posts):
        s += 25; why.append('AI/automation work')
    if AUTOMATION.search(c):
        s += 10; why.append('automation platform')
    if any(p['chicago'] for p in posts):
        s += 25; why.append('Chicago')
    if any(p['remote'] for p in posts):
        s += 25; why.append('remote')
    sm = max((p['smax'] or 0) for p in posts)
    if sm >= 200000:
        s += 20; why.append('$%dk top of band' % (sm // 1000))
    elif sm >= 150000:
        s += 15; why.append('$%dk top of band' % (sm // 1000))
    elif sm >= 120000:
        s += 10
    elif sm >= 95000:
        s += 5
    elif sm == 0:
        s += 4
    else:
        s -= 25; why.append('below $95k floor')
    newest = max((p['opened'] or '') for p in posts)
    if newest >= '2026-08-25':
        s += 20; why.append('opened in window')
    elif newest >= '2026-07-01':
        s += 12; why.append('live, opened recently')
    elif newest >= '2026-05-01':
        s += 5
    if TRADING.search(c):
        s += 12; why.append('qtkEngine is a direct match')
    if POOR.search(c):
        s -= 45; why.append('not a product-SWE fit')
    return s, best, why, sm, newest
