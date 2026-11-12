"""Get By's single-operator, loopback-only judging build."""
import base64, contextlib, datetime, io, json, mimetypes, os, re, secrets, sqlite3, subprocess, sys
import threading, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from discovery import AGENTS, CATALOG, scout
from public_work import public_work
import paypal

ROOT=Path(__file__).resolve().parent
MODE=os.getenv("GETBY_MODE","practice")
if MODE not in ("practice","sandbox"):raise RuntimeError("GETBY_MODE must be practice or sandbox")
RUNTIME=Path(os.getenv("GETBY_DATA",ROOT/".runtime"))/MODE
PORT=int(os.getenv("PORT","8765"))
TOKEN=secrets.token_urlsafe(24)
LOCK=threading.RLock()
JOBS={x["id"]:x for x in CATALOG}
PROMPTS=["오늘 날씨가 어떤가요?","다음 정류장에서 내려 주세요.","내일 아침에 다시 전화할게요."]
class Problem(Exception): pass

@contextlib.contextmanager
def db():
    conn=sqlite3.connect(RUNTIME/"getby.sqlite",timeout=12)
    conn.row_factory=sqlite3.Row
    try:
        with conn:yield conn
    finally:conn.close()

def init():
    RUNTIME.mkdir(parents=True,exist_ok=True)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS bills(role TEXT PRIMARY KEY, issuer TEXT, cents INTEGER, due TEXT, state TEXT DEFAULT 'open', pkey TEXT, ord TEXT, link TEXT, receipt TEXT);
        CREATE TABLE IF NOT EXISTS matches(agent TEXT PRIMARY KEY, result TEXT);
        CREATE TABLE IF NOT EXISTS work(id TEXT PRIMARY KEY,state TEXT NOT NULL,evidence TEXT,media BLOB,mime TEXT,pkey TEXT UNIQUE,batch TEXT,note TEXT);
        CREATE TABLE IF NOT EXISTS ledger(ref TEXT PRIMARY KEY,source TEXT UNIQUE,label TEXT NOT NULL,cents INTEGER NOT NULL,ts TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        c.execute("INSERT OR IGNORE INTO ledger(ref,source,label,cents) VALUES('opening','opening','Opening demo allocation',5000)")
        c.execute("INSERT OR IGNORE INTO work(id,state,evidence,pkey) VALUES('royalty','listed',?,?)",
                  (json.dumps({"caption":"Last month's sample still-life listing","source":"Seeded test listing; awaiting a purchase"}),uuid.uuid4().hex))

def state():
    with db() as c:
        bills=[dict(v) for v in c.execute("SELECT role,issuer,cents,due,state,receipt,link FROM bills ORDER BY role")]
        ledger=[dict(v) for v in c.execute("SELECT * FROM ledger ORDER BY rowid")]
        matches=[json.loads(v[0]) for v in c.execute("SELECT result FROM matches ORDER BY rowid")]
        work={v["id"]:dict(v) for v in c.execute("SELECT id,state,evidence,mime,batch,note FROM work")}
    total=sum(b["cents"] for b in bills);paid=sum(b["cents"] for b in bills if b["state"]=="paid")
    balance=sum(e["cents"] for e in ledger)
    return dict(mode=MODE,payout_ready=paypal.ready(),bills=bills,ledger=ledger,matches=matches,work=work,
                total=total,paid=paid,balance=balance,gap=max(0,total-paid-balance),
                earned=sum(e["cents"] for e in ledger if e["source"]!="opening" and e["cents"]>0),prompts=PROMPTS)

def integer(v,lo,hi):
    if type(v)!=int or not lo<=v<=hi:raise Problem("Please check the amount or time.")
    return v

def unpack(encoded):
    try:blob=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError):raise Problem("Could not read this attachment.")
    if not 1<=len(blob)<=5_000_000:raise Problem("Choose a file smaller than 5 MB.")
    return blob

def read_image(blob):
    try:
        with Image.open(io.BytesIO(blob)) as im:
            if im.format not in ("JPEG","PNG","WEBP") or im.width*im.height>16_000_000:raise Problem("Use a JPG, PNG or WebP up to 16 megapixels.")
            return ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):raise Problem("Could not read this image.")

