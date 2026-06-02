"""Build the vendored seed roster for rulers.ofthepast.org.

Where the sibling site rulers.ofancientrome.org mirrors a single closed list
(the infoplease roster of Rome), *this* site has no single source: it is a
**synchronic atlas of world rulers** — who held power, at the same time, across
the world, from antiquity to the eighteenth century. So the spine is a curated
table maintained right here, in this file: a representative roster of the most
recognisable monarchs of each region and age, chosen so that for most years the
gallery lights up several thrones at once.

The seed is deliberately *selective*, not a census. It is the spine the
harvester enriches from Wikidata + Wikipedia (exact reign spans, portraits,
biographies, succession, places). Curated reign years here are authoritative for
*placement on the timeline* (the harvester only fills them where blank), because
the whole site turns on "who reigned in year Y" and we do not want a stray
Wikidata office-date to misplace a famous king.

Each entry: (name, wp_title, realm, reign_from, reign_to, blurb).
  - reign_from / reign_to are signed ints; negative = BC.
  - wp_title is the canonical en.wikipedia article (resolved to a QID by the
    harvester). Keep it exact — a miss shows up in the manifest's `no_match`.

Output: harvester/data/seed.json — the spine the harvester reads.

Run:  python -m harvester.build_seed     (or: python harvester/build_seed.py)
"""

import json
import re
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# --- Regions (the lanes of the synchronic view) ------------------------------
# key -> human label. Declaration order is the lane order in the frontend.
REGIONS = [
    ("rome-byzantium", "Rome & Byzantium"),
    ("europe-west", "Western Europe"),
    ("europe-east", "Eastern Europe & Russia"),
    ("middle-east", "Middle East & Persia"),
    ("steppe", "Steppe & Central Asia"),
    ("south-asia", "South Asia"),
    ("southeast-asia", "Southeast Asia"),
    ("east-asia", "East Asia"),
    ("africa", "Africa"),
    ("americas", "The Americas"),
]
REGION_LABEL = dict(REGIONS)

# --- Eras (by reign start year) — the timeline's coloured ages ---------------
# (key, label, upper_bound_exclusive). The last bound is open-ended.
ERAS = [
    ("antiquity", "Antiquity", 300),
    ("late-antiquity", "Late Antiquity", 750),
    ("middle-ages", "Middle Ages", 1450),
    ("early-modern", "Early Modern", 9999),
]
ERA_LABEL = {k: l for k, l, _ in ERAS}


def era_of(year):
    for key, _label, upper in ERAS:
        if year < upper:
            return key
    return ERAS[-1][0]


# --- Civilization (Fandom) wiki links ----------------------------------------
# Many of these rulers are playable leaders (or notable figures) in the
# Civilization games, with a page on the Civ Fandom wiki. This maps roster id ->
# the canonical page title there, for the figures that "make sense" — every
# entry was verified to resolve to a real page (see the verification pass in the
# commit that added this). Figures without a sensible Civ page are simply absent.
CIV_FANDOM = "https://civilization.fandom.com/wiki/"
CIV_WIKI = {
    "augustus": "Augustus Caesar",
    "trajan": "Trajan",
    "cyrus-the-great": "Cyrus",
    "darius-the-great": "Darius I",
    "xerxes-i": "Xerxes",
    "alexander-the-great": "Alexander",
    "ashoka": "Ashoka",
    "chandragupta-maurya": "Chandragupta Maurya",
    "qin-shi-huang": "Qin Shi Huang",
    "wu-zetian": "Wu Zetian",
    "yongle-emperor": "Yongle",
    "kublai-khan": "Kublai Khan",
    "genghis-khan": "Genghis Khan",
    "gedei-khan": "Ögedei Khan",   # slug drops the leading "Ö"
    "attila": "Attila",
    "saladin": "Saladin",
    "harun-al-rashid": "Harun al-Rashid",
    "suleiman-the-magnificent": "Suleiman",
    "mehmed-the-conqueror": "Mehmed II",
    "isabella-i-of-castile": "Isabella",
    "elizabeth-i": "Elizabeth",
    "henry-viii": "Henry VIII",
    "louis-xiv": "Louis XIV",
    "frederick-i-holy-roman-emperor": "Frederick Barbarossa",
    "frederick-the-great": "Frederick the Great",
    "maria-theresa": "Maria Theresa",
    "catherine-the-great": "Catherine the Great",
    "peter-the-great": "Peter",
    "cleopatra": "Cleopatra",
    "hatshepsut": "Hatshepsut",
    "ramesses-ii": "Ramesses II",
    "ptolemy-i-soter": "Ptolemy",
    "mansa-musa": "Mansa Musa",
    "nzinga-of-ndongo-and-matamba": "Nzinga Mbande",
    "suryavarman-ii": "Suryavarman II",
    "jayavarman-vii": "Jayavarman VII",
    "pachacuti": "Pachacuti",
    "moctezuma-i": "Montezuma",
    "tokugawa-ieyasu": "Tokugawa Ieyasu",
    "oda-nobunaga": "Oda Nobunaga",
    "sejong-the-great": "Sejong",
    "ivan-the-terrible": "Ivan the Terrible",
    "basil-ii": "Basil II",
    "justinian-i": "Justinian I",
}


