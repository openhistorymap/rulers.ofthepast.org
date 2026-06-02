"""Build the vendored seed roster for rulers.ofthepast.org.

Where the sibling site rulers.ofancientrome.org mirrors a single closed list
(the infoplease roster of Rome), *this* site has no single source: it is a
**synchronic atlas of world rulers** — who held power, at the same time, across
the world, from the dawn of kingship to the eighteenth century. So the spine is
a curated table maintained right here, in this file: a representative roster of
the most recognisable monarchs of each region and age, chosen so that for most
years the gallery lights up several thrones at once.

The seed is deliberately *selective*, not a census. It is the spine the
harvester enriches from Wikidata + Wikipedia (exact reign spans, portraits,
biographies, succession, places). Curated reign years here are authoritative for
*placement on the timeline* (the harvester only fills them where blank), because
the whole site turns on "who reigned in year Y" and we do not want a stray
Wikidata office-date to misplace a famous king.

Deep time: the meridian reaches back to MERIDIAN_FLOOR (9000 BC), but the
earliest *named* rulers humanity records begin only around 3100 BC (Narmer), and
the oldest here are legendary (Gilgamesh, the Yellow Emperor). The long stretch
before that — the "Before the Kings" era — is deliberately empty: kingship is
younger than the city, and no name survives. That emptiness is the point.

Each entry: (name, wp_title, realm, reign_from, reign_to, blurb).
  - reign_from / reign_to are signed ints; negative = BC.
  - wp_title is the canonical en.wikipedia article (resolved to a QID by the
    harvester). Keep it exact — a miss shows up in the manifest's `no_match`.

Output: harvester/data/seed.json — the spine the harvester reads.

Run:  python -m harvester.build_seed     (or: python harvester/build_seed.py)
"""

