"""
One-off import of the Photo-to-Drive bot's config/projects.txt into the Project
table, so the Maintenance Report tool's project picker starts with all existing
projects instead of an empty list. This is a point-in-time copy, not a live sync --
re-run manually (it's idempotent, skips codes that already exist) if the bot's
list gains new projects you also want available here.

Usage: python seed_projects.py
"""
import re

from database import SessionLocal, init_db
from models import Project

# Copied from Photo-to-Drive's config/projects.txt (format: "ID | Name").
# Addresses aren't in that file -- left blank, fill in per-project on first use.
RAW_PROJECTS = """
APSN | APSN Chao Yang School and Tanglin School
ASJC | Anderson Serangoon School
AGFarm | AG Farm
AST | AST Project
B69ESG | Block 69 Green Wall
CANNHILL | Canning Hill
CCKWW | Choa Chu Kang Waterway
CR101 | Changi East Depot CR101
CF201 | CF201- Enhance works for commuter infrastructure
C12A | Changi East C12A
CMTPC | Clementi Polyclinic
CONEY | Coney Island
C915A | C915A Hume
DE195 | DE195 Site Office Greenwall
ECC | SGH Elective Care Centre and New National Dental Centre Singapore (NDCS)
HNSH | Hougang Nursing Home
HICA T2 | Hotel Indigo Changi Airport T2
IWMF EPC1 | Integrated Waste Management Facility - Tuas Nexus
JDNH | Jalan Damai Nursing Home
2JP | 2 Jalan Papan Setsco
JTCGR | JTC Senoko Green Roof
JRPSS | Jurong Pier Substation
JN2C26 | Jurong East N2C26
JN3C31 | Jurong West N3C31 & C32
JN1C34 | Jurong west N1C34
J101 | Tengah Depot for Jurong Region Line
J102 | Choa Chu Kang Station for JR line
KCDE GR | KCDE C821A Green Roof
KCDE IRR | KCDE C821A Dripline
KLA | KLA industrial building @ AMK
HMB1A | Habourfront MB1A
KRFac | Kranji Factory
NLT | Netlink trust
NTUEC | Nanyang Executive Centre
ORG | Orange Grove
DL | Project DL- Attap Valley Road
PRP | Pasir Ris Park
PRSC | Punggol Recreation Sports Centre
PNC11 | PNC11
PDD | Punggol Digital District
RC203 | Green roof bus shelter Realignment of Merpati Road
RWS | Resorts World Sentosa
SAS | Singapore American School
SGR | Sengkang Grand Residences
STSGR | Sentosa - Green Roof
SHAW | Shaw Tower
SHIM | Shimano Factory in Juong Innocation District
SLT | Singapore Land Tower
SO DRAMA | So Drama (SDE)
SPDE | C810 Sengkang-Punggol Depot Expansion
SSH | Kallang Sport Hub
TKNH | Tanjong Katong Nursing Home
TJNH | Taman Jurong Nursing Home
TNS42 | Tampines Nursing Home St 42
TSH GR | Temasek Shop House (GR)
TJC | Temasek Junior College
TengahC2 | Tengah Garden C2
TengahC5 | Tengah C5
TengahPC6 | Tengah Park C6
TengahGC6 | Tengah Garden C6
TPYROH | Toa Payoh Renewal of Heartland
TTSH | Tan Tock Seng Hospital
TAVE6 | Tuas Ave 6
WESTC | West Coast
WIPE7 | Woodlands Industrial Park E7 (WIPE7)
WN3C16 | Woodlands N3C16
WCE | Woodlands Checkpoint Extension
YTSQ | Yew Tee Square
YSC3 | Yishun Bus stop C3
ARCADY | Youth Facility @ Jalan Bahar
27SLHZ | 27 Senoko Loop
39RR | 39 Robinson Road
9KSR | 9 Koon Seng Road
TAVE13 | Tuas Ave 13
61LP | 61 Leedon Park
MARSCC | Marsiling CC
GREENRIDGE | Greenridge Shopping Centre
CPG | CPG Office
GD | A&A works at Gombak Drive
SSCFAH | SSC FAH
ECG | Eunos Crescent greenhouse
SHAW PLAZA | Shaw Plaza
RRF | RRF Tengah Town
SLT-TAKENAKA | Singapore Land Tower
ComcropGR | Comcrop Greenroof
TPID | Tao Payoh Sportshub
SORA | Sora project at Yuan Ching Road
Wycombe | Wycombe Abbey School
SVS | Substation at Sunview Drive
WIPE9 | Woodlands Industrial Park E9
HOYT | Heart of Yew Tee
FACWIPE7 | Factory at Woodlands Industrial Park E7
EGH | Bedok Eastern Hospital
""".strip()


def parse_projects():
    projects = []
    for line in RAW_PROJECTS.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        code = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else code
        projects.append((code, name))
    return projects


def seed():
    init_db()
    db = SessionLocal()
    try:
        existing_codes = {c for (c,) in db.query(Project.code).all()}
        added = 0
        for code, name in parse_projects():
            if code in existing_codes:
                continue
            db.add(Project(code=code, name=name))
            added += 1
        db.commit()
        print(f"Seeded {added} new project(s); {len(existing_codes)} already existed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