def civ_url(ruler_id):
    title = CIV_WIKI.get(ruler_id)
    if not title:
        return None
    return CIV_FANDOM + urllib.parse.quote(title.replace(" ", "_"))


# --- The curated roster ------------------------------------------------------
# region -> [ (name, wp_title, realm, reign_from, reign_to, blurb), ... ]
ROSTER = {
    "rome-byzantium": [
        ("Augustus", "Augustus", "Roman Empire", -27, 14,
         "first Roman emperor; founded the Principate and the Pax Romana"),
        ("Trajan", "Trajan", "Roman Empire", 98, 117,
         "soldier-emperor under whom the empire reached its greatest extent"),
        ("Hadrian", "Hadrian", "Roman Empire", 117, 138,
         "consolidator and builder of the Wall in Britain"),
        ("Marcus Aurelius", "Marcus Aurelius", "Roman Empire", 161, 180,
         "the philosopher-emperor of the Meditations"),
        ("Constantine the Great", "Constantine the Great", "Roman Empire", 306, 337,
         "first Christian emperor; founded Constantinople"),
        ("Theodosius I", "Theodosius I", "Roman Empire", 379, 395,
         "last to rule a united empire; made Christianity the state religion"),
        ("Justinian I", "Justinian I", "Byzantine Empire", 527, 565,
         "codified Roman law and reconquered much of the West"),
        ("Heraclius", "Heraclius", "Byzantine Empire", 610, 641,
         "broke Sasanian Persia, then faced the Arab conquests"),
        ("Leo III the Isaurian", "Leo III the Isaurian", "Byzantine Empire", 717, 741,
         "repelled the Arab siege of Constantinople; began Iconoclasm"),
        ("Irene of Athens", "Irene of Athens", "Byzantine Empire", 797, 802,
         "first woman to rule the empire in her own name"),
        ("Basil I", "Basil I", "Byzantine Empire", 867, 886,
         "founder of the Macedonian dynasty"),
        ("Basil II", "Basil II", "Byzantine Empire", 976, 1025,
         "the Bulgar-Slayer; brought the empire to a late zenith"),
        ("Alexios I Komnenos", "Alexios I Komnenos", "Byzantine Empire", 1081, 1118,
         "rebuilt the empire and called the First Crusade"),
        ("Constantine XI Palaiologos", "Constantine XI Palaiologos", "Byzantine Empire", 1449, 1453,
         "last emperor; died defending Constantinople"),
    ],
    "europe-west": [
        ("Clovis I", "Clovis I", "Frankish Kingdom", 481, 511,
         "united the Franks and converted to Catholic Christianity"),
        ("Charlemagne", "Charlemagne", "Carolingian Empire", 768, 814,
         "King of the Franks crowned Emperor of the Romans in 800"),
        ("Alfred the Great", "Alfred the Great", "Kingdom of Wessex", 871, 899,
         "held off the Danes and laid the groundwork for England"),
        ("Otto I", "Otto I, Holy Roman Emperor", "Holy Roman Empire", 936, 973,
         "founder of the Holy Roman Empire"),
        ("William the Conqueror", "William the Conqueror", "Kingdom of England", 1066, 1087,
         "Duke of Normandy who conquered England in 1066"),
        ("Frederick Barbarossa", "Frederick I, Holy Roman Emperor", "Holy Roman Empire", 1155, 1190,
         "Hohenstaufen emperor who clashed with the Lombard cities and the Pope"),
        ("Philip II of France", "Philip II of France", "Kingdom of France", 1180, 1223,
         "doubled the crown lands and broke the Angevin empire"),
        ("Frederick II", "Frederick II, Holy Roman Emperor", "Holy Roman Empire", 1220, 1250,
         "the 'stupor mundi', ruling from Sicily over a polyglot court"),
        ("Louis IX of France", "Louis IX of France", "Kingdom of France", 1226, 1270,
         "the crusading saint-king"),
        ("Edward I of England", "Edward I of England", "Kingdom of England", 1272, 1307,
         "lawgiver and conqueror of Wales"),
        ("Isabella I of Castile", "Isabella I of Castile", "Crown of Castile", 1474, 1504,
         "with Ferdinand, completed the Reconquista and sent Columbus west"),
        ("Ferdinand II of Aragon", "Ferdinand II of Aragon", "Crown of Aragon", 1479, 1516,
         "co-architect of a united Spain"),
        ("Henry VIII", "Henry VIII", "Kingdom of England", 1509, 1547,
         "broke with Rome and founded the Church of England"),
        ("Charles V", "Charles V, Holy Roman Emperor", "Holy Roman Empire", 1519, 1556,
         "ruled an empire on which the sun never set"),
        ("Philip II of Spain", "Philip II of Spain", "Spanish Empire", 1556, 1598,
         "master of a global empire; launched the Armada"),
        ("Elizabeth I", "Elizabeth I", "Kingdom of England", 1558, 1603,
         "the Virgin Queen of England's golden age"),
        ("Charles I of England", "Charles I of England", "Kingdom of England", 1625, 1649,
         "lost the Civil War and his head"),
        ("Louis XIV", "Louis XIV", "Kingdom of France", 1643, 1715,
         "the Sun King; the model of absolute monarchy"),
        ("Maria Theresa", "Maria Theresa", "Habsburg Monarchy", 1740, 1780,
         "only female ruler of the Habsburg lands; reformer"),
        ("Frederick the Great", "Frederick the Great", "Kingdom of Prussia", 1740, 1786,
         "soldier-philosopher who made Prussia a great power"),
    ],
    "europe-east": [
        ("Vladimir the Great", "Vladimir the Great", "Kievan Rus'", 980, 1015,
         "Christianised the Rus'"),
        ("Yaroslav the Wise", "Yaroslav the Wise", "Kievan Rus'", 1019, 1054,
         "lawgiver of the Rus' at its height"),
        ("Stephen Dušan", "Stephen Dušan", "Serbian Empire", 1331, 1355,
         "raised Serbia to an empire spanning the Balkans"),
        ("Casimir III the Great", "Casimir III the Great", "Kingdom of Poland", 1333, 1370,
         "'found Poland of wood and left it of stone'"),
        ("Matthias Corvinus", "Matthias Corvinus", "Kingdom of Hungary", 1458, 1490,
         "Renaissance king of Hungary"),
        ("Ivan III of Russia", "Ivan III of Russia", "Grand Duchy of Moscow", 1462, 1505,
         "the Great; threw off the Mongol yoke and gathered the Russian lands"),
        ("Ivan the Terrible", "Ivan the Terrible", "Tsardom of Russia", 1547, 1584,
         "first Tsar of all Russia"),
        ("John III Sobieski", "John III Sobieski", "Polish–Lithuanian Commonwealth", 1674, 1696,
         "broke the Ottoman siege of Vienna in 1683"),
        ("Peter the Great", "Peter the Great", "Tsardom of Russia", 1682, 1725,
         "westernised Russia and built St Petersburg"),
        ("Catherine the Great", "Catherine the Great", "Russian Empire", 1762, 1796,
         "enlightened empress who expanded Russia to the Black Sea"),
    ],
    "middle-east": [
        ("Cyrus the Great", "Cyrus the Great", "Achaemenid Empire", -559, -530,
         "founder of the first Persian empire"),
        ("Darius the Great", "Darius the Great", "Achaemenid Empire", -522, -486,
         "organised the empire into satrapies and built Persepolis"),
        ("Xerxes I", "Xerxes I", "Achaemenid Empire", -486, -465,
         "led the great invasion of Greece"),
        ("Alexander the Great", "Alexander the Great", "Macedonian Empire", -336, -323,
         "overthrew Persia and carried Greek arms to India"),
        ("Seleucus I Nicator", "Seleucus I Nicator", "Seleucid Empire", -305, -281,
         "general of Alexander who founded the Seleucid realm"),
        ("Shapur I", "Shapur I", "Sasanian Empire", 240, 270,
         "captured a Roman emperor, Valerian"),
        ("Khosrow I", "Khosrow I", "Sasanian Empire", 531, 579,
         "the Just; high point of Sasanian Persia"),
        ("Muawiyah I", "Muawiyah I", "Umayyad Caliphate", 661, 680,
         "founder of the Umayyad Caliphate"),
        ("Harun al-Rashid", "Harun al-Rashid", "Abbasid Caliphate", 786, 809,
         "caliph of the Baghdad golden age and the Arabian Nights"),
        ("Saladin", "Saladin", "Ayyubid Sultanate", 1174, 1193,
         "retook Jerusalem from the Crusaders"),
        ("Mehmed the Conqueror", "Mehmed the Conqueror", "Ottoman Empire", 1451, 1481,
         "took Constantinople in 1453"),
        ("Ismail I", "Ismail I", "Safavid Empire", 1501, 1524,
         "founded Safavid Persia and made it Shi'a"),
        ("Suleiman the Magnificent", "Suleiman the Magnificent", "Ottoman Empire", 1520, 1566,
         "the Lawgiver; the Ottoman zenith"),
        ("Abbas the Great", "Abbas the Great", "Safavid Empire", 1588, 1629,
         "remade Persia from his capital at Isfahan"),
        ("Nader Shah", "Nader Shah", "Afsharid Persia", 1736, 1747,
         "the 'Persian Napoleon'; sacked Delhi"),
    ],
    "steppe": [
        ("Attila", "Attila", "Hunnic Empire", 434, 453,
         "the Hun; the 'Scourge of God'"),
        ("Genghis Khan", "Genghis Khan", "Mongol Empire", 1206, 1227,
         "founder of the largest contiguous land empire in history"),
        ("Ögedei Khan", "Ögedei Khan", "Mongol Empire", 1229, 1241,
         "great khan under whom the Mongols reached Europe"),
        ("Batu Khan", "Batu Khan", "Golden Horde", 1227, 1255,
         "conquered the Rus' and founded the Golden Horde"),
        ("Timur", "Timur", "Timurid Empire", 1370, 1405,
         "Tamerlane; built an empire from Samarkand"),
    ],
    "south-asia": [
        ("Chandragupta Maurya", "Chandragupta Maurya", "Maurya Empire", -322, -298,
         "founder of the first empire to unite most of the subcontinent"),
        ("Ashoka", "Ashoka", "Maurya Empire", -268, -232,
         "embraced Buddhism after the bloodshed of Kalinga"),
        ("Kanishka", "Kanishka", "Kushan Empire", 127, 150,
         "Kushan emperor at the crossroads of the Silk Road"),
        ("Samudragupta", "Samudragupta", "Gupta Empire", 335, 375,
         "conqueror-king of the Gupta golden age"),
        ("Chandragupta II", "Chandragupta II", "Gupta Empire", 380, 415,
         "presided over a classical Indian renaissance"),
        ("Harsha", "Harsha", "Empire of Harsha", 606, 647,
         "last great ruler of a united northern India before Islam"),
        ("Rajaraja I", "Rajaraja I", "Chola Empire", 985, 1014,
         "made the Cholas a naval power across the Indian Ocean"),
        ("Rajendra Chola I", "Rajendra Chola I", "Chola Empire", 1014, 1044,
         "carried Chola arms to the Ganges and Srivijaya"),
        ("Alauddin Khalji", "Alauddin Khalji", "Delhi Sultanate", 1296, 1316,
         "repelled the Mongols and pushed the Sultanate south"),
        ("Krishnadevaraya", "Krishnadevaraya", "Vijayanagara Empire", 1509, 1529,
         "high point of the great southern Hindu empire"),
        ("Babur", "Babur", "Mughal Empire", 1526, 1530,
         "Timurid prince who founded the Mughal Empire"),
        ("Akbar", "Akbar", "Mughal Empire", 1556, 1605,
         "the Great; built a tolerant, centralised Mughal state"),
        ("Shah Jahan", "Shah Jahan", "Mughal Empire", 1628, 1658,
         "builder of the Taj Mahal"),
        ("Aurangzeb", "Aurangzeb", "Mughal Empire", 1658, 1707,
         "expanded the empire to its limit and overstretched it"),
        ("Shivaji", "Shivaji", "Maratha Empire", 1674, 1680,
         "founder of the Maratha state"),
    ],
    "southeast-asia": [
        ("Suryavarman II", "Suryavarman II", "Khmer Empire", 1113, 1150,
         "builder of Angkor Wat"),
        ("Jayavarman VII", "Jayavarman VII", "Khmer Empire", 1181, 1218,
         "greatest of the Angkor kings; built Angkor Thom"),
        ("Ram Khamhaeng", "Ram Khamhaeng", "Sukhothai Kingdom", 1279, 1298,
         "credited with the Thai alphabet"),
        ("Hayam Wuruk", "Hayam Wuruk", "Majapahit", 1350, 1389,
         "ruled Majapahit at its maritime height"),
        ("Bayinnaung", "Bayinnaung", "Toungoo Dynasty", 1550, 1581,
         "built the largest empire in Southeast Asian history"),
        ("Naresuan", "Naresuan", "Ayutthaya Kingdom", 1590, 1605,
         "won Siam's independence from Burma"),
    ],
    "east-asia": [
        ("Qin Shi Huang", "Qin Shi Huang", "Qin Dynasty", -221, -210,
         "first emperor to unify China; built the first Great Wall"),
        ("Emperor Gaozu of Han", "Emperor Gaozu of Han", "Han Dynasty", -202, -195,
         "peasant who founded the four-century Han dynasty"),
        ("Emperor Wu of Han", "Emperor Wu of Han", "Han Dynasty", -141, -87,
         "expanded Han China and opened the Silk Road"),
        ("Emperor Guangwu of Han", "Emperor Guangwu of Han", "Han Dynasty", 25, 57,
         "restored the Han dynasty after a usurpation"),
        ("Gwanggaeto the Great", "Gwanggaeto the Great", "Goguryeo", 391, 412,
         "conqueror-king who expanded Korea's Goguryeo"),
        ("Emperor Taizong of Tang", "Emperor Taizong of Tang", "Tang Dynasty", 626, 649,
         "model emperor of China's Tang golden age"),
        ("Wu Zetian", "Wu Zetian", "Zhou (Tang interregnum)", 690, 705,
         "the only woman to rule China as emperor"),
        ("Emperor Xuanzong of Tang", "Emperor Xuanzong of Tang", "Tang Dynasty", 712, 756,
         "presided over Tang's cultural peak, then the An Lushan ruin"),
        ("Emperor Kanmu", "Emperor Kanmu", "Imperial Japan", 781, 806,
         "moved the Japanese capital to Heian (Kyoto)"),
        ("Emperor Taizu of Song", "Emperor Taizu of Song", "Song Dynasty", 960, 976,
         "reunified China and founded the Song"),
        ("Minamoto no Yoritomo", "Minamoto no Yoritomo", "Kamakura Shogunate", 1192, 1199,
         "first shogun; began rule by the samurai"),
        ("Kublai Khan", "Kublai Khan", "Yuan Dynasty", 1260, 1294,
         "Mongol grandson of Genghis who founded the Yuan in China"),
        ("Hongwu Emperor", "Hongwu Emperor", "Ming Dynasty", 1368, 1398,
         "peasant rebel who drove out the Mongols and founded the Ming"),
        ("Yongle Emperor", "Yongle Emperor", "Ming Dynasty", 1402, 1424,
         "built the Forbidden City and sent out Zheng He's fleets"),
        ("Sejong the Great", "Sejong the Great", "Joseon", 1418, 1450,
         "gave Korea the Hangul alphabet"),
        ("Oda Nobunaga", "Oda Nobunaga", "Sengoku Japan", 1568, 1582,
         "began the reunification of warring-states Japan"),
        ("Wanli Emperor", "Wanli Emperor", "Ming Dynasty", 1572, 1620,
         "long reign that saw the Ming begin to falter"),
        ("Toyotomi Hideyoshi", "Toyotomi Hideyoshi", "Azuchi–Momoyama Japan", 1585, 1598,
         "completed the unification of Japan"),
        ("Tokugawa Ieyasu", "Tokugawa Ieyasu", "Tokugawa Shogunate", 1603, 1605,
         "founder of the shogunate that ruled Japan for 250 years"),
        ("Kangxi Emperor", "Kangxi Emperor", "Qing Dynasty", 1661, 1722,
         "one of the longest reigns in history; consolidated Qing rule"),
        ("Qianlong Emperor", "Qianlong Emperor", "Qing Dynasty", 1735, 1796,
         "ruled China at its largest and most prosperous"),
    ],
    "africa": [
        ("Hatshepsut", "Hatshepsut", "New Kingdom of Egypt", -1479, -1458,
         "one of the few women to rule as pharaoh"),
        ("Ramesses II", "Ramesses II", "New Kingdom of Egypt", -1279, -1213,
         "the Great; builder-pharaoh of Abu Simbel"),
        ("Ptolemy I Soter", "Ptolemy I Soter", "Ptolemaic Kingdom", -305, -282,
         "general of Alexander who founded the Ptolemaic dynasty"),
        ("Cleopatra", "Cleopatra", "Ptolemaic Kingdom", -51, -30,
         "last pharaoh of Egypt"),
        ("Ezana of Axum", "Ezana of Axum", "Kingdom of Aksum", 320, 360,
         "made Aksum (Ethiopia) a Christian kingdom"),
        ("Mansa Musa", "Mansa Musa", "Mali Empire", 1312, 1337,
         "fabled for the gold of his pilgrimage to Mecca"),
        ("Sunni Ali", "Sunni Ali", "Songhai Empire", 1464, 1492,
         "built Songhai into West Africa's greatest empire"),
        ("Askia the Great", "Askia Muhammad I", "Songhai Empire", 1493, 1528,
         "organised Songhai and made Timbuktu a seat of learning"),
        ("Idris Alooma", "Idris Alooma", "Kanem–Bornu Empire", 1564, 1596,
         "reformer-sultan of Bornu around Lake Chad"),
        ("Ahmad al-Mansur", "Ahmad al-Mansur", "Saadi Sultanate", 1578, 1603,
         "Moroccan sultan whose army crossed the Sahara to take Songhai"),
        ("Nzinga of Ndongo", "Nzinga of Ndongo and Matamba", "Ndongo and Matamba", 1624, 1663,
         "queen who fought the Portuguese slave trade for decades"),
    ],
    "americas": [
        ("Pakal the Great", "K'inich Janaab' Pakal", "Maya (Palenque)", 615, 683,
         "long-reigning king of the Maya city of Palenque"),
        ("Itzcoatl", "Itzcoatl", "Aztec Empire", 1427, 1440,
         "founder of the Aztec Triple Alliance"),
        ("Pachacuti", "Pachacuti", "Inca Empire", 1438, 1471,
         "transformed Cusco into the Inca Empire; built Machu Picchu"),
        ("Moctezuma I", "Moctezuma I", "Aztec Empire", 1440, 1469,
         "expanded the Aztec Empire across central Mexico"),
        ("Huayna Capac", "Huayna Capac", "Inca Empire", 1493, 1527,
         "ruled the Inca Empire at its greatest extent"),
        ("Moctezuma II", "Moctezuma II", "Aztec Empire", 1502, 1520,
         "emperor when Cortés arrived"),
        ("Atahualpa", "Atahualpa", "Inca Empire", 1532, 1533,
         "last independent Inca emperor; killed by Pizarro"),
    ],
}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    entries = []
    for region_key, _label in REGIONS:
        for (name, wp, realm, rf, rt, blurb) in ROSTER.get(region_key, []):
            entries.append({
                "name": name,
                "region": region_key,
                "region_label": REGION_LABEL[region_key],
                "realm": realm,
                "reign_from": rf,
                "reign_to": rt,
                "era": era_of(rf),
                "era_label": ERA_LABEL[era_of(rf)],
                "blurb": blurb,
                "wp": wp,
            })

    # Catalogue order = chronological by reign start, then by name. Gives every
    # ruler a stable global numeral (№) read off the line of world history.
    entries.sort(key=lambda e: (e["reign_from"], e["name"]))

    # Stable, unique slug ids derived from the wikipedia title.
    seen = {}
    out = []
    for i, e in enumerate(entries, start=1):
        base = slugify(e["wp"] or e["name"])
        n = seen.get(base, 0)
        seen[base] = n + 1
        slug = base if not n else f"{base}-{n + 1}"
        out.append({
            "id": slug,
            "order": i,
            "name": e["name"],
            "region": e["region"],
            "region_label": e["region_label"],
            "realm": e["realm"],
            "era": e["era"],
            "era_label": e["era_label"],
            "blurb": e["blurb"],
            "reign_from": e["reign_from"],
            "reign_to": e["reign_to"],
            # placement fallbacks the harvester reads (Wikidata fills birth/death)
            "year_from": e["reign_from"],
            "year_to": e["reign_to"],
            "wp": e["wp"],
            "civ_wiki": civ_url(slug),
        })

    (DATA / "seed.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    # --- report ---
    print(f"wrote seed.json: {len(out)} rulers")
    by_region = {}
    by_era = {}
    for e in out:
        by_region[e["region"]] = by_region.get(e["region"], 0) + 1
        by_era[e["era"]] = by_era.get(e["era"], 0) + 1
    print("by region:")
    for k, _l in REGIONS:
        print(f"   {k:16} {by_region.get(k, 0)}")
    print("by era:", by_era)
    yrs = [e["reign_from"] for e in out] + [e["reign_to"] for e in out]
    print(f"span: {min(yrs)} .. {max(yrs)}")

    # uniqueness guard
    ids = [e["id"] for e in out]
    assert len(ids) == len(set(ids)), "duplicate slug ids!"

    # a quick contemporaneity spot-check
    for probe in (-220, 100, 800, 1200, 1550, 1700):
        live = [e["name"] for e in out if e["reign_from"] <= probe <= e["reign_to"]]
        ylabel = f"{-probe} BC" if probe < 0 else f"AD {probe}"
        print(f"  {ylabel:8}: {len(live)} reigning — {', '.join(live[:8])}")


if __name__ == "__main__":
    main()
