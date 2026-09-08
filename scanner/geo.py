import re
ST = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
      "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
STN = ("alabama alaska arizona arkansas california colorado connecticut delaware florida georgia "
       "hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts "
       "michigan minnesota mississippi missouri montana nebraska nevada new hampshire new jersey "
       "new mexico new york north carolina north dakota ohio oklahoma oregon pennsylvania "
       "rhode island south carolina south dakota tennessee texas utah vermont virginia "
       "washington west virginia wisconsin wyoming").split(", ")
STN = ["alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware",
 "florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana",
 "maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana",
 "nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina",
 "north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina",
 "south dakota","tennessee","texas","utah","vermont","virginia","washington","west virginia",
 "wisconsin","wyoming","district of columbia"]
US_CITY = ["san francisco","new york","seattle","austin","boston","chicago","denver","atlanta",
 "los angeles","san diego","san jose","palo alto","mountain view","sunnyvale","santa clara",
 "redmond","bellevue","dallas","houston","phoenix","miami","philadelphia","pittsburgh","detroit",
 "minneapolis","portland","salt lake city","nashville","charlotte","raleigh","durham","columbus",
 "cincinnati","cleveland","kansas city","st. louis","st louis","tampa","orlando","baltimore",
 "washington dc","arlington","mclean","reston","hartford","providence","richmond","boulder",
 "ann arbor","madison","milwaukee","des moines","omaha","oklahoma city","san antonio","el segundo",
 "culver city","irvine","san mateo","menlo park","cupertino","fremont","hillsboro","beaverton",
 "plano","irving","fort worth","jersey city","princeton","stamford","bentonville","peoria",
 "bloomington","normal","naperville","schaumburg","evanston","deerfield","northbrook","oak brook"]
FOREIGN_CODE = re.compile(r",\s*(KA|MH|TS|UP|DL|HR|GJ|WB|KL|PB|RJ|JK|AS|BR|UK|OD|CG|HP)\b")
FOREIGN_NAME = re.compile(r"\b(karnataka|maharashtra|telangana|tamil\s+nadu|kerala|gujarat|west\s+bengal|haryana|punjab,\s+india|rajasthan|odisha|uttar\s+pradesh)\b", re.I)
FOREIGN = re.compile(r"\b(india|bangalore|bengaluru|hyderabad|pune|gurgaon|noida|chennai|mumbai|delhi|"
 r"london|uk|united kingdom|england|scotland|glasgow|edinburgh|manchester|cambridge, uk|dublin|ireland|"
 r"berlin|munich|hamburg|germany|paris|france|madrid|barcelona|spain|lisbon|portugal|"
 r"amsterdam|netherlands|brussels|belgium|zurich|geneva|zug|switzerland|vienna|austria|"
 r"stockholm|sweden|oslo|norway|copenhagen|denmark|helsinki|finland|aarhus|"
 r"warsaw|krakow|poland|prague|czech|bucharest|romania|budapest|hungary|belgrade|serbia|"
 r"sofia|bulgaria|athens|greece|milan|rome|italy|"
 r"tokyo|japan|osaka|seoul|korea|beijing|shanghai|shenzhen|china|hong kong|taipei|taiwan|"
 r"singapore|sydney|melbourne|australia|auckland|new zealand|"
 r"toronto|vancouver|montreal|ottawa|waterloo|calgary|canada|ontario|quebec|british columbia|"
 r"tel aviv|israel|dubai|uae|abu dhabi|riyadh|saudi|cairo|egypt|"
 r"sao paulo|brazil|mexico city|mexico|guadalajara|bogota|colombia|buenos aires|argentina|"
 r"ecuador|peru|uruguay|paraguay|bolivia|venezuela|panama|guatemala|honduras|"
 r"el salvador|nicaragua|dominican|puerto rico|jamaica|trinidad|"
 r"nigeria|ghana|uganda|rwanda|tanzania|ethiopia|serbia|ukraine|"
 r"santiago|chile|lima|peru|costa rica|manila|philippines|jakarta|indonesia|"
 r"bangkok|thailand|hanoi|vietnam|kuala lumpur|malaysia|lagos|nigeria|nairobi|kenya|"
 r"cape town|johannesburg|south africa|casablanca|morocco|istanbul|turkey|moscow|russia)\b", re.I)
REMOTE = re.compile(r"\b(remote|anywhere|distributed|virtual|work from home|wfh|telecommute)\b", re.I)
CHI = re.compile(r"\b(chicago|chicagoland|cook\s+county|dupage|naperville|schaumburg|evanston|deerfield|northbrook|oak\s+brook|oakbrook|rosemont|arlington\s+heights|des\s+plaines|elk\s+grove|skokie|joliet|elgin|palatine|hoffman\s+estates|downers\s+grove|lisle|itasca|buffalo\s+grove|glenview|park\s+ridge|oak\s+park|cicero|berwyn|bolingbrook|romeoville|westmont|hinsdale|burr\s+ridge|woodridge|wheaton|glen\s+ellyn|lombard|bensenville|elmhurst|villa\s+park|libertyville|vernon\s+hills|lemont|melrose\s+park|franklin\s+park|bedford\s+park|aurora|evergreen\s+park|orland\s+park|tinley\s+park)\b", re.I)
ST_RE = re.compile(r"(?:^|[,\s(/|-])(" + "|".join(ST) + r")(?:$|[,\s)/|-])")
STN_RE = re.compile(r"\b(" + "|".join(STN) + r")\b", re.I)
CITY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in US_CITY) + r")\b", re.I)

def geo(loc):
    """-> dict(us, remote, chicago, foreign_only)"""
    l = loc or ""
    remote = bool(REMOTE.search(l))
    chicago = bool(CHI.search(l))
    us_sig = bool(ST_RE.search(l) or STN_RE.search(l) or CITY_RE.search(l)
                  or re.search(r"\b(usa?|united states|u\.s\.)\b", l, re.I))
    foreign = bool(FOREIGN.search(l) or FOREIGN_NAME.search(l)
                   or FOREIGN_CODE.search(l))
    us = us_sig or (remote and not foreign) or chicago
    return dict(us=us, remote=remote, chicago=chicago,
                foreign_only=foreign and not us_sig and not chicago)


# A posting's location field often names an office while the BODY states the role
# is remote. Empower's "Software Engineer" carried addressLocality "Greenwood
# Village, Colorado" and "Workplace flexibility: Remote - Nationwide" - a real
# remote role the location-only gate would reject. Deliberately strict: these
# phrases state the ROLE is remote, not "our remote-friendly culture" or an EEO
# paragraph.
REMOTE_BODY = re.compile(
    r"(remote\s*[-–—:]\s*nationwide|fully\s+remote|100%\s+remote|"
    r"this\s+(role|position)\s+is\s+(fully\s+)?remote|"
    r"remote\s*\(\s*(us|united states|nationwide|anywhere)|"
    r"work\s+location:\s*remote|workplace\s+flexibility[:\s]*remote|"
    r"location:\s*remote|remote\s+within\s+the\s+(us|united states)|"
    r"anywhere\s+in\s+the\s+(us|united states)|us[-\s]remote\b|remote[-\s]us\b)", re.I)


def remote_in_text(text):
    """True when the posting BODY states the role itself is remote."""
    return bool(text) and bool(REMOTE_BODY.search(text))