def scan(p):
    im=read_image(unpack(p.get("data")));im.thumbnail((2200,2200))
    raw=io.BytesIO();im.save(raw,"PNG")
    try:
        o=subprocess.run(["tesseract","stdin","stdout","--psm","6"],input=raw.getvalue(),capture_output=True,timeout=15,check=True)
    except (OSError,subprocess.SubprocessError):raise Problem("OCR is unavailable. Enter the bill details manually.")
    lines=o.stdout.decode("utf8",errors="replace").splitlines()
    lines=[x.strip() for x in lines if x.strip()]
    money=None
    for line in sorted(lines,key=lambda l:0 if re.search('amount due|total due|balance due',l,re.I) else 1):
        m=re.search(r'\$\s*([0-9,]+)\.(\d\d)\b',line)
        if m:money=int(m[1].replace(",",""))*100+int(m[2]);break
    due=re.search(r'\b20\d\d-\d\d-\d\d\b'," ".join(lines))
    return {"issuer":lines[0][:80] if lines else "", "cents":money,"due":due[0] if due else "",
            "role":"mobile" if re.search("mobile|telecom|phone"," ".join(lines),re.I) else "electricity","text":"\n".join(lines)[:2000]}

def save_bill(p):
    if p.get("role") not in ("electricity","mobile"):raise Problem("Select a bill type.")
    name=str(p.get("issuer","")).strip()[:90];amount=integer(p.get("cents"),1,1000000)
    try:datetime.date.fromisoformat(p.get("due",""))
    except (TypeError,ValueError):raise Problem("Enter a valid due date.")
    if not name:raise Problem("Enter a biller name.")
    with LOCK,db() as c:
        old=c.execute("SELECT state FROM bills WHERE role=?",(p["role"],)).fetchone()
        if old and old[0]!="open":raise Problem("This bill already has a payment in progress.")
        c.execute("""INSERT INTO bills(role,issuer,cents,due,pkey) VALUES(?,?,?,?,?) ON CONFLICT(role) DO UPDATE SET
                  issuer=excluded.issuer,cents=excluded.cents,due=excluded.due""",(p["role"],name,amount,p["due"],uuid.uuid4().hex))
    return state()

def discover(p):
    agent=p.get("agent");lang=p.get("language");minutes=integer(p.get("minutes"),3,60)
    if agent not in AGENTS or lang not in ("ko","en"):raise Problem("Unknown scout or language.")
    with db() as c:
        due = c.execute("SELECT MIN(due) FROM bills WHERE state!='paid'").fetchone()[0]
    result=scout(agent,dict(language=lang,minutes=minutes,photos=p.get("photos") is True,due=due))
    with db() as c:c.execute("INSERT OR REPLACE INTO matches VALUES(?,?)",(agent,json.dumps(result)))
    return result

def submit(p):
    job=p.get("id");media=None;mime=None;ev={}
    if job not in ("voice","review","receipt","photo"):raise Problem("Unknown executable brief.")
    if not any(j["id"]==job for m in state()["matches"] for j in m["jobs"]):raise Problem("Find this opportunity first.")
    if job=="voice":
        if p.get("consent") is not True:raise Problem("Confirm the recording permission.")
        media=unpack(p.get("data"));mime=p.get("mime","").split(";")[0]
        valid=(mime in ("audio/wav","audio/x-wav") and media[:4]==b"RIFF" and media[8:12]==b"WAVE") or (mime in ("audio/webm","video/webm") and media[:4]==b"\x1aE\xdf\xa3") or (mime in ("audio/mp4","video/mp4") and media[4:8]==b"ftyp") or (mime=="audio/ogg" and media[:4]==b"OggS")
        if not valid or len(media)<512:raise Problem("Use a playable WAV, WebM, M4A or Ogg recording.")
        ev={"permission":"Local buyer evaluation","bytes":len(media)}
    elif job=="review":
        reason=str(p.get("reason","")).strip()
        if p.get("choice") not in ("A","B") or len(reason)<5:raise Problem("Choose an answer and explain your choice.")
        ev={"choice":p["choice"],"reason":reason[:500]}
    elif job=="receipt":
        ev={"total_cents":integer(p.get("total_cents"),1,100000)}
    else:
        if p.get("consent") is not True or not str(p.get("caption","")).strip():raise Problem("Add a caption and confirm your rights.")
        im=read_image(unpack(p.get("data")));im.thumbnail((1000,1000));b=io.BytesIO();im.save(b,"JPEG");media=b.getvalue();mime="image/jpeg"
        ev={"caption":str(p["caption"])[:300],"permission":"Test catalog listing"}
    with LOCK,db() as c:
        old=c.execute("SELECT state FROM work WHERE id=?",(job,)).fetchone()
        if old and old[0]!="revise":raise Problem("This submission is already on file.")
        c.execute("INSERT OR REPLACE INTO work(id,state,evidence,media,mime,pkey) VALUES(?,?,?,?,?,?)",
                  (job,"listed" if job=="photo" else "submitted",json.dumps(ev),media,mime,uuid.uuid4().hex))
    return state()