import json
import re
import unicodedata
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# The meridian reaches back this far even though no named ruler does — the deep
# "Before the Kings" stretch is shown empty on purpose. The harvester floors the
# timeline's lower bound to this value.
MERIDIAN_FLOOR = -9000

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
# (key, label, upper_bound_exclusive). The last bound is open-ended; the first
# era's lower bound is MERIDIAN_FLOOR.
ERAS = [
    ("dawn", "Before the Kings", -3300),
    ("bronze-age", "Bronze Age", -1200),
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
# entry is verified to resolve to a real page (see harvester verification pass).
CIV_FANDOM = "https://civilization.fandom.com/wiki/"
CIV_WIKI = {
    "gilgamesh": "Gilgamesh",
    "hammurabi": "Hammurabi",
    "nebuchadnezzar-ii": "Nebuchadnezzar II",
    "hatshepsut": "Hatshepsut",
    "ramesses-ii": "Ramesses II",
    "cleopatra": "Cleopatra",
    "ptolemy-i-soter": "Ptolemy",
    "cyrus-the-great": "Cyrus",
    "darius-the-great": "Darius I",
    "xerxes-i": "Xerxes",
    "alexander-the-great": "Alexander",
    "julius-caesar": "Julius Caesar",
    "augustus": "Augustus Caesar",
    "trajan": "Trajan",
    "ashoka": "Ashoka",
    "chandragupta-maurya": "Chandragupta Maurya",
    "qin-shi-huang": "Qin Shi Huang",
    "wu-zetian": "Wu Zetian",
    "yongle-emperor": "Yongle",
    "kublai-khan": "Kublai Khan",
    "genghis-khan": "Genghis Khan",
    "ogedei-khan": "Ögedei Khan",
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
    "gustavus-adolphus": "Gustavus Adolphus",
    "mansa-musa": "Mansa Musa",
    "nzinga-of-ndongo-and-matamba": "Nzinga Mbande",
    "suryavarman-ii": "Suryavarman II",
    "jayavarman-vii": "Jayavarman VII",
    "pachacuti": "Pachacuti",
    "moctezuma-i": "Montezuma",
    "tokugawa-ieyasu": "Tokugawa Ieyasu",
    "oda-nobunaga": "Oda Nobunaga",
    "hojo-tokimune": "Hojo Tokimune",
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
        ("Julius Caesar", "Julius Caesar", "Roman Republic", -49, -44,
         "dictator whose rise ended the Roman Republic"),
        ("Augustus", "Augustus", "Roman Empire", -27, 14,
         "first Roman emperor; founded the Principate and the Pax Romana"),
        ("Nero", "Nero", "Roman Empire", 54, 68,
         "last of the Julio-Claudians; fiddled while Rome burned"),
        ("Vespasian", "Vespasian", "Roman Empire", 69, 79,
         "founder of the Flavian dynasty; began the Colosseum"),
        ("Trajan", "Trajan", "Roman Empire", 98, 117,
         "soldier-emperor under whom the empire reached its greatest extent"),
        ("Hadrian", "Hadrian", "Roman Empire", 117, 138,
         "consolidator and builder of the Wall in Britain"),
        ("Marcus Aurelius", "Marcus Aurelius", "Roman Empire", 161, 180,
         "the philosopher-emperor of the Meditations"),
        ("Septimius Severus", "Septimius Severus", "Roman Empire", 193, 211,
         "African-born founder of the Severan dynasty"),
        ("Diocletian", "Diocletian", "Roman Empire", 284, 305,
         "split rule into the Tetrarchy and stabilised the empire"),
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
        ("Constantine V", "Constantine V", "Byzantine Empire", 741, 775,
         "able soldier-emperor and fierce iconoclast"),
        ("Irene of Athens", "Irene of Athens", "Byzantine Empire", 797, 802,
         "first woman to rule the empire in her own name"),
        ("Basil I", "Basil I", "Byzantine Empire", 867, 886,
         "founder of the Macedonian dynasty"),
        ("Nikephoros II Phokas", "Nikephoros II Phokas", "Byzantine Empire", 963, 969,
         "warrior-emperor who retook Crete and Antioch"),
        ("Basil II", "Basil II", "Byzantine Empire", 976, 1025,
         "the Bulgar-Slayer; brought the empire to a late zenith"),
        ("Alexios I Komnenos", "Alexios I Komnenos", "Byzantine Empire", 1081, 1118,
         "rebuilt the empire and called the First Crusade"),
        ("Manuel I Komnenos", "Manuel I Komnenos", "Byzantine Empire", 1143, 1180,
         "last emperor to wield real power across the Mediterranean"),
        ("Michael VIII Palaiologos", "Michael VIII Palaiologos", "Byzantine Empire", 1259, 1282,
         "recovered Constantinople from the Latins in 1261"),
        ("Constantine XI Palaiologos", "Constantine XI Palaiologos", "Byzantine Empire", 1449, 1453,
         "last emperor; died defending Constantinople"),
    ],
    "europe-west": [
        ("Clovis I", "Clovis I", "Frankish Kingdom", 481, 511,
         "united the Franks and converted to Catholic Christianity"),
        ("Charles Martel", "Charles Martel", "Frankish Kingdom", 718, 741,
         "halted the Umayyad advance at the Battle of Tours"),
        ("Charlemagne", "Charlemagne", "Carolingian Empire", 768, 814,
         "King of the Franks crowned Emperor of the Romans in 800"),
        ("Alfred the Great", "Alfred the Great", "Kingdom of Wessex", 871, 899,
         "held off the Danes and laid the groundwork for England"),
        ("Otto I", "Otto I, Holy Roman Emperor", "Holy Roman Empire", 936, 973,
         "founder of the Holy Roman Empire"),
        ("Hugh Capet", "Hugh Capet", "Kingdom of France", 987, 996,
         "founder of the Capetian dynasty of France"),
        ("Cnut the Great", "Cnut", "North Sea Empire", 1016, 1035,
         "ruled a North Sea empire of England, Denmark, and Norway"),
        ("William the Conqueror", "William the Conqueror", "Kingdom of England", 1066, 1087,
         "Duke of Normandy who conquered England in 1066"),
        ("Henry II of England", "Henry II of England", "Kingdom of England", 1154, 1189,
         "founder of the Angevin empire and English common law"),
        ("Frederick Barbarossa", "Frederick I, Holy Roman Emperor", "Holy Roman Empire", 1155, 1190,
         "Hohenstaufen emperor who clashed with the Lombard cities and the Pope"),
        ("Philip II of France", "Philip II of France", "Kingdom of France", 1180, 1223,
         "doubled the crown lands and broke the Angevin empire"),
        ("Richard the Lionheart", "Richard I of England", "Kingdom of England", 1189, 1199,
         "crusader-king of England"),
        ("John, King of England", "John, King of England", "Kingdom of England", 1199, 1216,
         "lost Normandy and was forced to seal Magna Carta"),
        ("Frederick II", "Frederick II, Holy Roman Emperor", "Holy Roman Empire", 1220, 1250,
         "the 'stupor mundi', ruling from Sicily over a polyglot court"),
        ("Louis IX of France", "Louis IX of France", "Kingdom of France", 1226, 1270,
         "the crusading saint-king"),
        ("Edward I of England", "Edward I of England", "Kingdom of England", 1272, 1307,
         "lawgiver and conqueror of Wales"),
        ("Philip IV of France", "Philip IV of France", "Kingdom of France", 1285, 1314,
         "the Fair; broke the Templars and the papacy"),
        ("Edward III of England", "Edward III of England", "Kingdom of England", 1327, 1377,
         "began the Hundred Years' War"),
        ("Henry V of England", "Henry V of England", "Kingdom of England", 1413, 1422,
         "victor of Agincourt"),
        ("Isabella I of Castile", "Isabella I of Castile", "Crown of Castile", 1474, 1504,
         "with Ferdinand, completed the Reconquista and sent Columbus west"),
        ("Ferdinand II of Aragon", "Ferdinand II of Aragon", "Crown of Aragon", 1479, 1516,
         "co-architect of a united Spain"),
        ("Maximilian I", "Maximilian I, Holy Roman Emperor", "Holy Roman Empire", 1508, 1519,
         "wove the Habsburgs into the great houses of Europe"),
        ("Henry VIII", "Henry VIII", "Kingdom of England", 1509, 1547,
         "broke with Rome and founded the Church of England"),
        ("Charles V", "Charles V, Holy Roman Emperor", "Holy Roman Empire", 1519, 1556,
         "ruled an empire on which the sun never set"),
        ("Philip II of Spain", "Philip II of Spain", "Spanish Empire", 1556, 1598,
         "master of a global empire; launched the Armada"),
        ("Elizabeth I", "Elizabeth I", "Kingdom of England", 1558, 1603,
         "the Virgin Queen of England's golden age"),
        ("Henry IV of France", "Henry IV of France", "Kingdom of France", 1589, 1610,
         "ended the Wars of Religion; 'Paris is worth a Mass'"),
        ("James VI and I", "James VI and I", "Kingdom of England", 1603, 1625,
         "first to rule England and Scotland together"),
        ("Gustavus Adolphus", "Gustavus Adolphus", "Swedish Empire", 1611, 1632,
         "the Lion of the North; made Sweden a great power"),
        ("Charles I of England", "Charles I of England", "Kingdom of England", 1625, 1649,
         "lost the Civil War and his head"),
        ("Louis XIV", "Louis XIV", "Kingdom of France", 1643, 1715,
         "the Sun King; the model of absolute monarchy"),
        ("Louis XV", "Louis XV", "Kingdom of France", 1715, 1774,
         "long reign that drifted toward revolution"),
        ("Maria Theresa", "Maria Theresa", "Habsburg Monarchy", 1740, 1780,
         "only female ruler of the Habsburg lands; reformer"),
        ("Frederick the Great", "Frederick the Great", "Kingdom of Prussia", 1740, 1786,
         "soldier-philosopher who made Prussia a great power"),
    ],
    "europe-east": [
        ("Mieszko I", "Mieszko I", "Duchy of Poland", 960, 992,
         "first ruler of Poland; brought it into Christendom"),
        ("Vladimir the Great", "Vladimir the Great", "Kievan Rus'", 980, 1015,
         "Christianised the Rus'"),
        ("Bolesław I the Brave", "Bolesław I the Brave", "Kingdom of Poland", 992, 1025,
         "first crowned king of Poland"),
        ("Yaroslav the Wise", "Yaroslav the Wise", "Kievan Rus'", 1019, 1054,
         "lawgiver of the Rus' at its height"),
        ("Béla IV of Hungary", "Béla IV of Hungary", "Kingdom of Hungary", 1235, 1270,
         "rebuilt Hungary after the Mongol invasion"),
        ("Stephen Dušan", "Stephen Dušan", "Serbian Empire", 1331, 1355,
         "raised Serbia to an empire spanning the Balkans"),
        ("Casimir III the Great", "Casimir III the Great", "Kingdom of Poland", 1333, 1370,
         "'found Poland of wood and left it of stone'"),
        ("Władysław II Jagiełło", "Władysław II Jagiełło", "Kingdom of Poland", 1386, 1434,
         "founder of the Jagiellonian dynasty; victor at Grunwald"),
        ("Vytautas", "Vytautas", "Grand Duchy of Lithuania", 1392, 1430,
         "the Great; ruled Lithuania at its widest extent"),
        ("Casimir IV Jagiellon", "Casimir IV Jagiellon", "Kingdom of Poland", 1447, 1492,
         "made the Jagiellonians the leading house of central Europe"),
        ("Matthias Corvinus", "Matthias Corvinus", "Kingdom of Hungary", 1458, 1490,
         "Renaissance king of Hungary"),
        ("Ivan III of Russia", "Ivan III of Russia", "Grand Duchy of Moscow", 1462, 1505,
         "the Great; threw off the Mongol yoke and gathered the Russian lands"),
        ("Ivan the Terrible", "Ivan the Terrible", "Tsardom of Russia", 1547, 1584,
         "first Tsar of all Russia"),
        ("Stephen Báthory", "Stephen Báthory", "Polish–Lithuanian Commonwealth", 1576, 1586,
         "warrior-king of Poland against Muscovy"),
        ("Sigismund III Vasa", "Sigismund III Vasa", "Polish–Lithuanian Commonwealth", 1587, 1632,
         "ruled Poland at its territorial peak"),
        ("Boris Godunov", "Boris Godunov", "Tsardom of Russia", 1598, 1605,
         "tsar whose death opened Russia's Time of Troubles"),
        ("Michael of Russia", "Michael of Russia", "Tsardom of Russia", 1613, 1645,
         "first Romanov tsar"),
        ("John III Sobieski", "John III Sobieski", "Polish–Lithuanian Commonwealth", 1674, 1696,
         "broke the Ottoman siege of Vienna in 1683"),
        ("Peter the Great", "Peter the Great", "Tsardom of Russia", 1682, 1725,
         "westernised Russia and built St Petersburg"),
        ("Catherine the Great", "Catherine the Great", "Russian Empire", 1762, 1796,
         "enlightened empress who expanded Russia to the Black Sea"),
    ],
    "middle-east": [
        ("Gilgamesh", "Gilgamesh", "Uruk", -2700, -2650,
         "legendary king of Uruk, hero of the oldest epic"),
        ("Sargon of Akkad", "Sargon of Akkad", "Akkadian Empire", -2334, -2279,
         "built the world's first empire, in Mesopotamia"),
        ("Ur-Nammu", "Ur-Nammu", "Third Dynasty of Ur", -2112, -2094,
         "issued one of the earliest known law codes"),
        ("Hammurabi", "Hammurabi", "First Babylonian Empire", -1792, -1750,
         "Babylonian king of the famous law code"),
        ("Suppiluliuma I", "Suppiluliuma I", "Hittite Empire", -1344, -1322,
         "made the Hittites a great power of the Bronze Age"),
        ("David", "David", "Kingdom of Israel", -1010, -970,
         "warrior-king of Israel"),
        ("Solomon", "Solomon", "Kingdom of Israel", -970, -931,
         "builder of the First Temple in Jerusalem"),
        ("Tiglath-Pileser III", "Tiglath-Pileser III", "Neo-Assyrian Empire", -745, -727,
         "remade Assyria into the first great military empire"),
        ("Sargon II", "Sargon II", "Neo-Assyrian Empire", -722, -705,
         "Assyrian conqueror; built Dur-Sharrukin"),
        ("Sennacherib", "Sennacherib", "Neo-Assyrian Empire", -705, -681,
         "rebuilt Nineveh and besieged Jerusalem"),
        ("Ashurbanipal", "Ashurbanipal", "Neo-Assyrian Empire", -668, -627,
         "gathered the great library of Nineveh"),
        ("Nebuchadnezzar II", "Nebuchadnezzar II", "Neo-Babylonian Empire", -605, -562,
         "built Babylon's Hanging Gardens; exiled the Judeans"),
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
        ("Ardashir I", "Ardashir I", "Sasanian Empire", 224, 242,
         "founder of the Sasanian Persian empire"),
        ("Shapur I", "Shapur I", "Sasanian Empire", 240, 270,
         "captured a Roman emperor, Valerian"),
        ("Khosrow I", "Khosrow I", "Sasanian Empire", 531, 579,
         "the Just; high point of Sasanian Persia"),
        ("Khosrow II", "Khosrow II", "Sasanian Empire", 590, 628,
         "last great Sasanian king before the Arab conquest"),
        ("Muawiyah I", "Muawiyah I", "Umayyad Caliphate", 661, 680,
         "founder of the Umayyad Caliphate"),
        ("Al-Mansur", "Al-Mansur", "Abbasid Caliphate", 754, 775,
         "founder of Baghdad and the Abbasid state"),
        ("Abd al-Rahman I", "Abd al-Rahman I", "Emirate of Córdoba", 756, 788,
         "Umayyad survivor who founded Muslim Spain's emirate"),
        ("Harun al-Rashid", "Harun al-Rashid", "Abbasid Caliphate", 786, 809,
         "caliph of the Baghdad golden age and the Arabian Nights"),
        ("Al-Ma'mun", "Al-Ma'mun", "Abbasid Caliphate", 813, 833,
         "patron of the House of Wisdom"),
        ("Abd al-Rahman III", "Abd al-Rahman III", "Caliphate of Córdoba", 912, 961,
         "raised Córdoba to a caliphate and a beacon of learning"),
        ("Alp Arslan", "Alp Arslan", "Seljuk Empire", 1063, 1072,
         "crushed Byzantium at Manzikert, opening Anatolia"),
        ("Malik-Shah I", "Malik-Shah I", "Seljuk Empire", 1072, 1092,
         "ruled the Seljuk Turks at their height"),
        ("Saladin", "Saladin", "Ayyubid Sultanate", 1174, 1193,
         "retook Jerusalem from the Crusaders"),
        ("Osman I", "Osman I", "Ottoman Empire", 1299, 1326,
         "founder of the Ottoman dynasty"),
        ("Murad I", "Murad I", "Ottoman Empire", 1362, 1389,
         "carried the Ottomans into the Balkans"),
        ("Bayezid I", "Bayezid I", "Ottoman Empire", 1389, 1402,
         "'the Thunderbolt'; checked only by Timur"),
        ("Mehmed the Conqueror", "Mehmed the Conqueror", "Ottoman Empire", 1451, 1481,
         "took Constantinople in 1453"),
        ("Ismail I", "Ismail I", "Safavid Empire", 1501, 1524,
         "founded Safavid Persia and made it Shi'a"),
        ("Selim I", "Selim I", "Ottoman Empire", 1512, 1520,
         "doubled the empire and took the caliphate"),
        ("Suleiman the Magnificent", "Suleiman the Magnificent", "Ottoman Empire", 1520, 1566,
         "the Lawgiver; the Ottoman zenith"),
        ("Tahmasp I", "Tahmasp I", "Safavid Empire", 1524, 1576,
         "long-reigning Safavid who held Persia together"),
        ("Abbas the Great", "Abbas the Great", "Safavid Empire", 1588, 1629,
         "remade Persia from his capital at Isfahan"),
        ("Murad IV", "Murad IV", "Ottoman Empire", 1623, 1640,
         "iron-willed sultan who retook Baghdad"),
        ("Nader Shah", "Nader Shah", "Afsharid Persia", 1736, 1747,
         "the 'Persian Napoleon'; sacked Delhi"),
        ("Karim Khan", "Karim Khan", "Zand dynasty", 1751, 1779,
         "brought a rare peace to 18th-century Persia"),
    ],
    "steppe": [
        ("Modu Chanyu", "Modu Chanyu", "Xiongnu", -209, -174,
         "forged the Xiongnu into a steppe empire that rivalled Han China"),
        ("Attila", "Attila", "Hunnic Empire", 434, 453,
         "the Hun; the 'Scourge of God'"),
        ("Bumin Qaghan", "Bumin Qaghan", "First Turkic Khaganate", 552, 552,
         "founder of the first Turkic empire of the steppe"),
        ("Genghis Khan", "Genghis Khan", "Mongol Empire", 1206, 1227,
         "founder of the largest contiguous land empire in history"),
        ("Batu Khan", "Batu Khan", "Golden Horde", 1227, 1255,
         "conquered the Rus' and founded the Golden Horde"),
        ("Ögedei Khan", "Ögedei Khan", "Mongol Empire", 1229, 1241,
         "great khan under whom the Mongols reached Europe"),
        ("Möngke Khan", "Möngke Khan", "Mongol Empire", 1251, 1259,
         "last khan to rule a united Mongol Empire"),
        ("Timur", "Timur", "Timurid Empire", 1370, 1405,
         "Tamerlane; built an empire from Samarkand"),
        ("Tokhtamysh", "Tokhtamysh", "Golden Horde", 1380, 1395,
         "briefly reunited the Golden Horde before Timur broke it"),
        ("Shah Rukh", "Shah Rukh", "Timurid Empire", 1405, 1447,
         "Timur's son; presided over a Timurid renaissance"),
        ("Ulugh Beg", "Ulugh Beg", "Timurid Empire", 1447, 1449,
         "the astronomer-king of Samarkand"),
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
        ("Pulakeshin II", "Pulakeshin II", "Chalukya dynasty", 610, 642,
         "Deccan emperor who checked Harsha in the north"),
        ("Rajaraja I", "Rajaraja I", "Chola Empire", 985, 1014,
         "made the Cholas a naval power across the Indian Ocean"),
        ("Rajendra Chola I", "Rajendra Chola I", "Chola Empire", 1014, 1044,
         "carried Chola arms to the Ganges and Srivijaya"),
        ("Prithviraj Chauhan", "Prithviraj Chauhan", "Chahamanas of Shakambhari", 1178, 1192,
         "Rajput king who fell to the Ghurids"),
        ("Qutb al-Din Aibak", "Qutb al-Din Aibak", "Delhi Sultanate", 1206, 1210,
         "first sultan of Delhi; raised the Qutb Minar"),
        ("Iltutmish", "Iltutmish", "Delhi Sultanate", 1211, 1236,
         "true organiser of the Delhi Sultanate"),
        ("Razia Sultana", "Razia Sultana", "Delhi Sultanate", 1236, 1240,
         "the only woman to rule the Delhi Sultanate"),
        ("Alauddin Khalji", "Alauddin Khalji", "Delhi Sultanate", 1296, 1316,
         "repelled the Mongols and pushed the Sultanate south"),
        ("Muhammad bin Tughluq", "Muhammad bin Tughluq", "Delhi Sultanate", 1325, 1351,
         "brilliant, erratic sultan of an over-stretched Delhi"),
        ("Krishnadevaraya", "Krishnadevaraya", "Vijayanagara Empire", 1509, 1529,
         "high point of the great southern Hindu empire"),
        ("Babur", "Babur", "Mughal Empire", 1526, 1530,
         "Timurid prince who founded the Mughal Empire"),
        ("Humayun", "Humayun", "Mughal Empire", 1530, 1556,
         "lost the Mughal throne and won it back"),
        ("Sher Shah Suri", "Sher Shah Suri", "Sur Empire", 1538, 1545,
         "reformer who briefly displaced the Mughals"),
        ("Akbar", "Akbar", "Mughal Empire", 1556, 1605,
         "the Great; built a tolerant, centralised Mughal state"),
        ("Maharana Pratap", "Maharana Pratap", "Mewar", 1572, 1597,
         "Rajput who defied Akbar from the hills of Mewar"),
        ("Jahangir", "Jahangir", "Mughal Empire", 1605, 1627,
         "connoisseur-emperor of the Mughal peace"),
        ("Shah Jahan", "Shah Jahan", "Mughal Empire", 1628, 1658,
         "builder of the Taj Mahal"),
        ("Aurangzeb", "Aurangzeb", "Mughal Empire", 1658, 1707,
         "expanded the empire to its limit and overstretched it"),
        ("Shivaji", "Shivaji", "Maratha Empire", 1674, 1680,
         "founder of the Maratha state"),
        ("Hyder Ali", "Hyder Ali", "Kingdom of Mysore", 1761, 1782,
         "soldier who made Mysore a power against the British"),
        ("Tipu Sultan", "Tipu Sultan", "Kingdom of Mysore", 1782, 1799,
         "the Tiger of Mysore"),
    ],
    "southeast-asia": [
        ("Suryavarman I", "Suryavarman I", "Khmer Empire", 1006, 1050,
         "expanded the Khmer Empire across the Chao Phraya"),
        ("Anawrahta", "Anawrahta", "Pagan Kingdom", 1044, 1077,
         "founder of the first Burmese empire, at Pagan"),
        ("Suryavarman II", "Suryavarman II", "Khmer Empire", 1113, 1150,
         "builder of Angkor Wat"),
        ("Parakramabahu I", "Parakramabahu I", "Kingdom of Polonnaruwa", 1153, 1186,
         "raised Sri Lanka to a brief golden age"),
        ("Jayavarman VII", "Jayavarman VII", "Khmer Empire", 1181, 1218,
         "greatest of the Angkor kings; built Angkor Thom"),
        ("Ram Khamhaeng", "Ram Khamhaeng", "Sukhothai Kingdom", 1279, 1298,
         "credited with the Thai alphabet"),
        ("Trần Nhân Tông", "Trần Nhân Tông", "Đại Việt", 1278, 1293,
         "twice threw back Kublai Khan's Mongols"),
        ("Raden Wijaya", "Raden Wijaya", "Majapahit", 1293, 1309,
         "founder of the Majapahit empire of Java"),
        ("Hayam Wuruk", "Hayam Wuruk", "Majapahit", 1350, 1389,
         "ruled Majapahit at its maritime height"),
        ("Lê Lợi", "Lê Lợi", "Đại Việt", 1428, 1433,
         "won Vietnam's independence from Ming China"),
        ("Borommatrailokkanat", "Borommatrailokkanat", "Ayutthaya Kingdom", 1448, 1488,
         "reorganised the Siamese state"),
        ("Bayinnaung", "Bayinnaung", "Toungoo Dynasty", 1550, 1581,
         "built the largest empire in Southeast Asian history"),
        ("Naresuan", "Naresuan", "Ayutthaya Kingdom", 1590, 1605,
         "won Siam's independence from Burma"),
        ("Taksin", "Taksin", "Thonburi Kingdom", 1767, 1782,
         "reunified Siam after the fall of Ayutthaya"),
    ],
    "east-asia": [
        ("Yellow Emperor", "Yellow Emperor", "Legendary China", -2697, -2598,
         "legendary founding sovereign of Chinese civilisation"),
        ("Yu the Great", "Yu the Great", "Xia dynasty", -2070, -2025,
         "legendary tamer of the floods; founder of the Xia"),
        ("Qin Shi Huang", "Qin Shi Huang", "Qin Dynasty", -221, -210,
         "first emperor to unify China; built the first Great Wall"),
        ("Emperor Gaozu of Han", "Emperor Gaozu of Han", "Han Dynasty", -202, -195,
         "peasant who founded the four-century Han dynasty"),
        ("Emperor Wu of Han", "Emperor Wu of Han", "Han Dynasty", -141, -87,
         "expanded Han China and opened the Silk Road"),
        ("Emperor Guangwu of Han", "Emperor Guangwu of Han", "Han Dynasty", 25, 57,
         "restored the Han dynasty after a usurpation"),
        ("Cao Pi", "Cao Pi", "Cao Wei", 220, 226,
         "ended the Han and founded Wei in the Three Kingdoms"),
        ("Liu Bei", "Liu Bei", "Shu Han", 221, 223,
         "founder of Shu Han, hero of the Three Kingdoms"),
        ("Sun Quan", "Sun Quan", "Eastern Wu", 229, 252,
         "founder of Eastern Wu in the Three Kingdoms"),
        ("Emperor Wu of Jin", "Emperor Wu of Jin", "Jin Dynasty", 266, 290,
         "reunified China after the Three Kingdoms"),
        ("Gwanggaeto the Great", "Gwanggaeto the Great", "Goguryeo", 391, 412,
         "conqueror-king who expanded Korea's Goguryeo"),
        ("Emperor Wen of Sui", "Emperor Wen of Sui", "Sui Dynasty", 581, 604,
         "reunified China after centuries of division"),
        ("Prince Shōtoku", "Prince Shōtoku", "Asuka Japan", 593, 622,
         "regent who shaped early Japanese statehood and Buddhism"),
        ("Emperor Gaozu of Tang", "Emperor Gaozu of Tang", "Tang Dynasty", 618, 626,
         "founder of the Tang dynasty"),
        ("Emperor Taizong of Tang", "Emperor Taizong of Tang", "Tang Dynasty", 626, 649,
         "model emperor of China's Tang golden age"),
        ("Munmu of Silla", "Munmu of Silla", "Silla", 661, 681,
         "unified the Korean peninsula under Silla"),
        ("Wu Zetian", "Wu Zetian", "Zhou (Tang interregnum)", 690, 705,
         "the only woman to rule China as emperor"),
        ("Emperor Xuanzong of Tang", "Emperor Xuanzong of Tang", "Tang Dynasty", 712, 756,
         "presided over Tang's cultural peak, then the An Lushan ruin"),
        ("Emperor Kanmu", "Emperor Kanmu", "Imperial Japan", 781, 806,
         "moved the Japanese capital to Heian (Kyoto)"),
        ("Taejo of Goryeo", "Taejo of Goryeo", "Goryeo", 918, 943,
         "founder of the Goryeo dynasty that named Korea"),
        ("Emperor Taizu of Song", "Emperor Taizu of Song", "Song Dynasty", 960, 976,
         "reunified China and founded the Song"),
        ("Emperor Huizong of Song", "Emperor Huizong of Song", "Song Dynasty", 1100, 1126,
         "artist-emperor who lost the north to the Jurchens"),
        ("Minamoto no Yoritomo", "Minamoto no Yoritomo", "Kamakura Shogunate", 1192, 1199,
         "first shogun; began rule by the samurai"),
        ("Kublai Khan", "Kublai Khan", "Yuan Dynasty", 1260, 1294,
         "Mongol grandson of Genghis who founded the Yuan in China"),
        ("Hōjō Tokimune", "Hōjō Tokimune", "Kamakura Shogunate", 1268, 1284,
         "regent who repelled the Mongol invasions of Japan"),
        ("Ashikaga Takauji", "Ashikaga Takauji", "Ashikaga Shogunate", 1338, 1358,
         "founded the Ashikaga shogunate"),
        ("Hongwu Emperor", "Hongwu Emperor", "Ming Dynasty", 1368, 1398,
         "peasant rebel who drove out the Mongols and founded the Ming"),
        ("Taejo of Joseon", "Taejo of Joseon", "Joseon", 1392, 1398,
         "founder of Korea's five-century Joseon dynasty"),
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
        ("Chongzhen Emperor", "Chongzhen Emperor", "Ming Dynasty", 1627, 1644,
         "last Ming emperor; hanged himself as rebels took Beijing"),
        ("Kangxi Emperor", "Kangxi Emperor", "Qing Dynasty", 1661, 1722,
         "one of the longest reigns in history; consolidated Qing rule"),
        ("Tokugawa Yoshimune", "Tokugawa Yoshimune", "Tokugawa Shogunate", 1716, 1745,
         "reforming shogun of Edo Japan"),
        ("Yongzheng Emperor", "Yongzheng Emperor", "Qing Dynasty", 1722, 1735,
         "hard-working emperor who centralised Qing power"),
        ("Yeongjo of Joseon", "Yeongjo of Joseon", "Joseon", 1724, 1776,
         "longest-reigning Joseon king; a reformer"),
        ("Qianlong Emperor", "Qianlong Emperor", "Qing Dynasty", 1735, 1796,
         "ruled China at its largest and most prosperous"),
    ],
    "africa": [
        ("Narmer", "Narmer", "Early Dynastic Egypt", -3100, -3085,
         "unified Upper and Lower Egypt — the first pharaoh"),
        ("Djoser", "Djoser", "Old Kingdom of Egypt", -2670, -2640,
         "built the first pyramid, the Step Pyramid at Saqqara"),
        ("Khufu", "Khufu", "Old Kingdom of Egypt", -2589, -2566,
         "built the Great Pyramid of Giza"),
        ("Pepi II", "Pepi II Neferkare", "Old Kingdom of Egypt", -2278, -2184,
         "one of the longest reigns in recorded history"),
        ("Hatshepsut", "Hatshepsut", "New Kingdom of Egypt", -1479, -1458,
         "one of the few women to rule as pharaoh"),
        ("Thutmose III", "Thutmose III", "New Kingdom of Egypt", -1479, -1425,
         "warrior-pharaoh who built Egypt's largest empire"),
        ("Akhenaten", "Akhenaten", "New Kingdom of Egypt", -1353, -1336,
         "the heretic pharaoh who worshipped the sun-disc Aten"),
        ("Tutankhamun", "Tutankhamun", "New Kingdom of Egypt", -1332, -1323,
         "the boy-king of the golden mask"),
        ("Ramesses II", "Ramesses II", "New Kingdom of Egypt", -1279, -1213,
         "the Great; builder-pharaoh of Abu Simbel"),
        ("Taharqa", "Taharqa", "Kingdom of Kush", -690, -664,
         "Kushite pharaoh who ruled Egypt from Nubia"),
        ("Ptolemy I Soter", "Ptolemy I Soter", "Ptolemaic Kingdom", -305, -282,
         "general of Alexander who founded the Ptolemaic dynasty"),
        ("Ptolemy II Philadelphus", "Ptolemy II Philadelphus", "Ptolemaic Kingdom", -283, -246,
         "built the Library and Lighthouse of Alexandria"),
        ("Cleopatra", "Cleopatra", "Ptolemaic Kingdom", -51, -30,
         "last pharaoh of Egypt"),
        ("Ezana of Axum", "Ezana of Axum", "Kingdom of Aksum", 320, 360,
         "made Aksum (Ethiopia) a Christian kingdom"),
        ("Yaqub al-Mansur", "Yaqub al-Mansur", "Almohad Caliphate", 1184, 1199,
         "Almohad caliph who ruled from Morocco to al-Andalus"),
        ("Lalibela", "Gebre Mesqel Lalibela", "Zagwe dynasty", 1181, 1221,
         "Ethiopian king who hewed churches from the rock"),
        ("Sundiata Keita", "Sundiata Keita", "Mali Empire", 1235, 1255,
         "founder of the Mali Empire"),
        ("Baibars", "Baibars", "Mamluk Sultanate", 1260, 1277,
         "Mamluk sultan who broke the Mongols at Ain Jalut"),
        ("Mansa Musa", "Mansa Musa", "Mali Empire", 1312, 1337,
         "fabled for the gold of his pilgrimage to Mecca"),
        ("Amda Seyon I", "Amda Seyon I", "Ethiopian Empire", 1314, 1344,
         "expanded the Christian Ethiopian empire"),
        ("Sunni Ali", "Sunni Ali", "Songhai Empire", 1464, 1492,
         "built Songhai into West Africa's greatest empire"),
        ("Askia the Great", "Askia Muhammad I", "Songhai Empire", 1493, 1528,
         "organised Songhai and made Timbuktu a seat of learning"),
        ("Idris Alooma", "Idris Alooma", "Kanem–Bornu Empire", 1564, 1596,
         "reformer-sultan of Bornu around Lake Chad"),
        ("Amina", "Amina", "Zazzau", 1576, 1610,
         "warrior-queen of the Hausa city-state of Zazzau"),
        ("Ahmad al-Mansur", "Ahmad al-Mansur", "Saadi Sultanate", 1578, 1603,
         "Moroccan sultan whose army crossed the Sahara to take Songhai"),
        ("Nzinga of Ndongo", "Nzinga of Ndongo and Matamba", "Ndongo and Matamba", 1624, 1663,
         "queen who fought the Portuguese slave trade for decades"),
        ("Fasilides", "Fasilides", "Ethiopian Empire", 1632, 1667,
         "founded Gondar, Ethiopia's royal city"),
        ("Moulay Ismail", "Ismail Ibn Sharif", "Alawi Sultanate", 1672, 1727,
         "Morocco's iron sultan, builder of Meknes"),
        ("Osei Tutu", "Osei Tutu", "Ashanti Empire", 1701, 1717,
         "founder of the Ashanti Empire and its Golden Stool"),
    ],
    "americas": [
        ("Yax Kʼukʼ Moʼ", "K'inich Yax K'uk' Mo'", "Maya (Copán)", 426, 437,
         "founder of the Maya dynasty of Copán"),
        ("Pakal the Great", "K'inich Janaab' Pakal", "Maya (Palenque)", 615, 683,
         "long-reigning king of the Maya city of Palenque"),
        ("Kan Bahlam II", "K'inich Kan Bahlam II", "Maya (Palenque)", 684, 702,
         "Pakal's son; raised Palenque's great temples"),
        ("Eight Deer Jaguar Claw", "Eight Deer Jaguar Claw", "Mixtec (Tilantongo)", 1063, 1115,
         "Mixtec lord whose codices record his conquests"),
        ("Acamapichtli", "Acamapichtli", "Aztec Empire", 1376, 1395,
         "first tlatoani of the Aztec city of Tenochtitlan"),
        ("Itzcoatl", "Itzcoatl", "Aztec Empire", 1427, 1440,
         "founder of the Aztec Triple Alliance"),
        ("Nezahualcoyotl", "Nezahualcoyotl", "Texcoco", 1429, 1472,
         "poet-king of Texcoco"),
        ("Pachacuti", "Pachacuti", "Inca Empire", 1438, 1471,
         "transformed Cusco into the Inca Empire; built Machu Picchu"),
        ("Moctezuma I", "Moctezuma I", "Aztec Empire", 1440, 1469,
         "expanded the Aztec Empire across central Mexico"),
        ("Topa Inca Yupanqui", "Topa Inca Yupanqui", "Inca Empire", 1471, 1493,
         "Pachacuti's son; carried the Inca conquests far south"),
        ("Ahuitzotl", "Ahuitzotl", "Aztec Empire", 1486, 1502,
         "warrior-emperor of the Aztecs at their widest"),
        ("Huayna Capac", "Huayna Capac", "Inca Empire", 1493, 1527,
         "ruled the Inca Empire at its greatest extent"),
        ("Moctezuma II", "Moctezuma II", "Aztec Empire", 1502, 1520,
         "emperor when Cortés arrived"),
        ("Cuauhtémoc", "Cuauhtémoc", "Aztec Empire", 1520, 1521,
         "last Aztec emperor, who fought Cortés to the end"),
        ("Atahualpa", "Atahualpa", "Inca Empire", 1532, 1533,
         "last independent Inca emperor; killed by Pizarro"),
    ],
}

