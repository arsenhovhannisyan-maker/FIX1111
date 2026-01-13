import quickfix as fix
import quickfix44 as fix44
from datetime import datetime
from threading import Timer
import os
from dotenv import load_dotenv

load_dotenv()

class OrderSession(fix.Application):
    def __init__(self):
        super().__init__()
        self.session_id = None
        self.logon_sent = False
        self.trading_session_open = False
        self.order_store = {}
        self.execution_reports = []
        self.last_clordid = 1000

        self.fix_password = os.getenv('FIX_PASSWORD_OM')

        if not self.fix_password:
            print("[ERROR] FIX_PASSWORD_OM not found in .env file!")
            print("[ERROR] Add to .env: FIX_PASSWORD_OM=y3pWsv8a")
            exit(1)

    def onCreate(self, sessionID):
        self.session_id = sessionID
        print(f"[OM] Session created: {sessionID}")

    def onLogon(self, sessionID):
        print("[OM] Logon successful")
        self.logon_sent = True

    def onLogout(self, sessionID):
        print("[OM] Logout")
        self.logon_sent = False
        self.trading_session_open = False
        for cl_ord_id, order in self.order_store.items():
            if order['status'] in ['PENDING', 'PENDING_CANCEL']:
                self.order_store[cl_ord_id]['status'] = 'LOGGED_OUT'
                self.order_store[cl_ord_id]['last_update'] = datetime.now().isoformat()

    def toAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        if msg_type_val == fix.MsgType_Logon:
            print("[OM] Preparing Logon message")
            message.setField(fix.EncryptMethod(0))
            message.setField(fix.HeartBtInt(30))
            message.setField(fix.Password(self.fix_password))

            message.setField(fix.StringField(336, "Trade Data"))

    def fromAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[OM] Admin recv: {msg_type_val}")

        try:
            if msg_type_val == "5":
                text = fix.Text()
                if message.isSetField(text):
                    message.getField(text)
                    print(f"[OM] Logout reason: {text.getValue()}")
                else:
                    print("[OM] Logout without reason")
            elif msg_type_val == "3":
                self.process_session_reject(message)
            elif msg_type_val == "0":
                pass
            elif msg_type_val == "A":
                pass
        except Exception as e:
            print(f"[ERROR] Admin message {msg_type_val}: {e}")

    def fromApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        print(f"[OM] App recv: {msg_type_val}")

        try:
            if msg_type_val == "8":
                self.process_execution_report(message)
            elif msg_type_val == "9":
                self.process_order_cancel_reject(message)
            elif msg_type_val == "3":
                self.process_business_reject(message)
            elif msg_type_val == "h":
                self.process_trading_session_status(message)
            elif msg_type_val == "4":
                self.process_sequence_reset(message)
            elif msg_type_val == "j":
                self.process_business_message_reject(message)
            elif msg_type_val == "2":
                self.process_resend_request(message)
            elif msg_type_val == "1":
                self.process_test_request(message)
            else:
                print(f"[OM] Unhandled message type: {msg_type_val}")
                self.print_message_details(message)

        except Exception as e:
            print(f"[ERROR] Processing message {msg_type_val}: {e}")
            import traceback
            traceback.print_exc()

    def process_trading_session_status(self, message):
        try:
            trading_session_id = fix.StringField(336)
            trad_sess_status = fix.CharField(340)

            if not message.isSetField(trading_session_id):
                print("[OM] TradingSessionID not found in message")
                return

            if not message.isSetField(trad_sess_status):
                print("[OM] TradingSessionStatus not found in message")
                return

            message.getField(trading_session_id)
            message.getField(trad_sess_status)

            session_type = trading_session_id.getValue()
            status_code = trad_sess_status.getValue()

            status_map = {
                "1": "Halted",
                "2": "Open",
                "3": "Closed",
                "4": "Pre-Open",
                "5": "Pre-Close"
            }

            status_text = status_map.get(status_code, f"Unknown ({status_code})")

            print(f"[OM] TradingSessionStatus: {session_type} - {status_text}")

            if session_type == "Trade Data":
                if status_code == "2":
                    self.trading_session_open = True
                    print("[OM] ✓ Trade Data session is OPEN - ready for trading")
                else:
                    self.trading_session_open = False
                    print(f"[OM] ✗ Order Entry session NOT available: {status_text}")
            else:
                print(f"[OM] Warning: Unexpected TradingSessionID: {session_type}")

        except Exception as e:
            print(f"[ERROR] Processing TradingSessionStatus: {e}")

    def process_sequence_reset(self, message):
        try:
            gap_fill_flag = fix.GapFillFlag()
            new_seq_no = fix.NewSeqNo()

            if message.isSetField(gap_fill_flag):
                message.getField(gap_fill_flag)
                gap_fill = gap_fill_flag.getValue()
            else:
                gap_fill = 'N'

            if message.isSetField(new_seq_no):
                message.getField(new_seq_no)
                seq_no = new_seq_no.getValue()
                print(f"[OM] SequenceReset: GapFill={gap_fill}, NewSeqNo={seq_no}")

        except Exception as e:
            print(f"[ERROR] Processing SequenceReset: {e}")

    def process_execution_report(self, message):
        try:
            cl_ord_id = fix.ClOrdID()
            ord_status = fix.OrdStatus()
            exec_type = fix.ExecType()
            symbol = fix.Symbol()
            side = fix.Side()

            fields_to_get = [cl_ord_id, ord_status, exec_type, symbol, side]
            for field in fields_to_get:
                if message.isSetField(field):
                    message.getField(field)
                else:
                    print(f"[OM] Warning: Missing field {field} in ExecutionReport")

            order_qty = fix.OrderQty()
            cum_qty = fix.CumQty()
            leaves_qty = fix.LeavesQty()
            avg_px = fix.AvgPx()
            last_px = fix.LastPx()
            last_qty = fix.LastQty()
            order_id = fix.OrderID()
            exec_id = fix.ExecID()
            text_field = fix.Text()

            status_map = {
                "0": "New", "1": "Partially filled", "2": "Filled", "3": "Done for day",
                "4": "Canceled", "5": "Replaced", "6": "Pending Cancel", "7": "Stopped",
                "8": "Rejected", "9": "Suspended", "A": "Pending New", "B": "Calculated",
                "C": "Expired", "D": "Accepted for bidding", "E": "Pending Replace"
            }

            exec_type_map = {
                "0": "New", "1": "Partial fill", "2": "Fill", "3": "Done for day",
                "4": "Canceled", "5": "Replace", "6": "Pending Cancel", "7": "Stopped",
                "8": "Rejected", "9": "Suspended", "A": "Pending New", "B": "Calculated",
                "C": "Expired", "D": "Restated", "E": "Pending Replace", "F": "Trade",
                "G": "Trade Correct", "H": "Trade Cancel", "I": "Order Status"
            }

            side_map = {"1": "Buy", "2": "Sell", "G": "Borrow", "F": "Lend"}

            cl_ord_id_val = self.get_field_value(message, cl_ord_id, "N/A")
            symbol_val = self.get_field_value(message, symbol, "N/A")
            side_val = self.get_field_value(message, side, "N/A")
            status_val = self.get_field_value(message, ord_status, "N/A")
            exec_type_val = self.get_field_value(message, exec_type, "N/A")

            order_qty_val = self.get_float_field(message, order_qty, "OrderQty")
            cum_qty_val = self.get_float_field(message, cum_qty, "CumQty")
            leaves_qty_val = self.get_float_field(message, leaves_qty, "LeavesQty")
            avg_px_val = self.get_float_field(message, avg_px, "AvgPx")
            last_px_val = self.get_float_field(message, last_px, "LastPx")
            last_qty_val = self.get_float_field(message, last_qty, "LastQty")

            order_id_val = order_id.getValue() if order_id.isSet() else "N/A"
            exec_id_val = exec_id.getValue() if exec_id.isSet() else "N/A"
            text_val = text_field.getValue() if text_field.isSet() else ""

            status_text = status_map.get(status_val, status_val)
            exec_type_text = exec_type_map.get(exec_type_val, exec_type_val)
            side_text = side_map.get(side_val, side_val)

            print(f"[OM] ExecutionReport:")
            print(f"  ClOrdID: {cl_ord_id_val}")
            print(f"  OrderID: {order_id_val}")
            print(f"  ExecID: {exec_id_val}")
            print(f"  Symbol: {symbol_val}")
            print(f"  Side: {side_text}")
            print(f"  Status: {status_text} ({status_val})")
            print(f"  ExecType: {exec_type_text} ({exec_type_val})")
            print(f"  OrderQty: {order_qty_val}")
            print(f"  CumQty: {cum_qty_val}")
            print(f"  LeavesQty: {leaves_qty_val}")
            print(f"  AvgPx: {avg_px_val:.5f}")
            print(f"  LastPx: {last_px_val:.5f}")
            print(f"  LastQty: {last_qty_val}")
            print(f"  Text: {text_val}")

            if cl_ord_id_val != "N/A" and cl_ord_id_val in self.order_store:
                self.order_store[cl_ord_id_val].update({
                    'status': status_val,
                    'order_id': order_id_val,
                    'exec_id': exec_id_val,
                    'cum_qty': cum_qty_val,
                    'leaves_qty': leaves_qty_val,
                    'avg_px': avg_px_val,
                    'last_update': datetime.now().isoformat(),
                    'text': text_val
                })

                if status_val in ["2", "4", "8"]:
                    print(f"[OM] Order {cl_ord_id_val} completed with status: {status_text}")

            self.execution_reports.append({
                'cl_ord_id': cl_ord_id_val,
                'order_id': order_id_val,
                'exec_id': exec_id_val,
                'timestamp': datetime.now().isoformat(),
                'status': status_val,
                'exec_type': exec_type_val,
                'symbol': symbol_val,
                'side': side_val,
                'order_qty': order_qty_val,
                'cum_qty': cum_qty_val,
                'leaves_qty': leaves_qty_val,
                'avg_px': avg_px_val,
                'last_px': last_px_val,
                'last_qty': last_qty_val,
                'text': text_val
            })

        except Exception as e:
            print(f"[ERROR] Processing ExecutionReport: {e}")
            import traceback
            traceback.print_exc()

    def process_order_cancel_reject(self, message):
        try:
            cl_ord_id = fix.ClOrdID()
            orig_cl_ord_id = fix.OrigClOrdID()
            ord_status = fix.OrdStatus()
            cxl_rej_reason = fix.CxlRejReason()
            text = fix.Text()
            cxl_rej_response_to = fix.CxlRejResponseTo()

            reason_map = {
                "0": "Too late to cancel",
                "1": "Unknown order",
                "2": "Broker/Exchange option",
                "3": "Order already in Pending Cancel or Pending Replace status",
                "4": "Unable to process Order Mass Cancel Request",
                "5": "OrigOrdModTime did not match last TransactTime of order",
                "6": "Duplicate ClOrdID received",
                "99": "Other"
            }

            values = {}
            fields = [
                (cl_ord_id, "ClOrdID"),
                (orig_cl_ord_id, "OrigClOrdID"),
                (ord_status, "OrdStatus"),
                (cxl_rej_reason, "CxlRejReason"),
                (text, "Text"),
                (cxl_rej_response_to, "CxlRejResponseTo")
            ]

            for field, name in fields:
                if message.isSetField(field):
                    message.getField(field)
                    values[name] = field.getValue()
                else:
                    values[name] = "N/A"

            reason_code = values["CxlRejReason"]
            reason_text = reason_map.get(reason_code, f"Unknown ({reason_code})")

            response_to_map = {"1": "Order Cancel Request", "2": "Order Cancel Replace Request"}
            response_to_text = response_to_map.get(values["CxlRejResponseTo"], values["CxlRejResponseTo"])

            print(f"[OM] OrderCancelReject:")
            print(f"  ClOrdID: {values['ClOrdID']}")
            print(f"  OrigClOrdID: {values['OrigClOrdID']}")
            print(f"  Status: {values['OrdStatus']}")
            print(f"  ResponseTo: {response_to_text}")
            print(f"  Reason: {reason_text}")
            print(f"  Text: {values['Text']}")

            orig_id = values["OrigClOrdID"]
            if orig_id != "N/A" and orig_id in self.order_store:
                self.order_store[orig_id]['status'] = 'CANCEL_REJECTED'
                self.order_store[orig_id]['cancel_reject_reason'] = reason_text
                self.order_store[orig_id]['last_update'] = datetime.now().isoformat()

        except Exception as e:
            print(f"[ERROR] Processing OrderCancelReject: {e}")

    def process_business_reject(self, message):
        try:
            text = fix.Text()
            ref_seq_num = fix.RefSeqNum()
            ref_msg_type = fix.RefMsgType()
            business_reject_reason = fix.BusinessRejectReason()

            text_val = self.get_field_value(message, text, "No text")
            seq_val = self.get_field_value(message, ref_seq_num, "N/A")
            msg_type_val = self.get_field_value(message, ref_msg_type, "N/A")
            reason_val = self.get_field_value(message, business_reject_reason, "N/A")

            print(f"[OM] Business Reject:")
            print(f"  SeqNum: {seq_val}")
            print(f"  RefMsgType: {msg_type_val}")
            print(f"  Reason: {reason_val}")
            print(f"  Text: {text_val}")

        except Exception as e:
            print(f"[ERROR] Processing Business Reject: {e}")

    def process_session_reject(self, message):
        try:
            text = fix.Text()
            ref_seq_num = fix.RefSeqNum()
            ref_tag_id = fix.RefTagID()
            session_reject_reason = fix.SessionRejectReason()

            text_val = self.get_field_value(message, text, "No text")
            seq_val = self.get_field_value(message, ref_seq_num, "N/A")
            tag_val = self.get_field_value(message, ref_tag_id, "N/A")
            reason_val = self.get_field_value(message, session_reject_reason, "N/A")

            print(f"[OM] Session Reject:")
            print(f"  SeqNum: {seq_val}")
            print(f"  RefTagID: {tag_val}")
            print(f"  Reason: {reason_val}")
            print(f"  Text: {text_val}")

        except Exception as e:
            print(f"[ERROR] Processing Session Reject: {e}")

    def process_business_message_reject(self, message):
        try:
            text = fix.Text()
            ref_seq_num = fix.RefSeqNum()
            ref_msg_type = fix.RefMsgType()

            text_val = self.get_field_value(message, text, "No text")
            seq_val = self.get_field_value(message, ref_seq_num, "N/A")
            msg_type_val = self.get_field_value(message, ref_msg_type, "N/A")

            print(f"[OM] Business Message Reject:")
            print(f"  SeqNum: {seq_val}")
            print(f"  RefMsgType: {msg_type_val}")
            print(f"  Text: {text_val}")

        except Exception as e:
            print(f"[ERROR] Processing Business Message Reject: {e}")

    def process_resend_request(self, message):
        try:
            begin_seq_no = fix.BeginSeqNo()
            end_seq_no = fix.EndSeqNo()

            if message.isSetField(begin_seq_no):
                message.getField(begin_seq_no)
                begin_val = begin_seq_no.getValue()
            else:
                begin_val = "N/A"

            if message.isSetField(end_seq_no):
                message.getField(end_seq_no)
                end_val = end_seq_no.getValue()
            else:
                end_val = "N/A"

            print(f"[OM] ResendRequest: BeginSeqNo={begin_val}, EndSeqNo={end_val}")

        except Exception as e:
            print(f"[ERROR] Processing ResendRequest: {e}")

    def process_test_request(self, message):
        try:
            test_req_id = fix.TestReqID()
            if message.isSetField(test_req_id):
                message.getField(test_req_id)
                req_id = test_req_id.getValue()
                print(f"[OM] TestRequest received: TestReqID={req_id}")
        except Exception as e:
            print(f"[ERROR] Processing TestRequest: {e}")

    def toApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()
        print(f"[OM] Send: {msg_type_val}")

    def send_new_order_single(self, symbol, side, quantity, price=None, order_type="2", time_in_force="3"):
        try:
            if not self.session_id:
                print("[OM] Cannot send order - no session ID")
                return None

            if not self.trading_session_open:
                print("[OM] Cannot send order - trading session not open")
                print("[OM] Wait for TradingSessionStatus with status=Open")
                return None

            self.last_clordid += 1
            cl_ord_id = f"OM{self.last_clordid:06d}"

            msg = fix44.NewOrderSingle()

            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.HandlInst('1'))
            msg.setField(fix.Symbol(symbol))
            msg.setField(fix.Side(side))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            msg.setField(fix.OrderQty(quantity))
            msg.setField(fix.OrdType(order_type))
            msg.setField(fix.TimeInForce(time_in_force))

            msg.setField(fix.StringField(336, "Trade Data"))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            if order_type == "2" and price is not None:
                msg.setField(fix.Price(price))

            if "/" in symbol:
                try:
                    currency = symbol.split("/")[1]
                    msg.setField(fix.Currency(currency))
                except:
                    print(f"[WARN] Could not extract currency from {symbol}")

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Sent NewOrderSingle:")
            print(f"  ClOrdID: {cl_ord_id}")
            print(f"  Symbol: {symbol}")
            print(f"  Side: {'BUY' if side == '1' else 'SELL'}")
            print(f"  Quantity: {quantity}")
            print(f"  Price: {price if price else 'MARKET'}")
            print(f"  OrdType: {'LIMIT' if order_type == '2' else 'MARKET'}")
            print(f"  TimeInForce: {time_in_force} ({self.get_time_in_force_text(time_in_force)})")

            self.order_store[cl_ord_id] = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price if order_type == "2" else None,
                'order_type': order_type,
                'time_in_force': time_in_force,
                'timestamp': datetime.now().isoformat(),
                'status': 'PENDING',
                'cum_qty': 0.0,
                'leaves_qty': quantity,
                'avg_px': 0.0,
                'order_id': None,
                'exec_id': None
            }

            return cl_ord_id

        except Exception as e:
            print(f"[ERROR] Sending NewOrderSingle: {e}")
            import traceback
            traceback.print_exc()
            return None

    def send_order_cancel_request(self, orig_cl_ord_id, symbol=None, side=None):
        try:
            if not self.session_id or not self.trading_session_open:
                print("[OM] Cannot send cancel - not ready")
                return False

            if orig_cl_ord_id not in self.order_store:
                print(f"[OM] Order {orig_cl_ord_id} not found in store")
                return False

            order_info = self.order_store[orig_cl_ord_id]

            symbol = symbol or order_info.get('symbol', 'EUR/USD')
            side = side or order_info.get('side', '1')

            self.last_clordid += 1
            cl_ord_id = f"CXL{self.last_clordid:06d}"

            msg = fix44.OrderCancelRequest()
            msg.setField(fix.OrigClOrdID(orig_cl_ord_id))
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.Symbol(symbol))
            msg.setField(fix.Side(side))
            # msg.setField(fix.TransactTime(datetime.now()))

            msg.setField(fix.StringField(336, "Trade Data"))

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Sent OrderCancelRequest:")
            print(f"  ClOrdID: {cl_ord_id}")
            print(f"  OrigClOrdID: {orig_cl_ord_id}")
            print(f"  Symbol: {symbol}")
            print(f"  Side: {'BUY' if side == '1' else 'SELL'}")

            self.order_store[orig_cl_ord_id]['status'] = 'PENDING_CANCEL'
            self.order_store[orig_cl_ord_id]['last_update'] = datetime.now().isoformat()

            return True

        except Exception as e:
            print(f"[ERROR] Sending OrderCancelRequest: {e}")
            return False

    def send_order_status_request(self, cl_ord_id, symbol="*"):
        try:
            if not self.session_id or not self.trading_session_open:
                return False

            msg = fix44.OrderStatusRequest()
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.Symbol(symbol))
            msg.setField(fix.StringField(625, "1"))
            msg.setField(fix.StringField(336, "Trade Data"))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Sent OrderStatusRequest for {cl_ord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] Sending OrderStatusRequest: {e}")
            return False

    def get_float_field(self, message, field, field_name):
        try:
            if message.isSetField(field):
                message.getField(field)
                return float(field.getValue())
            return 0.0
        except:
            return 0.0

    def get_field_value(self, message, field, default):
        try:
            if message.isSetField(field):
                message.getField(field)
                return field.getValue()
            return default
        except:
            return default

    def get_time_in_force_text(self, tif):
        tif_map = {
            "0": "Day", "1": "GTC", "2": "At Opening", "3": "IOC",
            "4": "FOK", "5": "GTX", "6": "GTD"
        }
        return tif_map.get(tif, f"Unknown ({tif})")

    def print_message_details(self, message):
        try:
            print(f"[OM] Message details:")
            print(f"  Raw: {message.toString().replace(chr(1), '|')}")
        except:
            print(f"[OM] Could not print message details")

    def get_order_info(self, cl_ord_id):
        return self.order_store.get(cl_ord_id)

    def get_all_orders(self):
        return self.order_store

    def get_execution_history(self):
        return self.execution_reports

    def send_test_order(self):
        print("[OM] === STARTING TEST ORDER ===")

        if not self.trading_session_open:
            print("[OM] ERROR: Trading session not open")
            return

        print("[OM] Sending test order...")

        cl_ord_id = self.send_new_order_single(
            symbol="EUR/USD",
            side="1",
            quantity=1000,
            price=1.0800,
            order_type="2",
            time_in_force="3"
        )

        if cl_ord_id:
            print(f"[OM] ✓ Test order sent with ClOrdID: {cl_ord_id}")

            Timer(3.0, lambda: self.send_order_status_request(cl_ord_id)).start()

            Timer(5.0, lambda: self.send_order_cancel_request(cl_ord_id)).start()

            return cl_ord_id
        else:
            print("[OM] ✗ Failed to send test order")
            return None

    def _create_transact_time(self):
        transact_time = fix.TransactTime()
        transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
        return transact_time