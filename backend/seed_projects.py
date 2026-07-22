"""
One-off import of the company's project masterlist into the Project table, so
the Maintenance Report tool's project picker starts populated instead of empty.
This is a point-in-time copy, not a live sync -- re-run manually (it's
idempotent: updates client/name for existing codes, adds any new ones) whenever
the masterlist gains projects you also want available here.

Usage: python seed_projects.py
"""
from database import SessionLocal, init_db
from models import Project

# Copied from "PROJECT MASTERLIST.xlsx" (Project ID / Project / Client-Main
# Contractor columns). 'code' must match the Photo-to-Drive bot's project ID
# for Drive folder search to find the right photos.
PROJECTS = [
    {'code': 'APSN', 'name': 'APSN Chao Yang School and Tanglin School', 'client': 'Thong Hup Gardens Pte Ltd'},
    {'code': 'ASJC', 'name': 'Anderson Serangoon School', 'client': 'Thong Hup Gardens Pte Ltd'},
    {'code': 'AGFarm', 'name': 'AG Farm', 'client': 'Artisan Green Pte Ltd'},
    {'code': 'AST', 'name': 'AST Project', 'client': 'Eco Garden Pte Ltd'},
    {'code': 'B69ESG', 'name': 'Block 69 Green Wall', 'client': 'Vidacity-Npark'},
    {'code': 'CANNHILL', 'name': 'Canning Hill', 'client': 'Nature Landscapes Pte Ltd'},
    {'code': 'CCKWW', 'name': 'Choa Chu Kang Waterway', 'client': 'Chip Eng Seng (CES_SDC Pte Ltd)'},
    {'code': 'CR101', 'name': 'Changi East Depot CR101', 'client': 'Cultigreen Pte Ltd'},
    {'code': 'CF201', 'name': 'CF201- Enhance works for commuter infrastructure', 'client': 'Shincon Industrial Pte Ltd'},
    {'code': 'C12A', 'name': 'Changi East C12A', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'CMTPC', 'name': 'Clementi Polyclinic', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'CONEY', 'name': 'Coney Island', 'client': 'Nature Landscapes Pte Ltd'},
    {'code': 'C915A', 'name': 'C915A Hume', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'DE195', 'name': 'DE195 Site Office Greenwall', 'client': 'Gammon Pte Ltd'},
    {'code': 'ECC', 'name': 'SGH Elective Care Centre and New National Dental Centre Singapore (NDCS)', 'client': 'Penta-Ocean Construction Co., Ltd.'},
    {'code': 'HNSH', 'name': 'Hougang Nursing Home', 'client': 'Eco Garden Pte Ltd'},
    {'code': 'HICA T2', 'name': 'Hotel Indigo Changi Airport T2', 'client': 'Lum Chang Building Contractors Pte Ltd'},
    {'code': 'IWMF EPC1', 'name': 'Integrated Waste Management Facility - Tuas Nexus', 'client': 'China Harbour (Singapore) Engineering Company Pte Ltd'},
    {'code': 'JDNH', 'name': 'Jalan Damai Nursing Home', 'client': "Prince's Landscape Pte Ltd"},
    {'code': '2JP', 'name': '2 Jalan Papan Setsco', 'client': 'Cultigreen Pte Ltd'},
    {'code': 'JTCGR', 'name': 'JTC Senoko Green Roof', 'client': 'Mao Sheng Quanji Construction Pte Ltd'},
    {'code': 'JRPSS', 'name': 'Jurong Pier Substation', 'client': 'Chuan Lim Construction Pte Ltd JV Buildstar'},
    {'code': 'JN2C26', 'name': 'Jurong East N2C26', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'JN3C31', 'name': 'Jurong West N3C31 & C32', 'client': 'Exklusive Landscape'},
    {'code': 'JN1C34', 'name': 'Jurong west N1C34', 'client': 'GG Landscape'},
    {'code': 'J101', 'name': 'Tengah Depot for Jurong Region Line', 'client': 'China Railway 11 Bureau Group Corporation (Singapore Branch)'},
    {'code': 'J102', 'name': 'Choa Chu Kang Station for JR line', 'client': 'Shanghai Tunnel Engineering Co (Singapore) Pte Ltd'},
    {'code': 'KCDE GR', 'name': 'KCDE C821A Green Roof', 'client': 'Woh Hup Pte Ltd'},
    {'code': 'KCDE IRR', 'name': 'KCDE C821A Dripline', 'client': 'Perfect Watertech Pte Ltd'},
    {'code': 'KLA', 'name': 'KLA industrial building @ AMK', 'client': 'The BLG Group Pte Ltd'},
    {'code': 'HMB1A', 'name': 'Habourfront MB1A', 'client': 'Kok Keong Landscape Pte Ltd'},
    {'code': 'KRFac', 'name': 'Kranji Factory', 'client': 'Yao Heng Builders Pte Ltd'},
    {'code': 'NLT', 'name': 'Netlink trust', 'client': 'TEHC International Pte Ltd'},
    {'code': 'NTUEC', 'name': 'Nanyang Executive Centre', 'client': 'Lian Soon Construction Pte Ltd'},
    {'code': 'ORG', 'name': 'Orange Grove', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'DL', 'name': 'Project DL- Attap Valley Road', 'client': 'Ghee Garden Landscape + Construction Pte Ltd'},
    {'code': 'PRP', 'name': 'Pasir Ris Park', 'client': 'Citysprouts Pte Ltd'},
    {'code': 'PRSC', 'name': 'Punggol Recreation Sports Centre', 'client': 'Nature Landscapes Pte Ltd'},
    {'code': 'PNC11', 'name': 'PNC11', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'PDD', 'name': 'Punggol Digital District', 'client': 'Woh Hup Pte Ltd'},
    {'code': 'RC203', 'name': 'Green roof bus shelter Realignment of Merpati Road', 'client': 'CCECC Singapore Pte Ltd'},
    {'code': 'RWS', 'name': 'Resorts World Sentosa', 'client': 'Green Forest Landscape Pte Ltd'},
    {'code': 'SAS', 'name': 'Singapore American School', 'client': 'Thong Hup Gardens Pte Ltd'},
    {'code': 'SGR', 'name': 'Sengkang Grand Residences', 'client': 'Nature Landscapes Pte Ltd'},
    {'code': 'STSGR', 'name': 'Sentosa - Green Roof', 'client': 'Sentosa Development Corporation'},
    {'code': 'SHAW', 'name': 'Shaw Tower', 'client': 'Kok Keong Landscape Pte Ltd'},
    {'code': 'SHIM', 'name': 'Shimano Factory in Juong Innocation District', 'client': 'Takenaka Singapore Private Limited'},
    {'code': 'SLT', 'name': 'Singapore Land Tower', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'SO DRAMA', 'name': 'So Drama (SDE)', 'client': 'Tiong Seng Contractors Pte Ltd'},
    {'code': 'SPDE', 'name': 'C810 Sengkang-Punggol Depot Expansion', 'client': 'Sato Kogyo (S) Pte Ltd'},
    {'code': 'SSH', 'name': 'Kallang Sport Hub', 'client': 'TTK Services Pte Ltd'},
    {'code': 'TKNH', 'name': 'Tanjong Katong Nursing Home', 'client': 'CMC Construction Pte Ltd'},
    {'code': 'TJNH', 'name': 'Taman Jurong Nursing Home', 'client': 'Cultigreen Pte Ltd'},
    {'code': 'TNS42', 'name': 'Tampines Nursing Home St 42', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'TSH GR', 'name': 'Temasek Shop House (GR)', 'client': 'Landscape Engineering Pte Ltd'},
    {'code': 'TJC', 'name': 'Temasek Junior College', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'TengahC2', 'name': 'Tengah Garden C2', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'TengahC5', 'name': 'Tengah C5', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'TengahPC6', 'name': 'Tengah Park C6', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'TengahGC6', 'name': 'Tengah Garden C6', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'TPYROH', 'name': 'Toa Payoh Renewal of Heartland', 'client': 'Shin Khai Construction Pte Ltd'},
    {'code': 'TTSH', 'name': 'Tan Tock Seng Hospital', 'client': 'Chip Eng Seng Contractors (1988) Pte Ltd'},
    {'code': 'TAVE6', 'name': 'Tuas Ave 6', 'client': 'Buildstar contractor'},
    {'code': 'WESTC', 'name': 'West Coast', 'client': 'City Sprouts'},
    {'code': 'WIPE7', 'name': 'Woodlands Industrial Park E7 (WIPE7)', 'client': 'Precise Development Pte Ltd'},
    {'code': 'WN3C16', 'name': 'Woodlands N3C16', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'WCE', 'name': 'Woodlands Checkpoint Extension', 'client': 'Woh Hup Pte Ltd'},
    {'code': 'YTSQ', 'name': 'Yew Tee Square', 'client': 'Urban Landscapes Pte Ltd'},
    {'code': 'YSC3', 'name': 'Yishun Bus stop C3', 'client': "Prince's Landscape Pte Ltd"},
    {'code': 'ARCADY', 'name': 'Youth Facility @ Jalan Bahar', 'client': 'Elite Landscape Pte Ltd'},
    {'code': '27SLHZ', 'name': '27 Senoko Loop', 'client': 'Hongze Construction Pte Ltd'},
    {'code': '39RR', 'name': '39 Robinson Road', 'client': "Prince's Landscape Pte Ltd"},
    {'code': '9KSR', 'name': '9 Koon Seng Road', 'client': 'Private client (housing)'},
    {'code': 'TAVE13', 'name': 'Tuas Ave 13', 'client': "Prince's Landscape Pte Ltd"},
    {'code': '61LP', 'name': '61 Leedon Park', 'client': 'Kok Keong Landscape Pte Ltd'},
    {'code': 'MARSCC', 'name': 'Marsiling CC', 'client': 'Elite Landscape Pte Ltd'},
    {'code': 'GREENRIDGE', 'name': 'Greenridge Shopping Centre', 'client': 'Urban Landscape Pte Ltd'},
    {'code': 'CPG', 'name': 'CPG Office', 'client': 'CPG Consultants Pte Ltd'},
    {'code': 'GD', 'name': 'A&A works at Gombak Drive', 'client': 'V-green Landscape and construction Pte Ltd'},
    {'code': 'SSCFAH', 'name': 'SSC FAH', 'client': 'Landscape Engineering Pte Ltd'},
    {'code': 'ECG', 'name': 'Eunos Crescent greenhouse', 'client': 'THK bloom ESLP @ Eunos Crescent'},
    {'code': 'SHAW PLAZA', 'name': 'Shaw Plaza', 'client': 'Gennal Industries Pte Ltd'},
    {'code': 'RRF', 'name': 'RRF Tengah Town', 'client': 'Landscape Engineering Pte Ltd'},
    {'code': 'SLT-TAKENAKA', 'name': 'Singapore Land Tower', 'client': 'Takenaka Corporation'},
    {'code': 'ComcropGR', 'name': 'Comcrop Greenroof', 'client': 'Comcrop'},
    {'code': 'TPID', 'name': 'Tao Payoh Sportshub', 'client': 'Kajima Overseas Asia (singapore) Pte Ltd'},
    {'code': 'SORA', 'name': 'Sora project at Yuan Ching Road', 'client': 'City Garden Pte Ltd'},
    {'code': 'Wycombe', 'name': 'Wycombe Abbey School', 'client': 'Wee Hur Construction Pte Ltd'},
    {'code': 'SVS', 'name': 'Substation at Sunview Drive', 'client': 'Woh Hup Pte Ltd'},
    {'code': 'WIPE9', 'name': 'Woodlands Industrial Park E9', 'client': 'Kim Seng Heng'},
    {'code': 'HOYT', 'name': 'Heart of Yew Tee', 'client': 'Harford Engineering Pte Ltd'},
    {'code': 'FACWIPE7', 'name': 'Factory at Woodlands Industrial Park E7', 'client': 'Tat Hin Builders Pte Ltd'},
    {'code': 'EGH', 'name': 'Bedok Eastern Hospital', 'client': 'Santarli JV Obayashi'},
    {'code': 'SGP2', 'name': 'Loyang Data Center', 'client': "Prince's Landscape Pte Ltd"},
]


def seed():
    init_db()
    db = SessionLocal()
    try:
        existing = {p.code: p for p in db.query(Project).all()}
        added = updated = 0
        for row in PROJECTS:
            if row['code'] in existing:
                proj = existing[row['code']]
                if proj.name != row['name'] or proj.client != row['client']:
                    proj.name = row['name']
                    proj.client = row['client']
                    updated += 1
            else:
                db.add(Project(code=row['code'], name=row['name'], client=row['client']))
                added += 1
        db.commit()
        print(f"Seeded {added} new project(s), updated {updated}; {len(existing)} already existed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