def reward(job):return 400 if job in ("photo","royalty") else JOBS[job]["reward"]

def review(p):
    job=p.get("id")
    with LOCK,db() as c:
        row=c.execute("SELECT * FROM work WHERE id=?",(job,)).fetchone()
        if not row or row["state"] not in ("submitted","listed"):raise Problem("Choose a submitted task or a listed photo.")
        if p.get("decision")=="revise":
            if row["state"]=="listed":raise Problem("Only submitted work can be returned for edits.")
            c.execute("UPDATE work SET state='revise',note=? WHERE id=?",(str(p.get("note") or "Please check your submission.")[:250],job))
        elif p.get("decision")=="approve":
            if job=="receipt" and json.loads(row["evidence"])["total_cents"]!=1320:raise Problem("The receipt totals $13.20. Request a correction.")
            c.execute("UPDATE work SET state='approved',note=NULL WHERE id=?",(job,))
        else:raise Problem("Unknown decision.")
    return state()

def settle(job):
    with LOCK:
        with db() as c:
            row=c.execute("SELECT * FROM work WHERE id=?",(job,)).fetchone()
            if not row or row["state"] not in ("approved","pending","received"):raise Problem("The buyer must approve this work first.")
            if row["state"]=="received":return state()
            cents=reward(job);key=row["pkey"];batch=row["batch"]
        if MODE=="sandbox":
            if not paypal.ready():raise Problem("Sandbox payout setup is incomplete. No payout was sent.")
            if not batch:
                with db() as c:c.execute("UPDATE work SET state='pending' WHERE id=?",(job,))
                batch=paypal.create_payout(key,cents)
                with db() as c:c.execute("UPDATE work SET batch=?,state='pending' WHERE id=?",(batch,job))
            status,ref=paypal.payout_status(batch,key,cents)
        else:status,ref="SUCCESS","practice-"+key
        with db() as c:
            if status=="SUCCESS" and ref:
                label="October photo royalty" if job=="royalty" else JOBS[job]["title"]
                c.execute("INSERT OR IGNORE INTO ledger(ref,source,label,cents) VALUES(?,?,?,?)",(ref,"work/"+job,label,cents))
                hit=c.execute("SELECT ref,cents FROM ledger WHERE source=?",("work/"+job,)).fetchone()
                if not hit or hit["ref"]!=ref or hit["cents"]!=cents:raise Problem("Payment reference mismatch; review the account activity.")
                c.execute("UPDATE work SET state='received',note=NULL WHERE id=?",(job,))
            else:
                terminal=status in ("DENIED","FAILED","BLOCKED","RETURNED","REFUNDED","REVERSED")
                c.execute("UPDATE work SET state=?,note=? WHERE id=?",("failed" if terminal else "pending",status,job))
    return state()

