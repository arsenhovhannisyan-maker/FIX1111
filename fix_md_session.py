import quickfix as fix
import quickfix44 as fix44
from datetime import datetime
import os
from dotenv import load_dotenv
from data_store import market_data_store

load_dotenv()

class FIXMarketDataApp(fix.Application):
    def __init__(self):
        super().__init__()
        self.session_id = None
        self.market_session_active = False
        self.market_data_subscriptions = {}
        self.fix_password = os.getenv('FIX_PASSWORD_MD')
        self.security_instruments = []
        self.logon_sent = False
        self.security_list_received = False
        self.security_requests = {}

    def onCreate(self, sessionID):
        self.session_id = sessionID
        print(f"[MD] Session created: {sessionID}")

    def onLogon(self, sessionID):
        print("[MD] Logon successful")
        self.logon_sent = True

    def onLogout(self, sessionID):
        print("[MD] Logout")
        self.market_session_active = False
        self.logon_sent = False

    def toAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        if msg_type.getValue() == fix.MsgType_Logon:
            message.setField(fix.Password(self.fix_password))

    def toApp(self, message, sessionID):

        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        if msg_type_val == "x":
            print(f"[DEBUG] SecurityListRequest raw: {message.toString()}")

        print(f"[MD] Sending: {msg_type_val}")

    def fromAdmin(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()

        if msg_type_val == "3":
            self.process_reject(message)
        elif msg_type_val == "5":
            text = fix.Text()
            if message.isSetField(text):
                message.getField(text)
                print(f"[MD] Logout reason: {text.getValue()}")

    def fromApp(self, message, sessionID):
        msg_type = fix.MsgType()
        message.getHeader().getField(msg_type)
        msg_type_val = msg_type.getValue()
        print(f"[MD] Received message type: {msg_type_val}")
        try:
            if msg_type_val == "h":
                self.process_trading_session_status(message)
            elif msg_type_val == "W":
                self.process_market_data_snapshot(message)
            elif msg_type_val == "X":
                self.process_market_data_incremental(message)
            elif msg_type_val == "Y":
                self.process_market_data_request_reject(message)
            elif msg_type_val == "y":
                self.process_security_list(message)
            elif msg_type_val == "d":
                self.process_security_definition(message)
            elif msg_type_val == "AG":
                self.process_quote_request_reject(message)
            elif msg_type_val == "j":
                self.process_business_message_reject(message)
            elif msg_type_val == "3":
                self.process_reject(message)
        except Exception as e:
            print(f"[ERROR] Processing {msg_type_val}: {e}")

    def process_trading_session_status(self, message):
        try:
            trading_session_id = fix.StringField(336)
            trad_sess_status = fix.CharField(340)

            if message.isSetField(trading_session_id) and message.isSetField(trad_sess_status):
                message.getField(trading_session_id)
                message.getField(trad_sess_status)

                if trading_session_id.getValue() == "Market Data" and trad_sess_status.getValue() == "2":
                    self.market_session_active = True
                    print("[MD] ✓ Market Data session OPEN")
        except Exception as e:
            print(f"[ERROR] Processing TradingSessionStatus: {e}")

    def send_market_data_request(self, symbol, subscribe=True, is_rfs=False):
        try:
            if not self.market_session_active:
                return

            req_id = f"MD_{symbol}_{datetime.now().strftime('%H%M%S%f')}"

            msg = fix44.MarketDataRequest()
            msg.setField(fix.MDReqID(req_id))
            md_update_type = 0
            if is_rfs:
                # Для RFS запросов
                msg.setField(fix.SubscriptionRequestType('0'))
                msg.setField(fix.MarketDepth(1))
                md_update_type = 0  # Или 2? Нужно тестировать!
            else:
                if subscribe:
                    msg.setField(fix.SubscriptionRequestType('1'))
                else:
                    msg.setField(fix.SubscriptionRequestType('2'))

                msg.setField(fix.MarketDepth(0))
                msg.setField(fix.MDUpdateType(1))

                if '_SPOT' in symbol or '/' in symbol and '_' not in symbol:
                    md_update_type = 1  # Incremental для спотов
                elif '_ON' in symbol or '_TN' in symbol:
                    md_update_type = 0  # Full для свопов?
                elif '_1W' in symbol or '_2W' in symbol or '_1Y' in symbol:
                    md_update_type = 0  # Full для форвардов?
                elif '_OUT' in symbol or 'broken' in symbol.lower():
                    md_update_type = 0  # Full для broken dates?
                else:
                    md_update_type = 1

            msg.setField(fix.MDUpdateType(md_update_type))
            related_sym_group = fix44.MarketDataRequest.NoRelatedSym()
            related_sym_group.setField(fix.Symbol(symbol))
            msg.addGroup(related_sym_group)

            entry_types = ['0', '1']
            for et in entry_types:
                md_entry_group = fix44.MarketDataRequest.NoMDEntryTypes()
                md_entry_group.setField(fix.MDEntryType(et))
                msg.addGroup(md_entry_group)

            fix.Session.sendToTarget(msg, self.session_id)

            if subscribe:
                print(f"[MD] Subscribed to {symbol}")
                self.market_data_subscriptions[symbol] = req_id
            else:
                print(f"[MD] Unsubscribed from {symbol}")
                if symbol in self.market_data_subscriptions:
                    del self.market_data_subscriptions[symbol]

        except Exception as e:
            print(f"[ERROR] Sending MarketDataRequest: {e}")

    def send_rfs_market_data_request(self, symbol):

        return self.send_market_data_request(symbol, subscribe=True, is_rfs=True)

    def send_market_data_unsubscribe(self, symbol):

        return self.send_market_data_request(symbol, subscribe=False)

    def process_market_data_snapshot(self, message):
        try:
            symbol = fix.Symbol()
            md_req_id = fix.MDReqID()

            if not message.isSetField(symbol):
                return

            message.getField(symbol)
            sym = symbol.getValue()

            req_id = ""
            if message.isSetField(md_req_id):
                message.getField(md_req_id)
                req_id = md_req_id.getValue()

            print(f"[DATA] Snapshot for {sym}")

            bids, asks = [], []
            no_entries = fix.NoMDEntries()

            if message.isSetField(no_entries):
                message.getField(no_entries)
                count = no_entries.getValue()

                group = fix44.MarketDataSnapshotFullRefresh.NoMDEntries()

                for i in range(1, count + 1):
                    message.getGroup(i, group)

                    entry_type = fix.MDEntryType()
                    if not group.isSetField(entry_type):
                        continue

                    group.getField(entry_type)
                    entry_type_val = entry_type.getValue()

                    price_val = 0.0
                    price = fix.MDEntryPx()
                    if group.isSetField(price):
                        group.getField(price)
                        price_val = float(price.getValue())

                    size_val = 0.0
                    size = fix.MDEntrySize()
                    if group.isSetField(size):
                        group.getField(size)
                        size_val = float(size.getValue())

                    entry = {"price": price_val, "size": size_val}

                    if entry_type_val == '0':
                        bids.append(entry)
                    elif entry_type_val == '1':
                        asks.append(entry)

            bids.sort(key=lambda x: x["price"], reverse=True)
            asks.sort(key=lambda x: x["price"])

            market_data_store.update(sym, {
                'symbol': sym,
                'timestamp': datetime.now().isoformat(),
                'bids': bids,
                'asks': asks,
                'last_update': datetime.now().isoformat()
            })

            print(f"[DATA] {sym}: {len(bids)} bids, {len(asks)} asks")

        except Exception as e:
            print(f"[ERROR] Processing snapshot: {e}")

    def process_market_data_incremental(self, message):
        print("[DATA] Incremental update received")

    def process_security_definition(self, message):
        symbol = fix.Symbol()
        if message.isSetField(symbol):
            message.getField(symbol)
            sym = symbol.getValue()
            if sym not in self.security_instruments:
                self.security_instruments.append(sym)
            print(f"[SECURITY] Definition for {sym}")

    def process_market_data_request_reject(self, message):
        print("[REJECT] MarketDataRequest rejected")

    def process_quote_request_reject(self, message):
        print("[REJECT] QuoteRequestReject received")

    def process_business_message_reject(self, message):
        print("[REJECT] BusinessMessageReject received")

    def process_reject(self, message):
        try:
            msg_type = fix.MsgType()
            ref_seq_num = fix.RefSeqNum()
            ref_tag_id = fix.RefTagID()
            text = fix.Text()

            message.getHeader().getField(msg_type)
            print(f"[REJECT] Message type: {msg_type.getValue()}")

            if message.isSetField(ref_seq_num):
                message.getField(ref_seq_num)
                print(f"[REJECT] RefSeqNum: {ref_seq_num.getValue()}")

            if message.isSetField(ref_tag_id):
                message.getField(ref_tag_id)
                print(f"[REJECT] Missing tag: {ref_tag_id.getValue()}")

            if message.isSetField(text):
                message.getField(text)
                print(f"[REJECT] Reason: {text.getValue()}")

        except Exception as e:
            print(f"[ERROR] Processing Reject: {e}")

    def process_security_list(self, message):
        try:
            print(f"[SECURITY] Processing Security List response")

            # Тег 320
            security_req_id_320 = fix.SecurityReqID()
            req_id_320 = ""
            if message.isSetField(security_req_id_320):
                message.getField(security_req_id_320)
                req_id_320 = security_req_id_320.getValue()
                print(f"[SECURITY] Got SecurityReqID (320): {req_id_320}")

            # Тег 322
            req_id_322 = ""
            try:
                field_322 = fix.StringField(322)
                if message.isSetField(field_322):
                    message.getField(field_322)
                    req_id_322 = field_322.getValue()
                    print(f"[SECURITY] Got SecurityRequestID (322): {req_id_322}")
            except Exception as e:
                print(f"[SECURITY] Error getting tag 322: {e}")

            print(f"[SECURITY] Response IDs - 320: {req_id_320}, 322: {req_id_322}")

            no_related_sym = fix.NoRelatedSym()
            if message.isSetField(no_related_sym):
                message.getField(no_related_sym)
                symbol_count = no_related_sym.getValue()
                print(f"[SECURITY] Number of symbols in response: {symbol_count}")

                self.security_instruments = []

                for i in range(1, symbol_count + 1):
                    group = fix44.SecurityList.NoRelatedSym()
                    if message.getGroup(i, group):
                        symbol = fix.Symbol()
                        if group.isSetField(symbol):
                            group.getField(symbol)
                            instrument = symbol.getValue()
                            self.security_instruments.append(instrument)

                print(f"[SECURITY] Successfully parsed {len(self.security_instruments)} instruments")

                if self.security_instruments:
                    print(f"[SECURITY] Sample instruments: {self.security_instruments[:3]}")

            self.security_list_received = True
            print(f"[SECURITY] ✓ Security list loaded")

        except Exception as e:
            print(f"[ERROR] Process SecurityList: {e}")

    def send_security_definition_request(self, symbol):
        try:
            if not self.market_session_active:
                return None

            from time import time
            req_id = f"SD_{symbol}_{int(time() * 1000)}"

            message = fix44.SecurityDefinitionRequest()
            message.setField(fix.SecurityReqID(req_id))
            message.setField(fix.StringField(322, req_id))
            message.setField(fix.Symbol(symbol))
            message.setField(fix.SubscriptionRequestType(1))
            message.setField(fix.CharField(263, '1'))
            message.setField(fix.IntField(320, 0))

            fix.Session.sendToTarget(message, self.session_id)
            print(f"[SECURITY] Definition request sent for {symbol}")
            return req_id

        except Exception as e:
            print(f"[ERROR] SecurityDefinitionRequest: {e}")
            return None

    def send_security_list_request(self):
        if not self.market_session_active:
            return None

        from time import time
        req_id = f"SL_{int(time() * 1000)}"

        msg = fix44.SecurityListRequest()

        msg.setField(fix.SecurityReqID(req_id))
        msg.setField(fix.StringField(322, req_id))
        msg.setField(fix.SecurityListRequestType(0))


        print(f"[MD] ✅ SecurityListRequest sent OK (320/322={req_id})")
        return req_id