import base64
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import paypal
import server

class FlowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for key,value in (("RUNTIME",Path(tmp.name)),("MODE","practice")):
            p=patch.object(server,key,value)
            p.start()
            self.addCleanup(p.stop)
        server.init()
        with server.db() as db:
            db.execute("INSERT INTO matches VALUES(?,?)",("test",json.dumps({"agent":"test","jobs":list(server.JOBS.values())})))
        self.bill("electricity",5000)
        self.bill("mobile",3000)

    def bill(self,role,amount):
        server.save_bill(dict(role=role,issuer=role,cents=amount,due="2026-11-20"))

    def approve(self,job):
        server.review({"id":job,"decision":"approve"})

    def test_full_cycle_and_repeat(self):
        voice=b"RIFF"+b"0000WAVE"+b"\x00"*1200
        server.submit({"id":"voice","consent":True,"data":base64.b64encode(voice).decode(),"mime":"audio/wav"})
        self.assertEqual(server.state()["gap"],3000)
        with self.assertRaises(server.Problem):server.settle("voice")
        self.approve("voice")
        self.assertEqual(server.state()["gap"],3000)
        with ThreadPoolExecutor(3) as pool:list(pool.map(server.settle,["voice"]*3))
        self.assertEqual(server.state()["gap"],1800)
        server.submit({"id":"review","choice":"A","reason":"A specifies the due date."})
        self.approve("review")
        server.settle("review")
        self.assertEqual(server.state()["gap"],800)
        server.submit({"id":"receipt","total_cents":1310})
        with self.assertRaises(server.Problem):self.approve("receipt")
        server.review({"id":"receipt","decision":"revise"})
        server.submit({"id":"receipt","total_cents":1320})
        self.approve("receipt")
        server.settle("receipt")
        self.approve("royalty")
        server.settle("royalty")
        self.assertEqual(server.state()["balance"],8400)
        server.pay_bill("electricity")
        self.assertEqual(server.state()["balance"],3400)
        with ThreadPoolExecutor(3) as pool:list(pool.map(server.pay_bill,["mobile"]*3))
        server.init()
        s=server.state()
        self.assertEqual((s["gap"],s["earned"],s["paid"],s["balance"],len(s["ledger"])),(0,3400,8000,400,7))

    def test_photo_waits_for_sale(self):
        blob=(server.ROOT/"web/samples/photo.jpg").read_bytes()
        s=server.submit({"id":"photo","caption":"Still life","consent":True,"data":base64.b64encode(blob).decode()})
        self.assertEqual(s["work"]["photo"]["state"],"listed")
        self.assertEqual(s["earned"],0)

    def test_ocr_samples(self):
        import shutil
        if not shutil.which("tesseract"):self.skipTest("Tesseract not installed")
        for role,cents in (("electricity",5000),("mobile",3000)):
            raw=(server.ROOT/"web/samples"/(role+".png")).read_bytes()
            out=server.scan({"data":base64.b64encode(raw).decode()})
            self.assertEqual((out["role"],out["cents"]),(role,cents))
            self.assertTrue(out["due"].startswith("2026-11-"))

    def test_sandbox_retry_uses_same_intent(self):
        self.approve("royalty")
        with patch.object(server,"MODE","sandbox"),patch.object(paypal,"ready",return_value=True),patch.object(paypal,"create_payout",side_effect=[paypal.PayPalError("timeout"),"BATCH"]) as send,patch.object(paypal,"payout_status",side_effect=[("UNCLAIMED",None),("SUCCESS","TX")]):
            with self.assertRaises(paypal.PayPalError):server.settle("royalty")
            self.assertEqual(server.state()["work"]["royalty"]["state"],"pending")
            server.settle("royalty")
            self.assertEqual(server.state()["earned"],0)
            self.assertEqual(server.settle("royalty")["earned"],400)
            self.assertEqual(send.call_args_list[0],send.call_args_list[1])

    def test_expired_order_releases_reservation_after_verified_void(self):
        with patch.object(server,"MODE","sandbox"),patch.object(paypal,"ready",return_value=True),patch.object(paypal,"bill_order",return_value=("ORDER","https://www.sandbox.paypal.com/test")),patch.object(paypal,"capture_bill",side_effect=paypal.ClosedOrder("void")):
            self.assertEqual(server.pay_bill("electricity")["state"],"approval")
            with self.assertRaises(server.Problem):server.pay_bill("mobile")
            self.assertEqual(server.pay_bill("electricity")["state"],"open")
            self.assertEqual(server.pay_bill("mobile")["state"],"approval")
            self.assertEqual(server.state()["balance"],5000)

    def test_duplicate_payout_links(self):
        for url,valid in [("https://api.sandbox.paypal.com/v1/payments/payouts/AB12",True),("https://other.example/v1/payments/payouts/WRONG",False)]:
            err=paypal.PayPalError("Duplicate",{"links":[{"href":url}]})
            with patch.dict(os.environ,{"PAYPAL_RECIPIENT_EMAIL":"test@example.invalid"}),patch.object(paypal,"call",side_effect=err):
                if valid:self.assertEqual(paypal.create_payout("k",1200),"AB12")
                else:
                    with self.assertRaises(paypal.PayPalError):paypal.create_payout("k",1200)

    def test_mismatched_order_never_captured(self):
        stub={"status":"APPROVED","purchase_units":[{"reference_id":"wrong"}]}
        with patch.object(paypal,"call",return_value=stub) as provider:
            with self.assertRaises(paypal.PayPalError):paypal.capture_bill("mobile","ORDER","right",3000)
            self.assertEqual(provider.call_count,1)

    def test_payout_identity(self):
        item={"payout_item":{"sender_item_id":"k","receiver":"someone@example.invalid","amount":{"currency":"USD","value":"12.00"}},"transaction_status":"SUCCESS","transaction_id":"T"}
        result={"batch_header":{"sender_batch_header":{"sender_batch_id":"k"}},"items":[item]}
        with patch.dict(os.environ,{"PAYPAL_RECIPIENT_EMAIL":"me@example.invalid"}),patch.object(paypal,"call",return_value=result):
            self.assertEqual(paypal.payout_status("B","k",1200),("PENDING",None))
            item["payout_item"]["receiver"]="me@example.invalid"
            self.assertEqual(paypal.payout_status("B","k",1200),("SUCCESS","T"))
