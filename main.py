from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite, os, math

app = FastAPI(title="RescueConnect V2 API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB = "rescue_v2.db"

# ── VEHICLE LOGIC ──
VEHICLE_CONFIG = {
    "Flood":      [("🚤","Rescue Boat",10),("🚁","Helicopter",50),("🚑","Ambulance",15)],
    "Fire":       [("🚒","Fire Truck",5),("🚑","Ambulance",8),("🚐","Rescue Van",20)],
    "Earthquake": [("🚧","Debris Clearance",15),("🚑","Ambulance",10),("🏗","Crane Unit",30),("🐕","K9 Unit",25)],
    "Medical":    [("🚑","Ambulance",5),("🏥","Mobile Med Unit",20),("🚁","Air Ambulance",50)],
    "Landslide":  [("🚧","Excavator",10),("🚑","Ambulance",8),("🚁","Helicopter",40),("🐕","K9 Unit",20)],
    "Cyclone":    [("🚌","Evacuation Bus",40),("🚑","Ambulance",15),("🚁","Helicopter",60),("🚤","Rescue Boat",20)],
}

def calc_vehicles(disaster, people):
    cfg = VEHICLE_CONFIG.get(disaster, VEHICLE_CONFIG["Flood"])
    return [{"icon":ic,"name":nm,"count":max(1,math.ceil(people/per))} for ic,nm,per in cfg]

# ── DB INIT ──
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS sos_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, location TEXT NOT NULL,
            emergency TEXT NOT NULL, people INTEGER DEFAULT 1,
            details TEXT, status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT, area TEXT, skills TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, location TEXT NOT NULL,
            contact TEXT, beds_total INTEGER DEFAULT 0,
            beds_available INTEGER DEFAULT 0, icu_available INTEGER DEFAULT 0,
            blood_units TEXT DEFAULT '{}', status TEXT DEFAULT 'Active',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS police_depts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_name TEXT NOT NULL, location TEXT NOT NULL,
            contact TEXT, officers_deployed INTEGER DEFAULT 0,
            vehicles_available INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Active',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, category TEXT NOT NULL,
            quantity INTEGER DEFAULT 0, unit TEXT DEFAULT 'units',
            location TEXT, last_updated TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS food_distribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camp_name TEXT NOT NULL, location TEXT NOT NULL,
            meals_distributed INTEGER DEFAULT 0, meals_capacity INTEGER DEFAULT 0,
            water_liters INTEGER DEFAULT 0, ration_kits INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Active',
            last_updated TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS rescued_people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, age INTEGER,
            gender TEXT, rescue_location TEXT NOT NULL,
            rescued_by TEXT, current_location TEXT,
            medical_condition TEXT DEFAULT 'Stable',
            family_contact TEXT, notes TEXT,
            rescued_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """)
        await db.commit()
        # Seed demo data if empty
        cur = await db.execute("SELECT COUNT(*) FROM hospitals")
        count = (await cur.fetchone())[0]
        if count == 0:
            await db.executescript("""
            INSERT INTO hospitals (name,location,contact,beds_total,beds_available,icu_available,blood_units,status)
            VALUES
            ('Amravati General Hospital','Amravati City','0721-2223344',300,45,8,'{"A+":12,"B+":8,"O+":15}','Active'),
            ('Daryapur Rural Hospital','Daryapur','07220-222111',80,12,2,'{"A+":4,"O+":6}','Active'),
            ('Warud Primary Health Center','Warud','07223-244001',30,8,0,'{"B+":2}','Overloaded');

            INSERT INTO police_depts (station_name,location,contact,officers_deployed,vehicles_available,status)
            VALUES
            ('Amravati City Police','Amravati','0721-2662100',45,12,'Active'),
            ('Daryapur Police Station','Daryapur','07220-222333',18,4,'Active'),
            ('Warud Police Station','Warud','07223-244200',12,3,'Active');

            INSERT INTO resources (name,category,quantity,unit,location)
            VALUES
            ('Life Jackets','Rescue Equipment',250,'pieces','NDRF Warehouse, Amravati'),
            ('Rescue Ropes','Rescue Equipment',80,'rolls','NDRF Warehouse, Amravati'),
            ('First Aid Kits','Medical',150,'kits','District Hospital Store'),
            ('Oxygen Cylinders','Medical',40,'cylinders','Amravati General Hospital'),
            ('Tents','Shelter',120,'units','Civil Lines Store'),
            ('Blankets','Shelter',800,'pieces','Civil Lines Store'),
            ('Drinking Water Pouches','Food & Water',5000,'pouches','Food Corp Warehouse'),
            ('Ready Meals (MRE)','Food & Water',2000,'packets','Food Corp Warehouse'),
            ('Generators','Power',15,'units','PWD Department'),
            ('Flashlights','Power',200,'pieces','NDRF Warehouse, Amravati');

            INSERT INTO food_distribution (camp_name,location,meals_distributed,meals_capacity,water_liters,ration_kits,status)
            VALUES
            ('Relief Camp Alpha','Govt High School, Ward 5',1240,1500,4500,320,'Active'),
            ('Relief Camp Beta','Community Hall, Daryapur',680,800,2200,180,'Active'),
            ('Relief Camp Gamma','Panchayat Building, Warud',210,400,900,90,'Active');

            INSERT INTO rescued_people (name,age,gender,rescue_location,rescued_by,current_location,medical_condition,family_contact)
            VALUES
            ('Ramesh Khade',52,'Male','Near Wardha River Bridge','NDRF Team A','Relief Camp Alpha','Stable','9876543210'),
            ('Sunita Bai',38,'Female','Daryapur Flood Zone','Local Volunteers','Amravati General Hospital','Minor Injuries','9812345678'),
            ('Ankit Deshmukh',8,'Male','Morshi Village','NDRF Team B','Relief Camp Beta','Stable','9898989898');
            """)
            await db.commit()

@app.on_event("startup")
async def startup():
    await init_db()

# ══ MODELS ══
class SOSRequest(BaseModel):
    name: str; location: str; emergency: str; people: int = 1; details: Optional[str] = ""

class SOSStatus(BaseModel):
    status: str

class Volunteer(BaseModel):
    name: str; phone: Optional[str]=""; area: Optional[str]=""; skills: Optional[List[str]]=[]

class Hospital(BaseModel):
    name: str; location: str; contact: Optional[str]=""
    beds_total: int=0; beds_available: int=0; icu_available: int=0
    blood_units: Optional[str]="{}"; status: Optional[str]="Active"

class HospitalUpdate(BaseModel):
    beds_available: Optional[int]=None; icu_available: Optional[int]=None
    blood_units: Optional[str]=None; status: Optional[str]=None

class PoliceStation(BaseModel):
    station_name: str; location: str; contact: Optional[str]=""
    officers_deployed: int=0; vehicles_available: int=0; status: Optional[str]="Active"

class PoliceUpdate(BaseModel):
    officers_deployed: Optional[int]=None; vehicles_available: Optional[int]=None; status: Optional[str]=None

class Resource(BaseModel):
    name: str; category: str; quantity: int=0; unit: str="units"; location: Optional[str]=""

class ResourceUpdate(BaseModel):
    quantity: int

class FoodCamp(BaseModel):
    camp_name: str; location: str; meals_capacity: int=0
    meals_distributed: int=0; water_liters: int=0; ration_kits: int=0; status: Optional[str]="Active"

class FoodUpdate(BaseModel):
    meals_distributed: Optional[int]=None; water_liters: Optional[int]=None
    ration_kits: Optional[int]=None; status: Optional[str]=None

class RescuedPerson(BaseModel):
    name: str; age: Optional[int]=None; gender: Optional[str]=""
    rescue_location: str; rescued_by: Optional[str]=""
    current_location: Optional[str]=""; medical_condition: Optional[str]="Stable"
    family_contact: Optional[str]=""; notes: Optional[str]=""

class RescuedUpdate(BaseModel):
    current_location: Optional[str]=None; medical_condition: Optional[str]=None
    family_contact: Optional[str]=None; notes: Optional[str]=None

# ══ HELPER ══
async def fetchall(query, params=()):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, params)
        return [dict(r) for r in await cur.fetchall()]

async def fetchone(query, params=()):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, params)
        row = await cur.fetchone()
        return dict(row) if row else None

async def execute(query, params=()):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid

# ══ SOS ══
@app.post("/api/sos", status_code=201)
async def create_sos(req: SOSRequest):
    vehicles = calc_vehicles(req.emergency, req.people)
    rid = await execute("INSERT INTO sos_requests (name,location,emergency,people,details) VALUES (?,?,?,?,?)",
        (req.name,req.location,req.emergency,req.people,req.details))
    return {"id":rid,"message":"SOS sent","vehicles_dispatched":vehicles}

@app.get("/api/sos")
async def list_sos():
    rows = await fetchall("SELECT * FROM sos_requests ORDER BY id DESC")
    for r in rows: r["vehicles"] = calc_vehicles(r["emergency"], r["people"])
    return rows

@app.patch("/api/sos/{sid}")
async def update_sos(sid: int, body: SOSStatus):
    if body.status not in ("Pending","Active","Resolved"): raise HTTPException(400,"Invalid status")
    await execute("UPDATE sos_requests SET status=? WHERE id=?", (body.status, sid))
    return {"id":sid,"status":body.status}

@app.delete("/api/sos/{sid}")
async def delete_sos(sid: int):
    await execute("DELETE FROM sos_requests WHERE id=?", (sid,))
    return {"deleted":sid}

# ══ VOLUNTEERS ══
@app.post("/api/volunteers", status_code=201)
async def create_volunteer(vol: Volunteer):
    rid = await execute("INSERT INTO volunteers (name,phone,area,skills) VALUES (?,?,?,?)",
        (vol.name,vol.phone,vol.area,",".join(vol.skills)))
    return {"id":rid,"message":f"{vol.name} registered"}

@app.get("/api/volunteers")
async def list_volunteers():
    rows = await fetchall("SELECT * FROM volunteers ORDER BY id DESC")
    for r in rows: r["skills"] = r["skills"].split(",") if r["skills"] else []
    return rows

# ══ HOSPITALS ══
@app.get("/api/hospitals")
async def list_hospitals():
    return await fetchall("SELECT * FROM hospitals ORDER BY id")

@app.post("/api/hospitals", status_code=201)
async def add_hospital(h: Hospital):
    rid = await execute("INSERT INTO hospitals (name,location,contact,beds_total,beds_available,icu_available,blood_units,status) VALUES (?,?,?,?,?,?,?,?)",
        (h.name,h.location,h.contact,h.beds_total,h.beds_available,h.icu_available,h.blood_units,h.status))
    return {"id":rid,"message":"Hospital added"}

@app.patch("/api/hospitals/{hid}")
async def update_hospital(hid: int, body: HospitalUpdate):
    h = await fetchone("SELECT * FROM hospitals WHERE id=?", (hid,))
    if not h: raise HTTPException(404,"Not found")
    beds_av = body.beds_available if body.beds_available is not None else h["beds_available"]
    icu_av = body.icu_available if body.icu_available is not None else h["icu_available"]
    blood = body.blood_units if body.blood_units is not None else h["blood_units"]
    status = body.status if body.status else h["status"]
    await execute("UPDATE hospitals SET beds_available=?,icu_available=?,blood_units=?,status=? WHERE id=?",
        (beds_av,icu_av,blood,status,hid))
    return {"id":hid,"updated":True}

# ══ POLICE ══
@app.get("/api/police")
async def list_police():
    return await fetchall("SELECT * FROM police_depts ORDER BY id")

@app.post("/api/police", status_code=201)
async def add_police(p: PoliceStation):
    rid = await execute("INSERT INTO police_depts (station_name,location,contact,officers_deployed,vehicles_available,status) VALUES (?,?,?,?,?,?)",
        (p.station_name,p.location,p.contact,p.officers_deployed,p.vehicles_available,p.status))
    return {"id":rid,"message":"Station added"}

@app.patch("/api/police/{pid}")
async def update_police(pid: int, body: PoliceUpdate):
    p = await fetchone("SELECT * FROM police_depts WHERE id=?", (pid,))
    if not p: raise HTTPException(404,"Not found")
    officers = body.officers_deployed if body.officers_deployed is not None else p["officers_deployed"]
    vehicles = body.vehicles_available if body.vehicles_available is not None else p["vehicles_available"]
    status = body.status if body.status else p["status"]
    await execute("UPDATE police_depts SET officers_deployed=?,vehicles_available=?,status=? WHERE id=?",
        (officers,vehicles,status,pid))
    return {"id":pid,"updated":True}

# ══ RESOURCES ══
@app.get("/api/resources")
async def list_resources():
    return await fetchall("SELECT * FROM resources ORDER BY category,name")

@app.post("/api/resources", status_code=201)
async def add_resource(r: Resource):
    rid = await execute("INSERT INTO resources (name,category,quantity,unit,location) VALUES (?,?,?,?,?)",
        (r.name,r.category,r.quantity,r.unit,r.location))
    return {"id":rid,"message":"Resource added"}

@app.patch("/api/resources/{rid}")
async def update_resource(rid: int, body: ResourceUpdate):
    await execute("UPDATE resources SET quantity=?,last_updated=datetime('now','localtime') WHERE id=?",
        (body.quantity, rid))
    return {"id":rid,"quantity":body.quantity}

@app.delete("/api/resources/{rid}")
async def delete_resource(rid: int):
    await execute("DELETE FROM resources WHERE id=?", (rid,))
    return {"deleted":rid}

# ══ FOOD ══
@app.get("/api/food")
async def list_food():
    return await fetchall("SELECT * FROM food_distribution ORDER BY id")

@app.post("/api/food", status_code=201)
async def add_food_camp(f: FoodCamp):
    rid = await execute("INSERT INTO food_distribution (camp_name,location,meals_capacity,meals_distributed,water_liters,ration_kits,status) VALUES (?,?,?,?,?,?,?)",
        (f.camp_name,f.location,f.meals_capacity,f.meals_distributed,f.water_liters,f.ration_kits,f.status))
    return {"id":rid,"message":"Camp added"}

@app.patch("/api/food/{fid}")
async def update_food(fid: int, body: FoodUpdate):
    f = await fetchone("SELECT * FROM food_distribution WHERE id=?", (fid,))
    if not f: raise HTTPException(404,"Not found")
    meals = body.meals_distributed if body.meals_distributed is not None else f["meals_distributed"]
    water = body.water_liters if body.water_liters is not None else f["water_liters"]
    kits = body.ration_kits if body.ration_kits is not None else f["ration_kits"]
    status = body.status if body.status else f["status"]
    await execute("UPDATE food_distribution SET meals_distributed=?,water_liters=?,ration_kits=?,status=?,last_updated=datetime('now','localtime') WHERE id=?",
        (meals,water,kits,status,fid))
    return {"id":fid,"updated":True}

# ══ RESCUED ══
@app.get("/api/rescued")
async def list_rescued():
    return await fetchall("SELECT * FROM rescued_people ORDER BY id DESC")

@app.post("/api/rescued", status_code=201)
async def add_rescued(p: RescuedPerson):
    rid = await execute("INSERT INTO rescued_people (name,age,gender,rescue_location,rescued_by,current_location,medical_condition,family_contact,notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (p.name,p.age,p.gender,p.rescue_location,p.rescued_by,p.current_location,p.medical_condition,p.family_contact,p.notes))
    return {"id":rid,"message":f"{p.name} registered"}

@app.patch("/api/rescued/{rid}")
async def update_rescued(rid: int, body: RescuedUpdate):
    r = await fetchone("SELECT * FROM rescued_people WHERE id=?", (rid,))
    if not r: raise HTTPException(404,"Not found")
    loc = body.current_location if body.current_location is not None else r["current_location"]
    med = body.medical_condition if body.medical_condition is not None else r["medical_condition"]
    fam = body.family_contact if body.family_contact is not None else r["family_contact"]
    notes = body.notes if body.notes is not None else r["notes"]
    await execute("UPDATE rescued_people SET current_location=?,medical_condition=?,family_contact=?,notes=? WHERE id=?",
        (loc,med,fam,notes,rid))
    return {"id":rid,"updated":True}

@app.delete("/api/rescued/{rid}")
async def delete_rescued(rid: int):
    await execute("DELETE FROM rescued_people WHERE id=?", (rid,))
    return {"deleted":rid}

# ══ STATS ══
@app.get("/api/stats")
async def stats():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        s = await (await db.execute("SELECT COUNT(*) t, SUM(CASE WHEN status='Resolved' THEN 1 ELSE 0 END) r FROM sos_requests")).fetchone()
        v = await (await db.execute("SELECT COUNT(*) t FROM volunteers")).fetchone()
        h = await (await db.execute("SELECT COUNT(*) t, SUM(beds_available) b, SUM(icu_available) i FROM hospitals")).fetchone()
        res = await (await db.execute("SELECT COUNT(*) t FROM rescued_people")).fetchone()
        food = await (await db.execute("SELECT SUM(meals_distributed) m FROM food_distribution")).fetchone()
        pol = await (await db.execute("SELECT SUM(officers_deployed) o, SUM(vehicles_available) v FROM police_depts")).fetchone()
    return {
        "sos_total": s["t"] or 0, "sos_resolved": s["r"] or 0,
        "volunteers": v["t"] or 0,
        "hospital_beds_available": h["b"] or 0, "icu_available": h["i"] or 0,
        "rescued_total": res["t"] or 0,
        "meals_distributed": food["m"] or 0,
        "officers_deployed": pol["o"] or 0, "police_vehicles": pol["v"] or 0,
    }

# ══ FRONTEND ══
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message":"RescueConnect V2 API","docs":"/docs"}
