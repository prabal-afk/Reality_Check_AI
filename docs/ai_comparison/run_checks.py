import sqlite3, sys, logging
logging.disable(logging.CRITICAL)
from flask import Flask, request, jsonify
checks=[("valid claim -> 201",{"claim_text":"The Earth is flat."},201),("missing field -> 400",{"x":1},400),
 ("spaces only -> 400",{"claim_text":"      "},400),("9 chars -> 400",{"claim_text":"123456789"},400),
 ("501 chars -> 400",{"claim_text":"a"*501},400),("number -> 400",{"claim_text":12345},400)]
for path in sys.argv[1:]:
    src="\n".join(l for l in open(path).read().split("\n") if not l.startswith(("from flask","from db")))  # imports supplied by harness
    app=Flask(__name__); conn=sqlite3.connect(":memory:",check_same_thread=False)
    conn.execute("CREATE TABLE claims(id INTEGER PRIMARY KEY AUTOINCREMENT, claim_text TEXT NOT NULL, verdict TEXT)")
    exec(src,{"app":app,"request":request,"jsonify":jsonify,"get_db":lambda:conn})
    app.config["PROPAGATE_EXCEPTIONS"]=False; c=app.test_client(); print("==",path)
    for name,body,exp in checks:
        r=c.post("/api/claims",json=body)
        print(" PASS" if r.status_code==exp else " FAIL",name,":",r.status_code,r.get_data(as_text=True).strip())
    r=c.post("/api/claims",json={"claim_text":"Another valid claim text"}); print("  success body:",r.get_json(),"| rows:",conn.execute("select count(*) from claims").fetchone()[0])
    r=c.post("/api/claims",json=[1,2,3]); print(" ", "PASS" if r.status_code==400 else "FAIL", "JSON list body [1,2,3] -> 400 :", r.status_code)
    print("  lines in function:",len([l for l in src.strip().split("\n") if l.strip()]))