_TRANSLIT = str.maketrans({
    "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ø": "o", "Ø": "O",
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ð": "d", "þ": "th",
    "ı": "i",
})


def slugify(s):
    """ASCII, hyphenated slug — transliterates accents so ids stay clean
    (Ögedei -> ogedei-khan, Hōjō -> hojo-tokimune, Władysław -> wladyslaw)."""
    s = s.translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def make_record(name, wp, realm, rf, rt, blurb, region_key, **extra):
    """One pre-slug roster record (the shape both the curated table and the
    Wikidata augmenter produce)."""
    rec = {
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
    }
    rec.update(extra)
    return rec


def curated_records():
    """The hand-curated spine, as pre-slug records."""
    records = []
    for region_key, _label in REGIONS:
        for (name, wp, realm, rf, rt, blurb) in ROSTER.get(region_key, []):
            records.append(make_record(name, wp, realm, rf, rt, blurb, region_key,
                                       source="curated"))
    return records


def finalize(records):
    """Sort chronologically, assign stable slug ids + catalogue order + civ links.
    Records are de-duplicated by wikipedia title (curated wins over augmented)."""
    seen_wp = {}
    deduped = []
    for r in records:
        key = (r.get("wp") or r["name"]).lower()
        if key in seen_wp:
            # keep the curated one if a duplicate appears
            if r.get("source") == "curated" and deduped[seen_wp[key]].get("source") != "curated":
                deduped[seen_wp[key]] = r
            continue
        seen_wp[key] = len(deduped)
        deduped.append(r)

    deduped.sort(key=lambda e: (e["reign_from"], e["name"]))
    seen = {}
    out = []
    for i, e in enumerate(deduped, start=1):
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
            "blurb": e.get("blurb"),
            "reign_from": e["reign_from"],
            "reign_to": e["reign_to"],
            "year_from": e["reign_from"],
            "year_to": e["reign_to"],
            "wp": e["wp"],
            "source": e.get("source", "curated"),
            "civ_wiki": civ_url(slug),
        })
    return out


