import quickfix as fix
import quickfix44 as fix44
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class OrderSession(fix.Application):
    def __init__(self):
        super().__init__()
        self.session_id = None
        self.trading_session_open = False
        self.orders = {}
        self.exec_reports = []
        self.clordid_counter = 1000
        self.fix_password = os.getenv('FIX_PASSWORD_OM')
        self.logon_sent = False

    def onCreate(self, sessionID):
        self.session_id = sessionID
        print(f"[OM] Session created: {sessionID}")

    def onLogon(self, sessionID):
        print("[OM] Logon successful")
        self.logon_sent = True

    def onLogout(self, sessionID):
        print("[OM] Logout")
        self.trading_session_open = False
        self.logon_sent = False

    def toAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)

        if msg_type.getValue() == fix.MsgType_Logon:
            message.setField(fix.Password(self.fix_password))
            message.setField(fix.StringField(336, "Trade Data"))


    def toApp(self, message, sessionID):

        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()
        print(f"[OM] Sending: {msg_type_val}")

    def fromAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)

        if msg_type.getValue() == fix.MsgType_Reject:
            self.process_reject(message)

    def fromApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        if msg_type_val == "8":
            self.process_execution_report(message)
        elif msg_type_val == "9":
            self.process_cancel_reject(message)
        elif msg_type_val == "h":
            self.process_session_status(message)
        elif msg_type_val == "j":
            self.process_business_message_reject(message)

    def process_session_status(self, message):
        session_id_field = fix.StringField(336)
        status_field = fix.CharField(340)

        if message.isSetField(session_id_field) and message.isSetField(status_field):
            message.getField(session_id_field)
            message.getField(status_field)

            if session_id_field.getValue() == "Trade Data" and status_field.getValue() == "2":
                self.trading_session_open = True
                print("[OM] ✓ Trading session OPEN")

    def send_new_order_single(self, symbol, side, quantity, price=None, price2=None,
                              order_type="2", time_in_force="1"):

        try:
            if not self.trading_session_open:
                print("[OM] Session not open")
                return None

            self.clordid_counter += 1
            cl_ord_id = f"ORD{self.clordid_counter}"

            msg = fix44.NewOrderSingle()
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.Symbol(symbol))
            msg.setField(fix.Side(side))
            msg.setField(fix.OrderQty(quantity))
            msg.setField(fix.OrdType(order_type))
            msg.setField(fix.TimeInForce(time_in_force))
            msg.setField(fix.StringField(336, "Trade Data"))

            if order_type == "2" and price:
                msg.setField(fix.Price(price))


            if '_ON' in symbol or '_TN' in symbol or '_1W' in symbol or price2:
                if price2:
                    msg.setField(fix.Price2(price2))
                elif price:
                    msg.setField(fix.Price2(price))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Order sent: {cl_ord_id} {symbol} {quantity}")

            self.orders[cl_ord_id] = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'order_type': order_type,
                'time_in_force': time_in_force,
                'status': 'PENDING',
                'timestamp': datetime.now().isoformat()
            }

            return cl_ord_id

        except Exception as e:
            print(f"[ERROR] Sending order: {e}")
            return None

    def send_order_cancel_request(self, orig_cl_ord_id):

        try:
            if orig_cl_ord_id not in self.orders:
                return False

            order = self.orders[orig_cl_ord_id]

            self.clordid_counter += 1
            cl_ord_id = f"CXL{self.clordid_counter}"

            msg = fix44.OrderCancelRequest()
            msg.setField(fix.OrigClOrdID(orig_cl_ord_id))
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.Symbol(order['symbol']))
            msg.setField(fix.Side(order['side']))
            msg.setField(fix.StringField(336, "Trade Data"))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Cancel sent for {orig_cl_ord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] Sending cancel: {e}")
            return False

    def send_order_status_request(self, cl_ord_id):

        try:
            msg = fix44.OrderStatusRequest()
            msg.setField(fix.ClOrdID(cl_ord_id))
            msg.setField(fix.Symbol("*"))
            msg.setField(fix.StringField(336, "Trade Data"))

            transact_time = fix.TransactTime()
            transact_time.setString(datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[:-3])
            msg.setField(transact_time)

            fix.Session.sendToTarget(msg, self.session_id)

            print(f"[OM] Status request for {cl_ord_id}")
            return True

        except Exception as e:
            print(f"[ERROR] Sending status request: {e}")
            return False

    def process_execution_report(self, message):

        try:
            cl_ord_id = fix.ClOrdID()
            ord_status = fix.OrdStatus()
            exec_type = fix.ExecType()
            symbol = fix.Symbol()
            cum_qty = fix.CumQty()
            leaves_qty = fix.LeavesQty()
            avg_px = fix.AvgPx()
            text = fix.Text()


            cl_ord_id_val = ""
            if message.isSetField(cl_ord_id):
                message.getField(cl_ord_id)
                cl_ord_id_val = cl_ord_id.getValue()

            ord_status_val = ""
            if message.isSetField(ord_status):
                message.getField(ord_status)
                ord_status_val = ord_status.getValue()

            text_val = ""
            if message.isSetField(text):
                message.getField(text)
                text_val = text.getValue()

            print(f"[OM] ExecutionReport: {cl_ord_id_val} = {ord_status_val}")

            if cl_ord_id_val in self.orders:
                self.orders[cl_ord_id_val]['status'] = ord_status_val
                self.orders[cl_ord_id_val]['text'] = text_val

                status_map = {
                    "0": "New", "1": "PartiallyFilled", "2": "Filled",
                    "4": "Cancelled", "8": "Rejected"
                }
                status_text = status_map.get(ord_status_val, ord_status_val)
                print(f"[OM] Order {cl_ord_id_val}: {status_text}")

        except Exception as e:
            print(f"[ERROR] Processing execution: {e}")

    def process_cancel_reject(self, message):
        print("[OM] OrderCancelReject received")

    def process_business_message_reject(self, message):
        print("[OM] BusinessMessageReject received")

    def process_reject(self, message):
        text = fix.Text()
        if message.isSetField(text):
            message.getField(text)
            print(f"[REJECT] {text.getValue()}")

    def get_order_info(self, cl_ord_id):
        return self.orders.get(cl_ord_id)

    def get_all_orders(self):
        return self.orders

    def get_execution_history(self):
        return self.exec_reports