def pay_bill(role):
    if role not in ("electricity","mobile"):raise Problem("Unknown bill type.")
    with LOCK,db() as c:
        row=c.execute("SELECT * FROM bills WHERE role=?",(role,)).fetchone()
        if not row:raise Problem("Add this bill first.")
        if row["state"]=="paid":return {"state":"paid"}
        balance=c.execute("SELECT SUM(cents) FROM ledger").fetchone()[0] or 0
        reserved=c.execute("SELECT COALESCE(SUM(cents),0) FROM bills WHERE state IN ('approval','creating') AND role<>?",(role,)).fetchone()[0]
        if balance-reserved<row["cents"]:raise Problem("There are not enough available funds for this payment.")
        if MODE=="sandbox":
            if not paypal.ready(role):raise Problem("This test biller is not configured. Funds are ready; no payment was sent.")
            if not row["ord"]:
                c.execute("UPDATE bills SET state='creating' WHERE role=?",(role,))
                c.commit()
                order,link=paypal.bill_order(role,row["pkey"],row["cents"],"http://localhost:"+str(PORT))
                c.execute("UPDATE bills SET state='approval',ord=?,link=? WHERE role=?",(order,link,role))
                return {"state":"approval","link":link}
            try:
                ref=paypal.capture_bill(role,row["ord"],row["pkey"],row["cents"])
            except paypal.ClosedOrder:
                c.execute("UPDATE bills SET state='open',ord=NULL,link=NULL,pkey=? WHERE role=?",(uuid.uuid4().hex,role))
                return {"state":"open"}
            if not ref:return {"state":"approval","link":row["link"]}
        else:ref="practice-bill-"+row["pkey"]
        c.execute("INSERT INTO ledger(ref,source,label,cents) VALUES(?,?,?,?)",(ref,"bill/"+role,row["issuer"],-row["cents"]))
        c.execute("UPDATE bills SET state='paid',receipt=?,link=NULL WHERE role=?",(ref,role))
        return {"state":"paid"}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def out(self,status,b,mime):
        self.send_response(status);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(b)))
        self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.send_header("X-Frame-Options","DENY");self.end_headers();self.wfile.write(b)
    def reply(self,v,code=200):self.out(code,json.dumps(v,ensure_ascii=False).encode(),"application/json; charset=utf-8")
    def allowed(self):return self.headers.get("Host","") in (f"localhost:{PORT}",f"127.0.0.1:{PORT}")
    def do_GET(self):
        if not self.allowed():return self.reply({"error":"Invalid host."},403)
        path=urllib.parse.urlsplit(self.path).path
        if path=="/api/state":return self.reply(dict(state(),token=TOKEN))
        if path.startswith("/api/media/"):
            with db() as c:r=c.execute("SELECT media,mime FROM work WHERE id=?",(path.split("/")[-1],)).fetchone()
            if r and r["media"]:return self.out(200,r["media"],r["mime"])
            return self.reply({"error":"No media."},404)
        name="index.html" if path=="/" else path.lstrip("/")
        if name not in ("index.html","style.css","app.js","samples/electricity.png","samples/mobile.png","samples/photo.jpg","samples/voice.wav"):
            return self.reply({"error":"Not found."},404)
        f=ROOT/"web"/name
        if not f.is_file():return self.reply({"error":"Missing asset."},404)
        self.out(200,f.read_bytes(),mimetypes.guess_type(str(f))[0] or "application/octet-stream")
    def do_POST(self):
        if not self.allowed() or self.headers.get("X-GetBy-Session")!=TOKEN:return self.reply({"error":"Reload the app to reconnect."},403)
        try:
            n=int(self.headers.get("Content-Length","0"))
            if not 1<=n<=7_000_000:raise Problem("Request size is outside the limit.")
            p=json.loads(self.rfile.read(n))
            if not isinstance(p,dict):raise Problem("Malformed request.")
            actions={"/api/public-work":public_work,"/api/scan":scan,"/api/bills":save_bill,"/api/scout":discover,"/api/submit":submit,"/api/review":review,
                     "/api/settle":lambda p:settle(p.get("id")),"/api/pay":lambda p:pay_bill(p.get("role"))}
            if self.path not in actions:return self.reply({"error":"Unknown action."},404)
            self.reply(actions[self.path](p))
        except (Problem,paypal.PayPalError,ValueError,KeyError,TypeError) as e:self.reply({"error":str(e)},400)
        except (ConnectionResetError,BrokenPipeError):pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.reply({"error":"Unexpected server error. Check the local terminal."},500)
if __name__=="__main__":
    init()
    print(f"Get By · {MODE} · http://localhost:{PORT}",flush=True)
    ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