def write_seed(out):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "seed.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def report(out):
    print(f"seed.json: {len(out)} rulers")
    by_region, by_era, by_source = {}, {}, {}
    for e in out:
        by_region[e["region"]] = by_region.get(e["region"], 0) + 1
        by_era[e["era"]] = by_era.get(e["era"], 0) + 1
        by_source[e.get("source", "curated")] = by_source.get(e.get("source", "curated"), 0) + 1
    print("by region:")
    for k, _l in REGIONS:
        print(f"   {k:16} {by_region.get(k, 0)}")
    print("by era:", {k: by_era.get(k, 0) for k, _l, _u in ERAS})
    print("by source:", by_source)
    yrs = [e["reign_from"] for e in out] + [e["reign_to"] for e in out]
    print(f"data span: {min(yrs)} .. {max(yrs)}  (meridian floor {MERIDIAN_FLOOR})")
    print(f"civ-linked: {len([e for e in out if e.get('civ_wiki')])}")
    ids = [e["id"] for e in out]
    assert len(ids) == len(set(ids)), "duplicate slug ids!"
    for probe in (-2600, -1250, -220, 100, 800, 1200, 1550, 1700):
        live = [e["name"] for e in out if e["reign_from"] <= probe <= e["reign_to"]]
        ylabel = f"{-probe} BC" if probe < 0 else f"AD {probe}"
        print(f"  {ylabel:8}: {len(live)} reigning — {', '.join(live[:9])}")


def main():
    out = finalize(curated_records())
    write_seed(out)
    report(out)


if __name__ == "__main__":
    main()
