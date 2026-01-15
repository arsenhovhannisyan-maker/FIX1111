import quickfix as fix
import quickfix44 as fix44
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class ConfigurationError(Exception):
    pass
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
            raise ConfigurationError("Missing FIX password")

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

    def toAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)

        if msg_type.getValue() == fix.MsgType_Logon:
            message.setField(fix.EncryptMethod(0))
            message.setField(fix.HeartBtInt(30))
            message.setField(fix.Password(self.fix_password))
            message.setField(fix.StringField(336, "Trade Data"))

    def fromAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()
        print(f"[OM] Admin recv: {msg_type_val}")

        if msg_type_val == fix.MsgType_Reject:
            self.process_reject(message)

    def fromApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        try:
            if msg_type_val == "8":
                self.process_execution_report(message)
            elif msg_type_val == "9":
                self.process_order_cancel_reject(message)
            elif msg_type_val == "h":
                self.process_trading_session_status(message)
            elif msg_type_val == "j":
                self.process_business_message_reject(message)
        except Exception as e:
            print(f"[ERROR] Processing message {msg_type_val}: {e}")

    def process_trading_session_status(self, message):
        try:
            trading_session_id = fix.StringField(336)
            trad_sess_status = fix.CharField(340)

            if message.isSetField(trading_session_id) and message.isSetField(trad_sess_status):
                message.getField(trading_session_id)
                message.getField(trad_sess_status)

                session_type = trading_session_id.getValue()
                status_code = trad_sess_status.getValue()

                if session_type == "Trade Data" and status_code == "2":
                    self.trading_session_open = True
                    print("[OM] ✓ Trade Data session is OPEN - ready for trading")
        except Exception as e:
            print(f"[ERROR] Processing TradingSessionStatus: {e}")

    def process_execution_report(self, message):
        try:
            print(f"[OM] Processing ExecutionReport")

            def get_field(field_class, default=None):
                try:
                    field = field_class()
                    if message.isSetField(field):
                        message.getField(field)
                        return field.getValue()
                except Exception:
                    pass
                return default

            def get_float_field(field_class, default=0.0):
                try:
                    value = get_field(field_class)
                    if value is not None:
                        return float(value)
                except (ValueError, TypeError):
                    pass
                return default

            cl_ord_id_val = get_field(fix.ClOrdID, "N/A")
            ord_status_val = get_field(fix.OrdStatus, "N/A")
            exec_type_val = get_field(fix.ExecType, "N/A")
            symbol_val = get_field(fix.Symbol, "N/A")
            side_val = get_field(fix.Side, "N/A")
            order_id_val = get_field(fix.OrderID, "N/A")
            exec_id_val = get_field(fix.ExecID, "N/A")
            text_val = get_field(fix.Text, "")

            order_qty_val = get_float_field(fix.OrderQty)
            cum_qty_val = get_float_field(fix.CumQty)
            leaves_qty_val = get_float_field(fix.LeavesQty)
            avg_px_val = get_float_field(fix.AvgPx)
            last_px_val = get_float_field(fix.LastPx)
            last_qty_val = get_float_field(fix.LastQty)

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

            side_map = {"1": "Buy", "2": "Sell"}

            status_text = status_map.get(ord_status_val, ord_status_val)
            exec_type_text = exec_type_map.get(exec_type_val, exec_type_val)
            side_text = side_map.get(side_val, side_val)

            print(f"[OM] ════════════════════════════════════════════════")
            print(f"[OM] 📋 ExecutionReport Received")
            print(f"[OM] ────────────────────────────────────────────────")
            print(f"[OM]   ClOrdID:    {cl_ord_id_val}")
            print(f"[OM]   OrderID:    {order_id_val}")
            print(f"[OM]   ExecID:     {exec_id_val}")
            print(f"[OM]   Symbol:     {symbol_val}")
            print(f"[OM]   Side:       {side_text} ({side_val})")
            print(f"[OM]   Status:     {status_text} ({ord_status_val})")
            print(f"[OM]   ExecType:   {exec_type_text} ({exec_type_val})")
            print(f"[OM] ────────────────────────────────────────────────")
            print(f"[OM]   OrderQty:   {order_qty_val:,.0f}")
            print(f"[OM]   CumQty:     {cum_qty_val:,.0f}")
            print(f"[OM]   LeavesQty:  {leaves_qty_val:,.0f}")
            print(f"[OM]   AvgPx:      {avg_px_val:.5f}")
            print(f"[OM]   LastPx:     {last_px_val:.5f}")
            print(f"[OM]   LastQty:    {last_qty_val:,.0f}")
            print(f"[OM] ────────────────────────────────────────────────")
            print(f"[OM]   Text:       {text_val}")
            print(f"[OM] ════════════════════════════════════════════════")

            if cl_ord_id_val != "N/A" and cl_ord_id_val in self.order_store:
                self.order_store[cl_ord_id_val].update({
                    'status': ord_status_val,
                    'order_id': order_id_val,
                    'exec_id': exec_id_val,
                    'cum_qty': cum_qty_val,
                    'leaves_qty': leaves_qty_val,
                    'avg_px': avg_px_val,
                    'last_px': last_px_val,
                    'last_qty': last_qty_val,
                    'text': text_val,
                    'last_update': datetime.now().isoformat()
                })

                print(f"[OM] ✅ Order {cl_ord_id_val} updated in store")

                if ord_status_val in ["2", "4", "8"]:
                    print(f"[OM] 🏁 Order {cl_ord_id_val} completed: {status_text}")

            self.execution_reports.append({
                'cl_ord_id': cl_ord_id_val,
                'order_id': order_id_val,
                'exec_id': exec_id_val,
                'timestamp': datetime.now().isoformat(),
                'status': ord_status_val,
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
            print(f"[ERROR] ❌ Failed to process ExecutionReport: {e}")
            import traceback
            traceback.print_exc()

            try:
                print(f"[ERROR] Raw message: {message.toString().replace(chr(1), '|')}")
            except:
                print(f"[ERROR] Could not print raw message")

    def process_order_cancel_reject(self, message):
        try:
            cl_ord_id = fix.ClOrdID()
            orig_cl_ord_id = fix.OrigClOrdID()
            ord_status = fix.OrdStatus()
            cxl_rej_reason = fix.CxlRejReason()
            text = fix.Text()

            values = {}
            fields = [
                (cl_ord_id, "ClOrdID"),
                (orig_cl_ord_id, "OrigClOrdID"),
                (ord_status, "OrdStatus"),
                (cxl_rej_reason, "CxlRejReason"),
                (text, "Text")
            ]

            for field, name in fields:
                if message.isSetField(field):
                    message.getField(field)
                    values[name] = field.getValue()
                else:
                    values[name] = "N/A"

            print(f"[OM] OrderCancelReject:")
            print(f"  ClOrdID: {values['ClOrdID']}")
            print(f"  OrigClOrdID: {values['OrigClOrdID']}")
            print(f"  Status: {values['OrdStatus']}")
            print(f"  Reason: {values['CxlRejReason']}")
            print(f"  Text: {values['Text']}")

        except Exception as e:
            print(f"[ERROR] Processing OrderCancelReject: {e}")

    def process_business_message_reject(self, message):
        try:
            text = fix.Text()
            ref_msg_type = fix.RefMsgType()

            text_val = text.getValue() if text.isSet() else "No text"
            msg_type_val = ref_msg_type.getValue() if ref_msg_type.isSet() else "N/A"

            print(f"[OM] Business Message Reject:")
            print(f"  RefMsgType: {msg_type_val}")
            print(f"  Text: {text_val}")

        except Exception as e:
            print(f"[ERROR] Processing Business Message Reject: {e}")

    def toApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()
        print(f"[OM] Send: {msg_type_val}")


        if msg_type_val in ["D", "F", "H"]:
            try:
                fix_string = message.toString()
                readable = fix_string.replace(chr(1), '|')
                print(f"[FIX OUT] {readable}")
            except Exception as e:
                print(f"[ERROR] Formatting outbound message: {e}")

        if msg_type_val == "D":
            print(f"[OM] 📤 Sending NewOrderSingle")
        elif msg_type_val == "F":
            print(f"[OM] 📤 Sending OrderCancelRequest")
        elif msg_type_val == "H":
            print(f"[OM] 📤 Sending OrderStatusRequest")
        else:
            print(f"[OM] Send: {msg_type_val}")

    def send_new_order_single(self, symbol, side, quantity, price=None, order_type="2", time_in_force=None):
        try:
            if not self.session_id or not self.trading_session_open:
                print("[OM] Cannot send order - not ready")
                return None

            import threading
            self._clordid_lock = threading.Lock()
            with self._clordid_lock:
                self.last_clordid += 1

            import time
            timestamp = int(time.time() * 1000) % 1000000
            cl_ord_id = f"OM{self.last_clordid:04d}_{timestamp:06d}"

            msg = fix44.NewOrderSingle()
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.HandlInst('1'))
            msg.setField(fix.Symbol(symbol))
            msg.setField(fix.Side(side))
            msg.setField(fix.OrderQty(quantity))
            msg.setField(fix.OrdType(order_type))
            msg.setField(fix.StringField(336, "Trade Data"))

            if order_type == "1":
                msg.setField(fix.TimeInForce("3"))
            elif order_type == "2":
                msg.setField(fix.TimeInForce("1"))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            if order_type == "2":
                if price is not None:
                    msg.setField(fix.Price(price))
                else:
                    print(f"[ERROR] LIMIT order requires price")
                    return None

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Sent NewOrderSingle:")
            print(f"  ClOrdID: {cl_ord_id}")
            print(f"  Symbol: {symbol}")
            print(f"  Side: {'BUY' if side == '1' else 'SELL'}")
            print(f"  Quantity: {quantity}")
            print(f"  Price: {price if price else 'MARKET'}")

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
                'avg_px': 0.0
            }

            return cl_ord_id

        except Exception as e:
            print(f"[ERROR] Sending NewOrderSingle: {e}")
            return None

    def send_order_cancel_request(self, orig_cl_ord_id, symbol=None, side=None):
        try:
            if not self.session_id or not self.trading_session_open:
                print("[OM] Cannot send cancel - session not ready")
                return False

            if orig_cl_ord_id not in self.order_store:
                print(f"[OM] Order {orig_cl_ord_id} not found")
                return False

            order_info = self.order_store[orig_cl_ord_id]

            if 'order_id' not in order_info:
                print(f"[OM] ❌ Order {orig_cl_ord_id} has no OrderID! Cannot cancel.")
                print(f"[OM]    OrderInfo: {order_info}")
                return False

            current_status = order_info.get('status')
            if current_status in ['2', '4', '8']:
                print(f"[OM] Order {orig_cl_ord_id} already completed (status: {current_status})")
                return False

            import threading
            self._clordid_lock = threading.Lock()
            with self._clordid_lock:
                self.last_clordid += 1

            cl_ord_id = f"CXL{self.last_clordid:06d}"

            symbol = order_info.get('symbol')
            side = order_info.get('side')
            order_id = order_info['order_id']

            print(f"[OM] 🔧 Preparing OrderCancelRequest:")
            print(f"     OrigClOrdID: {orig_cl_ord_id}")
            print(f"     OrderID:     {order_id}")
            print(f"     Symbol:      {symbol}")
            print(f"     Side:        {side}")

            msg = fix44.OrderCancelRequest()
            msg.setField(fix.OrigClOrdID(orig_cl_ord_id))
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.OrderID(order_id))
            msg.setField(fix.Symbol(symbol))
            msg.setField(fix.Side(side))
            msg.setField(fix.StringField(336, "Trade Data"))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] ✅ Sent OrderCancelRequest:")
            print(f"  ClOrdID:    {cl_ord_id}")
            print(f"  OrigClOrdID: {orig_cl_ord_id}")
            print(f"  OrderID:    {order_id}")
            print(f"  Symbol:     {symbol}")
            print(f"  Side:       {'BUY' if side == '1' else 'SELL'}")

            self.order_store[orig_cl_ord_id]['status'] = 'PENDING_CANCEL'
            self.order_store[orig_cl_ord_id]['cancel_cl_ord_id'] = cl_ord_id
            self.order_store[orig_cl_ord_id]['cancel_request_time'] = datetime.now().isoformat()

            return True

        except Exception as e:
            print(f"[ERROR] ❌ Sending OrderCancelRequest: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_order_status_request(self, cl_ord_id):
        try:
            if not self.session_id or not self.trading_session_open:
                return False

            msg = fix44.OrderStatusRequest()
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.Symbol("*"))
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

    def get_order_info(self, cl_ord_id):
        return self.order_store.get(cl_ord_id)

    def get_all_orders(self):
        return self.order_store

    def get_execution_history(self):
        return self.execution_reports


    def process_reject(self, message):
        try:
            print(f"[OM] ❌ Processing Reject message")

            ref_seq_num = fix.RefSeqNum()
            text = fix.Text()
            ref_msg_type = fix.RefMsgType()
            session_reject_reason = fix.SessionRejectReason()

            if message.isSetField(ref_seq_num):
                message.getField(ref_seq_num)
                print(f"[OM]   RefSeqNum: {ref_seq_num.getValue()}")

            if message.isSetField(text):
                message.getField(text)
                print(f"[OM]   Text: {text.getValue()}")

            if message.isSetField(ref_msg_type):
                message.getField(ref_msg_type)
                print(f"[OM]   RefMsgType: {ref_msg_type.getValue()}")

            if message.isSetField(session_reject_reason):
                message.getField(session_reject_reason)
                reason_code = session_reject_reason.getValue()
                reason_map = {
                    "0": "Invalid Tag Number",
                    "1": "Required Tag Missing",
                    "2": "Tag Not Defined for This Message Type",
                    "3": "Undefined Tag",
                    "4": "Tag Specified Without a Value",
                    "5": "Value is Incorrect (Out of Range) for This Tag",
                    "6": "Incorrect Data Format for Value",
                    "7": "Decryption Problem",
                    "8": "Signature Problem",
                    "9": "CompID Problem",
                    "10": "SendingTime Accuracy Problem",
                    "11": "Invalid MsgType",
                    "12": "XML Validation Error",
                    "13": "Tag Appears More Than Once",
                    "14": "Tag Specified Out of Required Order",
                    "15": "Repeating Group Fields Out of Order",
                    "16": "Incorrect NumInGroup Count for Repeating Group",
                    "17": "Non-Data Value Includes Field Delimiter",
                    "18": "Invalid/Unsupported Application Version",
                    "99": "Other"
                }
                print(f"[OM]   Reject Reason: {reason_code} - {reason_map.get(reason_code, 'Unknown')}")

            text_val = text.getValue() if text.isSet() else ""
            import re
            cl_ord_id_match = re.search(r'ClOrdID[=:\s]*([A-Z0-9_]+)', text_val)
            if cl_ord_id_match:
                affected_cl_ord_id = cl_ord_id_match.group(1)
                print(f"[OM]   Affected ClOrdID: {affected_cl_ord_id}")

                if affected_cl_ord_id in self.order_store:
                    self.order_store[affected_cl_ord_id]['status'] = 'REJECTED'
                    self.order_store[affected_cl_ord_id]['reject_reason'] = text_val

            print(f"[OM]   Raw message: {message.toString().replace(chr(1), '|')}")

        except Exception as e:
            print(f"[ERROR] Processing Reject: {e}")
            import traceback
            traceback.print_exc()